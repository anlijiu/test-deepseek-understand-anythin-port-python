"""Python language extractor.

Port of the TypeScript ``PythonExtractor`` — extracts functions, classes,
imports, exports, and call-graph edges from Python source via tree-sitter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from understand_anything.plugins.extractors.base import (
    child_by_field_name,
    find_child,
    find_children,
)
from understand_anything.plugins.extractors.types import LanguageExtractor
from understand_anything.types import (
    CallGraphEntry,
    ClassInfo,
    ExportInfo,
    FunctionInfo,
    ImportInfo,
    StructuralAnalysis,
)

if TYPE_CHECKING:
    from tree_sitter import Node


# ---------------------------------------------------------------------------
# Node type helpers
# ---------------------------------------------------------------------------


def _extract_params(params_node: Node | None) -> list[str]:
    """Extract parameter names from a Python ``parameters`` node.

    Handles ``identifier``, ``typed_parameter``, ``default_parameter``,
    ``typed_default_parameter``, ``list_splat_pattern`` (*args), and
    ``dictionary_splat_pattern`` (**kwargs).
    """
    if params_node is None:
        return []
    params: list[str] = []

    for child in params_node.children:
        if not child.is_named:
            continue
        child_type = child.type

        if child_type == "identifier":
            text = child.text
            if text is not None:
                name = text.decode("utf-8")
                if name not in ("self", "cls"):
                    params.append(name)

        elif child_type in (
            "typed_parameter",
            "default_parameter",
            "typed_default_parameter",
        ):
            ident = find_child(child, "identifier")
            if ident is not None and ident.text is not None:
                name = ident.text.decode("utf-8")
                if name not in ("self", "cls"):
                    params.append(name)

        elif child_type == "list_splat_pattern":
            ident = find_child(child, "identifier")
            if ident is not None and ident.text is not None:
                params.append("*" + ident.text.decode("utf-8"))

        elif child_type == "dictionary_splat_pattern":
            ident = find_child(child, "identifier")
            if ident is not None and ident.text is not None:
                params.append("**" + ident.text.decode("utf-8"))

    return params


def _extract_return_type(node: Node) -> str | None:
    """Extract the return type annotation from a function_definition node.

    Python AST uses a ``return_type`` field (the node after ``->``).
    """
    return_type = child_by_field_name(node, "return_type")
    if return_type is not None and return_type.text is not None:
        return return_type.text.decode("utf-8")
    return None


def _unwrap_decorated(node: Node) -> Node:
    """Unwrap a ``decorated_definition`` to get the inner definition.

    If the node is not a decorated_definition, returns the node itself.
    """
    if node.type == "decorated_definition":
        inner = find_child(node, "function_definition") or find_child(
            node, "class_definition"
        )
        if inner is not None:
            return inner
    return node


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class PythonExtractor(LanguageExtractor):
    """Structural extractor for Python source code.

    Handles functions, classes, imports, exports, and call graph extraction
    using the tree-sitter-python grammar.  Python has no formal export syntax,
    so all top-level function and class definitions are treated as exports.
    """

    @property
    def language_ids(self) -> list[str]:
        return ["python"]

    # ------------------------------------------------------------------
    # Structure extraction
    # ------------------------------------------------------------------

    def extract_structure(self, root_node: Node) -> StructuralAnalysis:
        """Extract all structural information from a Python AST."""
        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []
        imports: list[ImportInfo] = []
        exports: list[ExportInfo] = []

        for child in root_node.children:
            # Unwrap decorated definitions to get the inner node
            inner = _unwrap_decorated(child)

            if inner.type == "function_definition":
                self._extract_function(inner, functions)
                self._extract_nested_functions(inner, functions)
                self._add_export(inner, child, exports)

            elif inner.type == "class_definition":
                self._extract_class(inner, classes)
                self._extract_class_nested_functions(inner, functions)
                self._add_export(inner, child, exports)

            elif inner.type == "import_statement":
                self._extract_import(inner, imports)

            elif inner.type == "import_from_statement":
                self._extract_from_import(inner, imports)

        return StructuralAnalysis(
            functions=functions,
            classes=classes,
            imports=imports,
            exports=exports,
        )

    # ------------------------------------------------------------------
    # Call graph extraction
    # ------------------------------------------------------------------

    def extract_call_graph(self, root_node: Node) -> list[CallGraphEntry]:
        """Extract caller → callee relationships from Python source."""
        entries: list[CallGraphEntry] = []
        function_stack: list[str] = []

        def walk_for_calls(node: Node) -> None:
            pushed_name = False

            # Track entering function/method definitions
            if node.type == "function_definition":
                name_node = child_by_field_name(node, "name")
                if name_node is not None and name_node.text is not None:
                    function_stack.append(name_node.text.decode("utf-8"))
                    pushed_name = True

            # Extract call expressions
            if node.type == "call":
                callee_node = next(
                    (
                        c
                        for c in node.children
                        if c.type in ("identifier", "attribute")
                    ),
                    None,
                )
                if callee_node is not None and function_stack:
                    entries.append(
                        CallGraphEntry(
                            caller=function_stack[-1],
                            callee=callee_node.text.decode("utf-8")
                            if callee_node.text
                            else "<unknown>",
                            line_number=node.start_point[0] + 1,
                        )
                    )

            for child in node.children:
                walk_for_calls(child)

            if pushed_name:
                function_stack.pop()

        walk_for_calls(root_node)
        return entries

    # ------------------------------------------------------------------
    # Private helpers — function
    # ------------------------------------------------------------------

    def _extract_function(
        self, node: Node, functions: list[FunctionInfo]
    ) -> None:
        """Extract function info from a function_definition node."""
        name_node = child_by_field_name(node, "name")
        if name_node is None or name_node.text is None:
            return

        params_node = child_by_field_name(node, "parameters")
        params = _extract_params(params_node)
        return_type = _extract_return_type(node)

        functions.append(
            FunctionInfo(
                name=name_node.text.decode("utf-8"),
                line_range=(node.start_point[0] + 1, node.end_point[0] + 1),
                params=params,
                return_type=return_type,
            )
        )

    def _extract_nested_functions(
        self, node: Node, functions: list[FunctionInfo]
    ) -> None:
        """Extract nested function definitions inside *node*.

        Nested functions can appear as call-graph callers. Creating function
        nodes for them keeps Pipeline call edges referentially valid.
        """
        body = child_by_field_name(node, "body")
        if body is None:
            return

        for child in body.children:
            inner = _unwrap_decorated(child)
            if inner.type == "function_definition":
                self._extract_function(inner, functions)
                self._extract_nested_functions(inner, functions)

    def _extract_class_nested_functions(
        self, node: Node, functions: list[FunctionInfo]
    ) -> None:
        """Extract functions nested inside class methods."""
        body = child_by_field_name(node, "body")
        if body is None:
            return

        for member in body.children:
            inner_member = _unwrap_decorated(member)
            if inner_member.type == "function_definition":
                self._extract_nested_functions(inner_member, functions)

    # ------------------------------------------------------------------
    # Private helpers — class
    # ------------------------------------------------------------------

    def _extract_class(
        self, node: Node, classes: list[ClassInfo]
    ) -> None:
        """Extract class info from a class_definition node."""
        name_node = child_by_field_name(node, "name")
        if name_node is None or name_node.text is None:
            return

        methods: list[str] = []
        properties: list[str] = []

        body = child_by_field_name(node, "body")
        if body is not None:
            for member in body.children:
                if not member.is_named:
                    continue

                # Methods: function_definition or decorated_definition
                # wrapping a function_definition
                inner_member = _unwrap_decorated(member)
                if inner_member.type == "function_definition":
                    method_name = child_by_field_name(inner_member, "name")
                    if method_name is not None and method_name.text is not None:
                        methods.append(method_name.text.decode("utf-8"))

                # Properties: type-annotated assignments at class body level
                # e.g., ``name: str`` or ``value: int = 0``
                if member.type == "expression_statement":
                    assignment = find_child(member, "assignment")
                    if assignment is not None:
                        # Check if this is a type-annotated class-level
                        # assignment (has a ``type`` child)
                        type_node = find_child(assignment, "type")
                        name_ident = find_child(assignment, "identifier")
                        if type_node is not None and name_ident is not None:
                            properties.append(
                                name_ident.text.decode("utf-8")
                                if name_ident.text
                                else "<unknown>"
                            )

        classes.append(
            ClassInfo(
                name=name_node.text.decode("utf-8"),
                line_range=(node.start_point[0] + 1, node.end_point[0] + 1),
                methods=methods,
                properties=properties,
            )
        )

    # ------------------------------------------------------------------
    # Private helpers — imports
    # ------------------------------------------------------------------

    def _extract_import(
        self, node: Node, imports: list[ImportInfo]
    ) -> None:
        """Extract info from an ``import_statement`` node.

        Handles ``import os``, ``import os.path``, and
        ``import os, sys as system``.
        """
        dotted_names = find_children(node, "dotted_name")
        aliased_imports = find_children(node, "aliased_import")

        for dn in dotted_names:
            if dn.text is not None:
                source = dn.text.decode("utf-8")
                imports.append(
                    ImportInfo(
                        source=source,
                        specifiers=[source],
                        line_number=node.start_point[0] + 1,
                    )
                )

        for ai in aliased_imports:
            dotted_name = find_child(ai, "dotted_name")
            alias = next(
                (c for c in ai.children if c.type == "identifier"), None
            )
            if dotted_name is not None and dotted_name.text is not None:
                source = dotted_name.text.decode("utf-8")
                specifier = (
                    alias.text.decode("utf-8")
                    if (alias is not None and alias.text is not None)
                    else source
                )
                imports.append(
                    ImportInfo(
                        source=source,
                        specifiers=[specifier],
                        line_number=node.start_point[0] + 1,
                    )
                )

    def _extract_from_import(
        self, node: Node, imports: list[ImportInfo]
    ) -> None:
        """Extract info from an ``import_from_statement`` node.

        Handles ``from pathlib import Path``,
        ``from typing import Optional, List``,
        ``from foo import bar as baz``, and
        ``from os.path import *``.
        """
        module_node = child_by_field_name(node, "module_name")
        source = (
            module_node.text.decode("utf-8")
            if (module_node is not None and module_node.text is not None)
            else ""
        )

        specifiers: list[str] = []

        # Collect dotted_name specifiers (non-aliased)
        # Skip the module_name dotted_name (compare by node id)
        module_node_id = module_node.id if module_node is not None else None
        all_dotted_names = find_children(node, "dotted_name")
        for dn in all_dotted_names:
            if module_node_id is not None and dn.id == module_node_id:
                continue
            if dn.text is not None:
                specifiers.append(dn.text.decode("utf-8"))

        # Collect aliased imports: ``from foo import bar as baz``
        aliased_imports = find_children(node, "aliased_import")
        for ai in aliased_imports:
            alias = next(
                (c for c in ai.children if c.type == "identifier"), None
            )
            if alias is not None and alias.text is not None:
                specifiers.append(alias.text.decode("utf-8"))

        # Handle wildcard imports: ``from os import *``
        if find_child(node, "wildcard_import") is not None:
            specifiers.append("*")

        imports.append(
            ImportInfo(
                source=source,
                specifiers=specifiers,
                line_number=node.start_point[0] + 1,
            )
        )

    # ------------------------------------------------------------------
    # Private helpers — exports
    # ------------------------------------------------------------------

    @staticmethod
    def _add_export(
        inner: Node, outer: Node, exports: list[ExportInfo]
    ) -> None:
        """Add a top-level definition as an export."""
        name_node = child_by_field_name(inner, "name")
        if name_node is not None and name_node.text is not None:
            exports.append(
                ExportInfo(
                    name=name_node.text.decode("utf-8"),
                    line_number=outer.start_point[0] + 1,
                )
            )
