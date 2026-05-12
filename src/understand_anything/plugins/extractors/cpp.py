"""C/C++ language extractor.

Python port of the TypeScript ``CppExtractor`` — extracts functions, classes,
structs, #include directives, namespace-scoped declarations, out-of-class
method definitions, and call-graph edges from C/C++ source via tree-sitter.

Covers both C (``.c``, ``.h``) and C++ (``.cpp``, ``.cc``, ``.cxx``, ``.hpp``,
``.hh``, ``.hxx``) source files.

Handles:
  - Free functions (function_definition)
  - Classes (class_specifier) with methods, properties, access specifiers
  - Structs (struct_specifier) with fields
  - #include directives mapped to imports
  - Namespaces (namespace_definition) with recursive traversal
  - Out-of-class method definitions (e.g., ``void Server::start()``)
  - Call graph extraction from call_expression nodes
  - Static detection for export filtering

C/C++ has no formal export syntax. Non-static top-level functions and
public class/struct members are treated as exports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from understand_anything.plugins.extractors.base import (
    find_child,
    find_children,
    get_node_text,
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
# Node type constants (tree-sitter-cpp grammar)
# ---------------------------------------------------------------------------

_PROGRAM = "translation_unit"
_PREPROC_INCLUDE = "preproc_include"
_CLASS_SPECIFIER = "class_specifier"
_STRUCT_SPECIFIER = "struct_specifier"
_FUNCTION_DEFINITION = "function_definition"
_NAMESPACE_DEFINITION = "namespace_definition"
_DECLARATION = "declaration"
_DECLARATION_LIST = "declaration_list"
_FIELD_DECLARATION = "field_declaration"
_FIELD_DECLARATION_LIST = "field_declaration_list"
_FUNCTION_DECLARATOR = "function_declarator"
_PARAMETER_LIST = "parameter_list"
_PARAMETER_DECLARATION = "parameter_declaration"
_CALL_EXPRESSION = "call_expression"
_FIELD_EXPRESSION = "field_expression"
_IDENTIFIER = "identifier"
_FIELD_IDENTIFIER = "field_identifier"
_QUALIFIED_IDENTIFIER = "qualified_identifier"
_NAMESPACE_IDENTIFIER = "namespace_identifier"
_ACCESS_SPECIFIER = "access_specifier"
_STORAGE_CLASS_SPECIFIER = "storage_class_specifier"
_SYSTEM_LIB_STRING = "system_lib_string"
_STRING_LITERAL = "string_literal"
_STRING_CONTENT = "string_content"
_POINTER_DECLARATOR = "pointer_declarator"
_REFERENCE_DECLARATOR = "reference_declarator"
_ARRAY_DECLARATOR = "array_declarator"


# ---------------------------------------------------------------------------
# Recursive declarator unwrapping
# ---------------------------------------------------------------------------


def _unwrap_declarator_name(node: Node) -> str | None:
    """Recursively unwrap nested declarators to find the leaf identifier.

    C/C++ parameter declarators can be deeply nested::

        ``char** pp`` → pointer_declarator → pointer_declarator → identifier("pp")
        ``const std::string& ref`` → reference_declarator → identifier("ref")
        ``int arr[]`` → array_declarator → identifier("arr")
    """
    if node.type in (_IDENTIFIER, _FIELD_IDENTIFIER):
        return get_node_text(node)

    # Dig into the nested declarator field
    inner = node.child_by_field_name("declarator")
    if inner:
        return _unwrap_declarator_name(inner)

    # Fallback: look for direct identifier/field_identifier child
    ident = (
        find_child(node, _IDENTIFIER)
        or find_child(node, _FIELD_IDENTIFIER)
    )
    if ident:
        return get_node_text(ident)

    return None


def _extract_func_decl_name(
    func_decl: Node,
) -> tuple[str, str | None] | None:
    """Extract function/method name from a function_declarator node.

    The declarator field can be:
      - ``identifier`` for free functions: ``int baz(int y)``
      - ``field_identifier`` for in-class declarations: ``void start();``
      - ``qualified_identifier`` for out-of-class: ``void Server::start()``

    For qualified_identifier, returns just the final name and the qualifier.
    """
    decl_node = func_decl.child_by_field_name("declarator")
    if decl_node is None:
        return None

    if decl_node.type in (_IDENTIFIER, _FIELD_IDENTIFIER):
        return (get_node_text(decl_node), None)

    if decl_node.type == _QUALIFIED_IDENTIFIER:
        name_node = decl_node.child_by_field_name("name")
        ns_node = find_child(decl_node, _NAMESPACE_IDENTIFIER)
        return (
            get_node_text(name_node) if name_node else get_node_text(decl_node),
            get_node_text(ns_node) if ns_node else None,
        )

    return (get_node_text(decl_node), None)


def _extract_params(params_node: Node | None) -> list[str]:
    """Extract parameter names from a parameter_list node."""
    if params_node is None:
        return []

    params: list[str] = []
    decls = find_children(params_node, _PARAMETER_DECLARATION)
    for decl in decls:
        decl_node = decl.child_by_field_name("declarator")
        if decl_node:
            name = _unwrap_declarator_name(decl_node)
            if name:
                params.append(name)

    return params


def _extract_return_type(node: Node) -> str | None:
    """Extract the return type text from a function_definition node."""
    type_node = node.child_by_field_name("type")
    if type_node:
        return get_node_text(type_node)
    return None


def _is_static(node: Node) -> bool:
    """Check if a function_definition has a ``static`` storage_class_specifier."""
    storage = find_child(node, _STORAGE_CLASS_SPECIFIER)
    return storage is not None and get_node_text(storage) == "static"


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class CppExtractor(LanguageExtractor):
    """Structural extractor for C and C++.

    Handles both C (``.c``, ``.h``) and C++ (``.cpp``, ``.cc``, ``.hpp``, etc.)
    source files using the tree-sitter-cpp grammar.
    """

    @property
    def language_ids(self) -> list[str]:
        return ["cpp", "c"]

    # ------------------------------------------------------------------
    # Structure extraction
    # ------------------------------------------------------------------

    def extract_structure(self, root_node: Node) -> StructuralAnalysis:
        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []
        imports: list[ImportInfo] = []
        exports: list[ExportInfo] = []

        # Track methods associated with classes via out-of-class definitions
        methods_by_class: dict[str, list[str]] = {}

        self._walk_top_level(
            root_node, functions, classes, imports, exports, methods_by_class
        )

        # Attach out-of-class methods to their corresponding classes
        for cls in classes:
            methods = methods_by_class.get(cls.name)
            if methods:
                for m in methods:
                    if m not in cls.methods:
                        cls.methods.append(m)

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
        entries: list[CallGraphEntry] = []
        function_stack: list[str] = []

        def _walk_for_calls(node: Node) -> None:
            pushed_name = False

            # Track entering function_definition
            if node.type == _FUNCTION_DEFINITION:
                name = self._extract_function_name(node)
                if name:
                    function_stack.append(name)
                    pushed_name = True

            # Extract call_expression nodes
            if node.type == _CALL_EXPRESSION and function_stack:
                callee = self._extract_callee_name(node)
                if callee:
                    entries.append(
                        CallGraphEntry(
                            caller=function_stack[-1],
                            callee=callee,
                            line_number=node.start_point[0] + 1,
                        )
                    )

            for child in node.children:
                _walk_for_calls(child)

            if pushed_name:
                function_stack.pop()

        _walk_for_calls(root_node)
        return entries

    # ------------------------------------------------------------------
    # Internal: top-level walk
    # ------------------------------------------------------------------

    def _walk_top_level(
        self,
        parent_node: Node,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
        imports: list[ImportInfo],
        exports: list[ExportInfo],
        methods_by_class: dict[str, list[str]],
    ) -> None:
        """Walk top-level declarations, recursing into namespaces."""
        for node in parent_node.children:
            node_type = node.type

            if node_type == _PREPROC_INCLUDE:
                self._extract_include(node, imports)

            elif node_type == _CLASS_SPECIFIER:
                self._extract_class_or_struct(
                    node, "class", classes, functions, exports
                )

            elif node_type == _STRUCT_SPECIFIER:
                self._extract_class_or_struct(
                    node, "struct", classes, functions, exports
                )

            elif node_type == _FUNCTION_DEFINITION:
                self._extract_function_def(
                    node, functions, exports, methods_by_class
                )

            elif node_type == _NAMESPACE_DEFINITION:
                body = find_child(node, _DECLARATION_LIST)
                if body:
                    self._walk_top_level(
                        body, functions, classes, imports, exports, methods_by_class
                    )

            elif node_type == _DECLARATION:
                # A top-level ";" terminated statement — class/struct specifiers
                # can appear as children of a declaration node
                inner_class = find_child(node, _CLASS_SPECIFIER)
                if inner_class:
                    self._extract_class_or_struct(
                        inner_class, "class", classes, functions, exports
                    )
                inner_struct = find_child(node, _STRUCT_SPECIFIER)
                if inner_struct:
                    self._extract_class_or_struct(
                        inner_struct, "struct", classes, functions, exports
                    )

    # ------------------------------------------------------------------
    # Internal: include extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_include(node: Node, imports: list[ImportInfo]) -> None:
        """Extract #include directive into the imports list."""
        path_node = node.child_by_field_name("path")
        if path_node is None:
            return

        if path_node.type == _SYSTEM_LIB_STRING:
            # Strip angle brackets: <iostream> → iostream
            text = get_node_text(path_node)
            source = text.strip("<>")
        elif path_node.type == _STRING_LITERAL:
            # Extract content from string: "myfile.h" → myfile.h
            content_node = find_child(path_node, _STRING_CONTENT)
            if content_node:
                source = get_node_text(content_node)
            else:
                text = get_node_text(path_node)
                source = text.strip('"')
        else:
            source = get_node_text(path_node)

        imports.append(
            ImportInfo(
                source=source,
                specifiers=[source],
                line_number=node.start_point[0] + 1,
            )
        )

    # ------------------------------------------------------------------
    # Internal: class/struct extraction
    # ------------------------------------------------------------------

    def _extract_class_or_struct(
        self,
        node: Node,
        kind: str,
        classes: list[ClassInfo],
        functions: list[FunctionInfo],
        exports: list[ExportInfo],
    ) -> None:
        """Extract class_specifier / struct_specifier into the classes array."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        class_name = get_node_text(name_node)
        methods: list[str] = []
        properties: list[str] = []

        body = node.child_by_field_name("body")
        if body and body.type == _FIELD_DECLARATION_LIST:
            # Default access: public for struct, private for class
            current_access = "public" if kind == "struct" else "private"

            for member in body.children:
                if member.type == _ACCESS_SPECIFIER:
                    spec_child = member.child(0)
                    if spec_child:
                        current_access = get_node_text(spec_child)
                    continue

                if member.type == _FIELD_DECLARATION:
                    decl_node = member.child_by_field_name("declarator")
                    if decl_node and decl_node.type == _FUNCTION_DECLARATOR:
                        # Method declaration (no body)
                        info = _extract_func_decl_name(decl_node)
                        if info:
                            methods.append(info[0])
                            if current_access == "public":
                                exports.append(
                                    ExportInfo(
                                        name=info[0],
                                        line_number=member.start_point[0] + 1,
                                    )
                                )
                    elif decl_node:
                        # Property
                        name = _unwrap_declarator_name(decl_node)
                        if name:
                            properties.append(name)

                if member.type == _FUNCTION_DEFINITION:
                    # Inline method definition
                    func_decl = member.child_by_field_name("declarator")
                    if func_decl and func_decl.type == _FUNCTION_DECLARATOR:
                        info = _extract_func_decl_name(func_decl)
                        if info:
                            methods.append(info[0])

                            params_node = func_decl.child_by_field_name("parameters")
                            functions.append(
                                FunctionInfo(
                                    name=info[0],
                                    line_range=(
                                        member.start_point[0] + 1,
                                        member.end_point[0] + 1,
                                    ),
                                    params=_extract_params(params_node),
                                    return_type=_extract_return_type(member),
                                )
                            )

                            if current_access == "public":
                                exports.append(
                                    ExportInfo(
                                        name=info[0],
                                        line_number=member.start_point[0] + 1,
                                    )
                                )

        classes.append(
            ClassInfo(
                name=class_name,
                line_range=(
                    node.start_point[0] + 1,
                    node.end_point[0] + 1,
                ),
                methods=methods,
                properties=properties,
            )
        )

        # The class/struct name itself is always an export
        exports.append(
            ExportInfo(
                name=class_name,
                line_number=node.start_point[0] + 1,
            )
        )

    # ------------------------------------------------------------------
    # Internal: function definition extraction
    # ------------------------------------------------------------------

    def _extract_function_def(
        self,
        node: Node,
        functions: list[FunctionInfo],
        exports: list[ExportInfo],
        methods_by_class: dict[str, list[str]],
    ) -> None:
        """Extract a free function or out-of-class method definition."""
        func_decl = node.child_by_field_name("declarator")
        if func_decl is None or func_decl.type != _FUNCTION_DECLARATOR:
            return

        info = _extract_func_decl_name(func_decl)
        if info is None:
            return

        func_name, qualifier = info
        params_node = func_decl.child_by_field_name("parameters")
        params = _extract_params(params_node)
        return_type = _extract_return_type(node)

        functions.append(
            FunctionInfo(
                name=func_name,
                line_range=(node.start_point[0] + 1, node.end_point[0] + 1),
                params=params,
                return_type=return_type,
            )
        )

        # Track out-of-class method definitions (e.g., void Server::start())
        if qualifier:
            if qualifier not in methods_by_class:
                methods_by_class[qualifier] = []
            methods_by_class[qualifier].append(func_name)

        # Non-static top-level functions are exports
        if not _is_static(node):
            exports.append(
                ExportInfo(
                    name=func_name,
                    line_number=node.start_point[0] + 1,
                )
            )

    # ------------------------------------------------------------------
    # Internal: function name extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_function_name(node: Node) -> str | None:
        """Extract the simple function name from a function_definition."""
        decl_node = node.child_by_field_name("declarator")
        if decl_node is None or decl_node.type != _FUNCTION_DECLARATOR:
            return None

        info = _extract_func_decl_name(decl_node)
        if info:
            return info[0]
        return None

    # ------------------------------------------------------------------
    # Internal: callee name extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_callee_name(call_node: Node) -> str | None:
        """Extract the callee name from a call_expression."""
        func_node = call_node.child(0)
        if func_node is None:
            return None

        if func_node.type == _IDENTIFIER:
            return get_node_text(func_node)

        if func_node.type == _FIELD_EXPRESSION:
            field = func_node.child_by_field_name("field")
            if field:
                return get_node_text(field)
            return get_node_text(func_node)

        if func_node.type == _QUALIFIED_IDENTIFIER:
            return get_node_text(func_node)

        return get_node_text(func_node)
