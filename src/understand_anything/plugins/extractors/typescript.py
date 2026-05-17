"""TypeScript / JavaScript language extractor.

Python port of the TypeScript ``LanguageExtractor`` for the TypeScript
and JavaScript language families.  Covers both ``.ts`` / ``.tsx`` and
``.js`` / ``.jsx`` / ``.mjs`` / ``.cjs`` source files.

Extracts:
  - Functions (declarations, arrow functions, exported functions)
  - Classes (with methods, properties, heritage)
  - Imports (named, default, namespace, type-only)
  - Exports (named, default, re-exports)
  - Call graph (caller → callee edges)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from understand_anything.plugins.extractors.base import (
    collect_nodes_of_type,
    find_child,
    find_children,
    get_node_text,
    get_string_value,
    traverse,
)
from understand_anything.plugins.extractors.types import LanguageExtractor
from understand_anything.types import (
    CallGraphEntry,
    ClassInfo,
    EnumInfo,
    ExportInfo,
    FunctionInfo,
    ImportInfo,
    InheritanceInfo,
    InterfaceInfo,
    MethodInfo,
    StructuralAnalysis,
    TypeAliasInfo,
    VariableInfo,
)

if TYPE_CHECKING:
    from tree_sitter import Node


# ---------------------------------------------------------------------------
# Node type constants (tree-sitter-typescript grammar)
# ---------------------------------------------------------------------------

_PROGRAM = "program"
_FUNCTION_DECLARATION = "function_declaration"
_GENERATOR_FUNCTION_DECLARATION = "generator_function_declaration"
_METHOD_DEFINITION = "method_definition"
_ARROW_FUNCTION = "arrow_function"
_CLASS_DECLARATION = "class_declaration"
_ABSTRACT_CLASS_DECLARATION = "abstract_class_declaration"
_IMPORT_STATEMENT = "import_statement"
_EXPORT_STATEMENT = "export_statement"
_EXPORT_CLAUSE = "export_clause"
_LEXICAL_DECLARATION = "lexical_declaration"
_VARIABLE_DECLARATION = "variable_declaration"
_CALL_EXPRESSION = "call_expression"
_NEW_EXPRESSION = "new_expression"
_IDENTIFIER = "identifier"
_MEMBER_EXPRESSION = "member_expression"
_PROPERTY_IDENTIFIER = "property_identifier"
_STRING = "string"
_TEMPLATE_STRING = "template_string"
_STATEMENT_BLOCK = "statement_block"
_FORMAL_PARAMETERS = "formal_parameters"
_REQUIRED_PARAMETER = "required_parameter"
_OPTIONAL_PARAMETER = "optional_parameter"
_TYPE_ANNOTATION = "type_annotation"
_PUBLIC_FIELD_DEFINITION = "public_field_definition"
_PRIVATE_FIELD_DEFINITION = "private_field_definition"
_CLASS_HERITAGE = "class_heritage"
_EXTENDS_CLAUSE = "extends_clause"
_IMPLEMENTS_CLAUSE = "implements_clause"
_DECORATOR = "decorator"
_AMBIGUOUS_NAME = "ambiguous_name"
_NAMED_IMPORTS = "named_imports"
_IMPORT_SPECIFIER = "import_specifier"
_NAMESPACE_IMPORT = "namespace_import"
_IMPORT = "import"
_IMPORT_CLAUSE = "import_clause"
_STRING_FRAGMENT = "string_fragment"
_INTERFACE_DECLARATION = "interface_declaration"
_ENUM_DECLARATION = "enum_declaration"
_TYPE_ALIAS_DECLARATION = "type_alias_declaration"


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class TypeScriptExtractor(LanguageExtractor):
    """Structural extractor for TypeScript and JavaScript.

    Handles the full TS/JS family: ``.ts``, ``.tsx``, ``.js``, ``.jsx``,
    ``.mjs``, ``.cjs``, ``.mts``, ``.cts``.
    """

    @property
    def language_ids(self) -> list[str]:
        return ["typescript", "tsx", "javascript"]

    # ------------------------------------------------------------------
    # Structure extraction
    # ------------------------------------------------------------------

    def extract_structure(self, root_node: Node) -> StructuralAnalysis:
        """Extract all structural information from a TS/JS AST.

        Processes the file in a single AST walk to minimise overhead.
        """
        analysis = StructuralAnalysis()
        self._walk_program(root_node, analysis)
        return analysis

    def _walk_program(self, root_node: Node, analysis: StructuralAnalysis) -> None:
        """Walk the program node and dispatch each top-level statement."""

        def visitor(node: Node) -> None:
            node_type = node.type

            if node_type == _FUNCTION_DECLARATION:
                analysis.functions.append(self._extract_function(node))

            elif node_type == _GENERATOR_FUNCTION_DECLARATION:
                analysis.functions.append(
                    self._extract_function(node, is_generator=True)
                )

            elif node_type in (_CLASS_DECLARATION, _ABSTRACT_CLASS_DECLARATION):
                analysis.classes.append(self._extract_class(node))

            elif node_type == _INTERFACE_DECLARATION:
                analysis.interfaces.append(self._extract_interface(node))

            elif node_type == _ENUM_DECLARATION:
                analysis.enums.append(self._extract_enum(node))

            elif node_type == _TYPE_ALIAS_DECLARATION:
                analysis.type_aliases.append(self._extract_type_alias(node))

            elif node_type == _IMPORT_STATEMENT:
                analysis.imports.append(self._extract_import(node))

            elif node_type == _EXPORT_STATEMENT:
                analysis.exports.extend(self._extract_exports(node))

            elif node_type == _LEXICAL_DECLARATION:
                self._extract_lexical_functions(node, analysis)
                self._extract_lexical_exports(node, analysis)
                self._extract_lexical_variables(node, analysis)

            elif node_type == _VARIABLE_DECLARATION:
                self._extract_lexical_functions(node, analysis)
                self._extract_variable_exports(node, analysis)
                self._extract_lexical_variables(node, analysis)

        traverse(root_node, visitor)

    # ------------------------------------------------------------------
    # Function extraction
    # ------------------------------------------------------------------

    def _extract_function(
        self, node: Node, is_generator: bool = False
    ) -> FunctionInfo:
        """Extract function info from a function_declaration node."""
        name_node = find_child(node, _IDENTIFIER)
        name = get_node_text(name_node) if name_node else "<anonymous>"
        params = self._extract_parameters(node)
        return_type = self._extract_return_type(node)
        line_range = (node.start_point[0] + 1, node.end_point[0] + 1)

        return FunctionInfo(
            name=name,
            line_range=line_range,
            params=params,
            return_type=return_type,
        )

    def _extract_parameters(self, node: Node) -> list[str]:
        """Extract parameter names from a function declaration."""
        params_node = find_child(node, _FORMAL_PARAMETERS)
        if params_node is None:
            return []

        param_names: list[str] = []
        for child in params_node.children:
            if child.type in (_REQUIRED_PARAMETER, _OPTIONAL_PARAMETER):
                # The first named child is usually the identifier or pattern
                for sub in child.children:
                    if sub.type == _IDENTIFIER:
                        param_names.append(get_node_text(sub))
                        break
                    # Destructured parameter: { a, b }
                    if sub.type == "object_pattern":
                        param_names.extend(
                            get_node_text(ident)
                            for ident in collect_nodes_of_type(sub, _IDENTIFIER)
                        )
                        break
                    if sub.type == "array_pattern":
                        param_names.extend(
                            get_node_text(ident)
                            for ident in collect_nodes_of_type(sub, _IDENTIFIER)
                        )
                        break
        return param_names

    def _extract_return_type(self, node: Node) -> str | None:
        """Extract the return type annotation from a function."""
        type_node = find_child(node, _TYPE_ANNOTATION)
        if type_node is None:
            return None
        return get_node_text(type_node).removeprefix(": ").strip()

    # ------------------------------------------------------------------
    # Class extraction
    # ------------------------------------------------------------------

    def _extract_class(self, node: Node) -> ClassInfo:
        """Extract class info from a class_declaration node."""
        name_node = find_child(node, _IDENTIFIER)
        # For abstract classes, the identifier might be nested deeper
        if name_node is None:
            name_node = find_child(node, "type_identifier")
        name = get_node_text(name_node) if name_node else "<anonymous>"
        line_range = (node.start_point[0] + 1, node.end_point[0] + 1)

        method_details: list[MethodInfo] = []
        properties: list[str] = []

        # Extract class body
        body_node = find_child(node, "class_body")
        if body_node is not None:
            for child in body_node.children:
                if child.type == _METHOD_DEFINITION:
                    mn = find_child(child, _PROPERTY_IDENTIFIER)
                    if mn:
                        m_name = get_node_text(mn)
                        m_params = self._extract_parameters(child)
                        m_ret = self._extract_return_type(child)
                        method_details.append(
                            MethodInfo(
                                name=m_name,
                                line_range=(
                                    child.start_point[0] + 1,
                                    child.end_point[0] + 1,
                                ),
                                params=m_params,
                                return_type=m_ret,
                            )
                        )
                elif child.type in (
                    _PUBLIC_FIELD_DEFINITION,
                    _PRIVATE_FIELD_DEFINITION,
                ):
                    prop_name = find_child(child, _PROPERTY_IDENTIFIER)
                    if prop_name:
                        properties.append(get_node_text(prop_name))
                elif child.type == _DECORATOR:
                    # Decorated methods
                    for sibling in body_node.children:
                        if sibling.type == _METHOD_DEFINITION:
                            mn = find_child(sibling, _PROPERTY_IDENTIFIER)
                            if mn:
                                m_name = get_node_text(mn)
                                m_params = self._extract_parameters(sibling)
                                m_ret = self._extract_return_type(sibling)
                                method_details.append(
                                    MethodInfo(
                                        name=m_name,
                                        line_range=(
                                            sibling.start_point[0] + 1,
                                            sibling.end_point[0] + 1,
                                        ),
                                        params=m_params,
                                        return_type=m_ret,
                                    )
                                )

        # Detect inheritance
        inheritance = self._extract_class_heritage(node)

        return ClassInfo(
            name=name,
            line_range=line_range,
            methods=[m.name for m in method_details],
            properties=properties,
            inheritance=inheritance,
            method_details=method_details,
        )

    @staticmethod
    def _extract_class_heritage(node: Node) -> InheritanceInfo | None:
        """Extract extends/implements from a class_declaration."""
        heritage = find_child(node, _CLASS_HERITAGE)
        if heritage is None:
            return None

        extends: list[str] = []
        implements: list[str] = []

        extends_clause = find_child(heritage, _EXTENDS_CLAUSE)
        if extends_clause is not None:
            extends.extend(
                get_node_text(n)
                for n in collect_nodes_of_type(extends_clause, _IDENTIFIER)
            )
            extends.extend(
                get_node_text(t)
                for t in collect_nodes_of_type(extends_clause, "type_identifier")
            )

        implements_clause = find_child(heritage, _IMPLEMENTS_CLAUSE)
        if implements_clause is not None:
            implements.extend(
                get_node_text(n)
                for n in collect_nodes_of_type(implements_clause, _IDENTIFIER)
            )
            implements.extend(
                get_node_text(t)
                for t in collect_nodes_of_type(implements_clause, "type_identifier")
            )

        if extends or implements:
            return InheritanceInfo(extends=extends, implements=implements)
        return None

    def _extract_interface(self, node: Node) -> InterfaceInfo:
        """Extract interface info from an interface_declaration node."""
        name_node = find_child(node, _IDENTIFIER)
        if name_node is None:
            name_node = find_child(node, "type_identifier")
        name = get_node_text(name_node) if name_node else "<anonymous>"
        line_range = (node.start_point[0] + 1, node.end_point[0] + 1)

        iface_methods: list[MethodInfo] = []
        properties: list[str] = []

        body_node = find_child(node, "object_type") or find_child(
            node, "interface_body"
        )
        if body_node is not None:
            for child in body_node.children:
                if child.type in (_METHOD_DEFINITION, "method_signature"):
                    mn = find_child(child, _PROPERTY_IDENTIFIER)
                    if mn:
                        m_name = get_node_text(mn)
                        m_params = self._extract_parameters(child)
                        m_ret = self._extract_return_type(child)
                        iface_methods.append(
                            MethodInfo(
                                name=m_name,
                                line_range=(
                                    child.start_point[0] + 1,
                                    child.end_point[0] + 1,
                                ),
                                params=m_params,
                                return_type=m_ret,
                            )
                        )
                elif child.type in (
                    _PUBLIC_FIELD_DEFINITION,
                    "property_signature",
                ):
                    prop_name = find_child(child, _PROPERTY_IDENTIFIER)
                    if prop_name:
                        properties.append(get_node_text(prop_name))

        # Interface extends clauses
        extends: list[str] = []
        extends_clause = find_child(node, _EXTENDS_CLAUSE)
        if extends_clause is not None:
            extends.extend(
                get_node_text(n)
                for n in collect_nodes_of_type(extends_clause, _IDENTIFIER)
            )
            extends.extend(
                get_node_text(t)
                for t in collect_nodes_of_type(extends_clause, "type_identifier")
            )

        return InterfaceInfo(
            name=name,
            line_range=line_range,
            methods=iface_methods,
            properties=properties,
            extends=extends,
        )

    def _extract_enum(self, node: Node) -> EnumInfo:
        """Extract enum info from an enum_declaration node."""
        name_node = find_child(node, _IDENTIFIER)
        if name_node is None:
            name_node = find_child(node, "type_identifier")
        name = get_node_text(name_node) if name_node else "<anonymous>"
        line_range = (node.start_point[0] + 1, node.end_point[0] + 1)

        values: list[str] = []
        body_node = find_child(node, "enum_body")
        if body_node is not None:
            for child in body_node.children:
                if child.type in (_PROPERTY_IDENTIFIER, "enum_member"):
                    member_name = find_child(child, _PROPERTY_IDENTIFIER)
                    if member_name:
                        values.append(get_node_text(member_name))
                    else:
                        ident = find_child(child, _IDENTIFIER)
                        if ident:
                            values.append(get_node_text(ident))

        return EnumInfo(
            name=name,
            line_range=line_range,
            values=values,
        )

    def _extract_type_alias(self, node: Node) -> TypeAliasInfo:
        """Extract type alias info from a type_alias_declaration node."""
        name_node = find_child(node, _IDENTIFIER)
        if name_node is None:
            name_node = find_child(node, "type_identifier")
        name = get_node_text(name_node) if name_node else "<anonymous>"
        line_range = (node.start_point[0] + 1, node.end_point[0] + 1)

        target_type = ""
        type_node = find_child(node, "type_annotation")
        if type_node is not None:
            target_type = get_node_text(type_node)
        else:
            # Get the type parameter (the right-hand side of `type X = ...`)
            for child in reversed(node.children):
                if child.is_named and child.type != _IDENTIFIER:
                    target_type = get_node_text(child)
                    break

        return TypeAliasInfo(
            name=name,
            line_range=line_range,
            target_type=target_type,
        )

    def _extract_lexical_variables(
        self, node: Node, analysis: StructuralAnalysis
    ) -> None:
        """Extract top-level const/let/var declarations as VariableInfo.

        Skips declarations that are arrow functions (handled by
        _extract_lexical_functions) and declarations that are exports
        (handled by _extract_lexical_exports).
        """
        parent = node.parent
        if parent is not None and parent.type == _EXPORT_STATEMENT:
            return  # already handled as export

        for decl in find_children(node, "variable_declarator"):
            name_node = find_child(decl, _IDENTIFIER)
            if name_node is None:
                continue

            # Skip arrow functions
            if find_child(decl, _ARROW_FUNCTION) is not None:
                continue

            name = get_node_text(name_node)
            if name.startswith("_"):
                continue

            type_annot = ""
            type_node = find_child(decl, _TYPE_ANNOTATION)
            if type_node is not None:
                type_annot = get_node_text(type_node).removeprefix(": ").strip()

            is_const = (
                find_child(node, "const") is not None
                if hasattr(node, "text")
                else False
            )

            analysis.variables.append(
                VariableInfo(
                    name=name,
                    line_range=(
                        decl.start_point[0] + 1,
                        decl.end_point[0] + 1,
                    ),
                    type_annotation=type_annot or None,
                    is_const=is_const,
                )
            )

    # ------------------------------------------------------------------
    # Import extraction
    # ------------------------------------------------------------------

    def _extract_import(self, node: Node) -> ImportInfo:
        """Extract import info from an import_statement node."""
        line_number = node.start_point[0] + 1

        # Extract source module path
        source_path = ""
        source_node = find_child(node, _STRING)
        if source_node is not None:
            source_path = get_string_value(source_node)

        # Extract import specifiers
        specifiers: list[str] = []

        import_clause = find_child(node, _IMPORT_CLAUSE)
        if import_clause is not None:
            # Default import: import Foo from 'bar'
            ident = find_child(import_clause, _IDENTIFIER)
            if ident:
                specifiers.append(get_node_text(ident))

            # Named imports: import { a, b } from 'bar'
            named = find_child(import_clause, _NAMED_IMPORTS)
            if named is not None:
                for spec in find_children(named, _IMPORT_SPECIFIER):
                    name_node = find_child(spec, _IDENTIFIER)
                    if name_node is None:
                        name_node = find_child(spec, _PROPERTY_IDENTIFIER)
                    if name_node:
                        specifiers.append(get_node_text(name_node))

            # Namespace import: import * as Foo from 'bar'
            ns = find_child(import_clause, _NAMESPACE_IMPORT)
            if ns is not None:
                ns_ident = find_child(ns, _IDENTIFIER)
                if ns_ident:
                    specifiers.append(f"* as {get_node_text(ns_ident)}")

        # Side-effect import: import 'foo'
        if not specifiers:
            import_kw = find_child(node, _IMPORT)
            if import_kw:
                specifiers.append(source_path or "(side-effect)")

        return ImportInfo(
            source=source_path,
            specifiers=specifiers,
            line_number=line_number,
        )

    # ------------------------------------------------------------------
    # Export extraction
    # ------------------------------------------------------------------

    def _extract_exports(self, node: Node) -> list[ExportInfo]:
        """Extract export info from an export_statement node."""
        exports: list[ExportInfo] = []
        line_number = node.start_point[0] + 1

        # Check for "export default"
        is_default = any(
            child.type == "default" for child in node.children
        )

        # Check for export clause: export { a, b }
        export_clause = find_child(node, _EXPORT_CLAUSE)
        if export_clause is not None:
            for spec in find_children(export_clause, _IMPORT_SPECIFIER):
                name_node = find_child(spec, _IDENTIFIER)
                if name_node is None:
                    name_node = find_child(spec, _PROPERTY_IDENTIFIER)
                if name_node:
                    exports.append(
                        ExportInfo(
                            name=get_node_text(name_node),
                            line_number=line_number,
                            is_default=False,
                        )
                    )
            return exports

        # export const/let/var/function/class X
        for child in node.children:
            if child.type in (_FUNCTION_DECLARATION, _CLASS_DECLARATION):
                name_node = find_child(child, _IDENTIFIER)
                if name_node:
                    exports.append(
                        ExportInfo(
                            name=get_node_text(name_node),
                            line_number=line_number,
                            is_default=is_default,
                        )
                    )
            elif child.type in (_LEXICAL_DECLARATION, _VARIABLE_DECLARATION):
                for decl in find_children(child, "variable_declarator"):
                    decl_name = find_child(decl, _IDENTIFIER)
                    if decl_name is None:
                        decl_name = find_child(decl, _PROPERTY_IDENTIFIER)
                    if decl_name:
                        exports.append(
                            ExportInfo(
                                name=get_node_text(decl_name),
                                line_number=line_number,
                                is_default=is_default,
                            )
                        )
            elif child.type == _IDENTIFIER:
                # export default <identifier>
                if is_default:
                    exports.append(
                        ExportInfo(
                            name=get_node_text(child),
                            line_number=line_number,
                            is_default=True,
                        )
                    )

        # If default export with no named identifier found (e.g. anonymous
        # class/function), add a placeholder
        if is_default and not exports:
            exports.append(
                ExportInfo(
                    name="default",
                    line_number=line_number,
                    is_default=True,
                )
            )

        return exports

    def _extract_lexical_exports(
        self, node: Node, analysis: StructuralAnalysis
    ) -> None:
        """Handle const/let exported via a parent export_statement.

        Only adds to exports if the parent is an export_statement.
        """
        parent = node.parent
        if parent is not None and parent.type == _EXPORT_STATEMENT:
            for decl in find_children(node, "variable_declarator"):
                name_node = find_child(decl, _IDENTIFIER)
                if name_node:
                    analysis.exports.append(
                        ExportInfo(
                            name=get_node_text(name_node),
                            line_number=parent.start_point[0] + 1,
                            is_default=False,
                        )
                    )

    def _extract_lexical_functions(
        self, node: Node, analysis: StructuralAnalysis
    ) -> None:
        """Extract named arrow functions assigned to variables.

        This keeps call-graph callers such as ``handler`` addressable as
        ``function:{file}:handler`` nodes in the graph.
        """
        for decl in find_children(node, "variable_declarator"):
            name_node = find_child(decl, _IDENTIFIER)
            arrow_node = find_child(decl, _ARROW_FUNCTION)
            if name_node is None or arrow_node is None:
                continue

            name = get_node_text(name_node)
            if any(fn.name == name for fn in analysis.functions):
                continue

            analysis.functions.append(
                FunctionInfo(
                    name=name,
                    line_range=(
                        arrow_node.start_point[0] + 1,
                        arrow_node.end_point[0] + 1,
                    ),
                    params=self._extract_parameters(arrow_node),
                    return_type=self._extract_return_type(arrow_node),
                )
            )

    def _extract_variable_exports(
        self, node: Node, analysis: StructuralAnalysis
    ) -> None:
        """Same as _extract_lexical_exports but for 'var' declarations."""
        self._extract_lexical_exports(node, analysis)

    # ------------------------------------------------------------------
    # Call graph extraction
    # ------------------------------------------------------------------

    def extract_call_graph(self, root_node: Node) -> list[CallGraphEntry]:
        """Extract caller → callee relationships from TS/JS source.

        Walks all function/method bodies and records every call expression.
        """
        entries: list[CallGraphEntry] = []

        # Collect all function-like nodes
        func_nodes: list[Node] = []
        func_nodes.extend(collect_nodes_of_type(root_node, _FUNCTION_DECLARATION))
        func_nodes.extend(
            collect_nodes_of_type(root_node, _GENERATOR_FUNCTION_DECLARATION)
        )
        func_nodes.extend(collect_nodes_of_type(root_node, _METHOD_DEFINITION))
        func_nodes.extend(collect_nodes_of_type(root_node, _ARROW_FUNCTION))

        for func_node in func_nodes:
            # Determine the caller name
            caller = self._resolve_function_name(func_node)

            # Find all call expressions within this function's scope
            # (excluding nested function bodies)
            calls = self._collect_calls_in_scope(func_node)
            for callee, line_number in calls:
                entries.append(
                    CallGraphEntry(
                        caller=caller,
                        callee=callee,
                        line_number=line_number,
                    )
                )

        return entries

    def _resolve_function_name(self, node: Node) -> str:
        """Resolve a human-readable name for a function-like node."""
        # Function declaration: function foo() {}
        if node.type in (_FUNCTION_DECLARATION, _GENERATOR_FUNCTION_DECLARATION):
            name_node = find_child(node, _IDENTIFIER)
            if name_node:
                return get_node_text(name_node)

        # Method definition: method() {}
        if node.type == _METHOD_DEFINITION:
            name_node = find_child(node, _PROPERTY_IDENTIFIER)
            if name_node:
                return get_node_text(name_node)

        # Arrow function assigned to a variable
        if node.type == _ARROW_FUNCTION:
            parent = node.parent
            if parent is not None:
                if parent.type == "variable_declarator":
                    vname = find_child(parent, _IDENTIFIER)
                    if vname:
                        return get_node_text(vname)
                if parent.type == "assignment_expression":
                    left = find_child(parent, _IDENTIFIER)
                    if left:
                        return get_node_text(left)

        return "<anonymous>"

    def _collect_calls_in_scope(
        self, func_node: Node
    ) -> list[tuple[str, int]]:
        """Collect all call expressions within *func_node* scope.

        Returns a list of ``(callee_name, line_number)`` tuples.
        """
        calls: list[tuple[str, int]] = []
        body_node = find_child(func_node, _STATEMENT_BLOCK)
        search_root = body_node if body_node is not None else func_node

        call_nodes = collect_nodes_of_type(search_root, _CALL_EXPRESSION)

        for call in call_nodes:
            callee = self._resolve_call_target(call)
            line_number = call.start_point[0] + 1
            calls.append((callee, line_number))

        return calls

    def _resolve_call_target(self, call_node: Node) -> str:
        """Resolve the target name from a call_expression node."""
        # Direct call: foo()
        ident = find_child(call_node, _IDENTIFIER)
        if ident is not None:
            return get_node_text(ident)

        # Member call: obj.method() or this.method()
        member = find_child(call_node, _MEMBER_EXPRESSION)
        if member is not None:
            prop = find_child(member, _PROPERTY_IDENTIFIER)
            if prop is not None:
                obj_ident = find_child(member, _IDENTIFIER)
                if obj_ident is not None:
                    return f"{get_node_text(obj_ident)}.{get_node_text(prop)}"
                return get_node_text(prop)

        # super() call
        super_kw = find_child(call_node, "super")
        if super_kw is not None:
            return "super"

        return "<unknown>"
