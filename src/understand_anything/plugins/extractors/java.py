"""Java language extractor.

Python port of the TypeScript ``JavaExtractor`` — extracts classes, interfaces,
methods, constructors, fields, imports, visibility-based exports, and call-graph
edges from Java source code via tree-sitter.

Handles:
  - Classes (class_declaration) with methods, properties, constructors
  - Interfaces (interface_declaration) with method signatures and constants
  - Imports (import_declaration) — regular and wildcard (``*``)
  - Exports determined by ``public`` modifier on classes, methods,
    constructors, and fields
  - Call graph extraction from method_invocation and object_creation_expression
    nodes
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
    EnumInfo,
    ExportInfo,
    FunctionInfo,
    ImportInfo,
    InheritanceInfo,
    InterfaceInfo,
    MethodInfo,
    StructuralAnalysis,
)

if TYPE_CHECKING:
    from tree_sitter import Node


# ---------------------------------------------------------------------------
# Node type constants (tree-sitter-java grammar)
# ---------------------------------------------------------------------------

_IMPORT_DECLARATION = "import_declaration"
_CLASS_DECLARATION = "class_declaration"
_INTERFACE_DECLARATION = "interface_declaration"
_METHOD_DECLARATION = "method_declaration"
_CONSTRUCTOR_DECLARATION = "constructor_declaration"
_FIELD_DECLARATION = "field_declaration"
_METHOD_INVOCATION = "method_invocation"
_OBJECT_CREATION_EXPRESSION = "object_creation_expression"
_MODIFIERS = "modifiers"
_FORMAL_PARAMETERS = "formal_parameters"
_FORMAL_PARAMETER = "formal_parameter"
_SPREAD_PARAMETER = "spread_parameter"
_SCOPED_IDENTIFIER = "scoped_identifier"
_ASTERISK = "asterisk"
_CONSTANT_DECLARATION = "constant_declaration"
_VARIABLE_DECLARATOR = "variable_declarator"
_IDENTIFIER = "identifier"
_CLASS_BODY = "class_body"
_INTERFACE_BODY = "interface_body"
_ENUM_DECLARATION = "enum_declaration"
_ENUM_BODY = "enum_body"
_ENUM_CONSTANT = "enum_constant"
_SUPERCLASS = "superclass"
_SUPER_INTERFACES = "super_interfaces"
_TYPE_LIST = "type_list"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _has_modifier(node: Node, modifier: str) -> bool:
    """Check if *node* has a ``modifiers`` child containing *modifier*."""
    modifiers = find_child(node, _MODIFIERS)
    if modifiers is None:
        return False
    return any(get_node_text(child) == modifier for child in modifiers.children)


def _extract_params(params_node: Node | None) -> list[str]:
    """Extract parameter names from a ``formal_parameters`` node.

    Handles both ``formal_parameter`` and ``spread_parameter`` (varargs).
    """
    if params_node is None:
        return []
    params: list[str] = []

    for decl in find_children(params_node, _FORMAL_PARAMETER):
        name_node = decl.child_by_field_name("name")
        if name_node is not None:
            params.append(get_node_text(name_node))

    for spread in find_children(params_node, _SPREAD_PARAMETER):
        name_node = spread.child_by_field_name("name")
        if name_node is not None:
            params.append(get_node_text(name_node))

    return params


def _extract_return_type(node: Node) -> str | None:
    """Extract the return type text from a method_declaration node."""
    type_node = node.child_by_field_name("type")
    if type_node is None:
        return None
    return get_node_text(type_node)


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class JavaExtractor(LanguageExtractor):
    """Structural extractor for Java.

    Handles classes, interfaces, methods, constructors, fields, imports,
    visibility-based exports, and call graphs for Java source code.
    """

    @property
    def language_ids(self) -> list[str]:
        return ["java"]

    # ------------------------------------------------------------------
    # Structure extraction
    # ------------------------------------------------------------------

    def extract_structure(self, root_node: Node) -> StructuralAnalysis:
        functions: list[FunctionInfo] = []
        classes: list[ClassInfo] = []
        imports: list[ImportInfo] = []
        exports: list[ExportInfo] = []
        enums: list[EnumInfo] = []
        interfaces: list[InterfaceInfo] = []

        for node in root_node.children:
            if node.type == _IMPORT_DECLARATION:
                self._extract_import(node, imports)
            elif node.type == _CLASS_DECLARATION:
                self._extract_class(node, functions, classes, exports)
            elif node.type == _INTERFACE_DECLARATION:
                self._extract_interface(node, functions, interfaces, exports)
            elif node.type == _ENUM_DECLARATION:
                self._extract_enum_def(node, enums, exports)

        return StructuralAnalysis(
            functions=functions,
            classes=classes,
            imports=imports,
            exports=exports,
            enums=enums,
            interfaces=interfaces,
        )

    # ------------------------------------------------------------------
    # Internal: enum extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_enum_def(
        node: Node,
        enums: list[EnumInfo],
        exports: list[ExportInfo],
    ) -> None:
        """Extract an enum_declaration into the enums list."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        enum_name = get_node_text(name_node)
        values: list[str] = []
        method_list: list[MethodInfo] = []

        body = node.child_by_field_name("body")
        if body is not None:
            for child in body.children:
                if child.type == _ENUM_CONSTANT:
                    const_name = find_child(child, _IDENTIFIER)
                    if const_name:
                        values.append(get_node_text(const_name))
                elif child.type == _METHOD_DECLARATION:
                    meth_name_node = child.child_by_field_name("name")
                    if meth_name_node:
                        m_name = get_node_text(meth_name_node)
                        params_node = child.child_by_field_name("parameters")
                        method_list.append(
                            MethodInfo(
                                name=m_name,
                                line_range=(
                                    child.start_point[0] + 1,
                                    child.end_point[0] + 1,
                                ),
                                params=_extract_params(params_node),
                                return_type=_extract_return_type(child),
                            )
                        )

        enums.append(
            EnumInfo(
                name=enum_name,
                line_range=(
                    node.start_point[0] + 1,
                    node.end_point[0] + 1,
                ),
                values=values,
                methods=method_list,
            )
        )

        if _has_modifier(node, "public"):
            exports.append(
                ExportInfo(
                    name=enum_name,
                    line_number=node.start_point[0] + 1,
                )
            )

    # ------------------------------------------------------------------
    # Call graph extraction
    # ------------------------------------------------------------------

    def extract_call_graph(self, root_node: Node) -> list[CallGraphEntry]:
        """从 AST 中提取调用图（迭代遍历，避免深层嵌套栈溢出）."""
        entries: list[CallGraphEntry] = []
        function_stack: list[str] = []

        # 显式栈：Node 表示待处理的节点，str 表示弹出 function_stack 的哨兵
        stack: list[Node | str] = [root_node]

        while stack:
            item = stack.pop()

            if isinstance(item, str):
                # 哨兵：离开函数作用域
                function_stack.pop()
                continue

            node = item
            pushed = False

            # Track entering method/constructor declarations
            if node.type in (_METHOD_DECLARATION, _CONSTRUCTOR_DECLARATION):
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    function_stack.append(get_node_text(name_node))
                    pushed = True

            # Extract method invocations: e.g. fetchFromDb(limit), System.out.println(msg)
            if node.type == _METHOD_INVOCATION and function_stack:
                callee = self._extract_method_invocation_name(node)
                if callee:
                    entries.append(
                        CallGraphEntry(
                            caller=function_stack[-1],
                            callee=callee,
                            line_number=node.start_point[0] + 1,
                        )
                    )

            # Extract object creation: e.g. new Foo()
            if node.type == _OBJECT_CREATION_EXPRESSION and function_stack:
                type_node = node.child_by_field_name("type")
                if type_node is not None:
                    entries.append(
                        CallGraphEntry(
                            caller=function_stack[-1],
                            callee=f"new {get_node_text(type_node)}",
                            line_number=node.start_point[0] + 1,
                        )
                    )

            # 先压入哨兵（在此节点的所有子节点处理完后弹出 function_stack）
            if pushed:
                stack.append("__FUNC_END__")

            # 子节点逆序入栈
            stack.extend(reversed(node.children))

        return entries

    # ------------------------------------------------------------------
    # Internal: method invocation name
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_method_invocation_name(node: Node) -> str | None:
        """Extract the callee name from a method_invocation node.

        Handles:
        - Plain method call: ``fetchFromDb(limit)`` → ``"fetchFromDb"``
        - Qualified call: ``System.out.println(msg)`` → ``"System.out.println"``
        """
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None

        object_node = node.child_by_field_name("object")
        if object_node is not None:
            return f"{get_node_text(object_node)}.{get_node_text(name_node)}"

        return get_node_text(name_node)

    # ------------------------------------------------------------------
    # Internal: import extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_import(
        node: Node, imports: list[ImportInfo]
    ) -> None:
        """Extract an import_declaration into the imports list.

        Handles both regular imports (``import java.util.List;``) and wildcard
        imports (``import java.util.*;``).
        """
        has_asterisk = find_child(node, _ASTERISK) is not None

        scoped_id = find_child(node, _SCOPED_IDENTIFIER)
        if scoped_id is None:
            return

        full_path = get_node_text(scoped_id)

        if has_asterisk:
            imports.append(
                ImportInfo(
                    source=full_path,
                    specifiers=["*"],
                    line_number=node.start_point[0] + 1,
                )
            )
        else:
            specifier = full_path.split(".")[-1]
            imports.append(
                ImportInfo(
                    source=full_path,
                    specifiers=[specifier],
                    line_number=node.start_point[0] + 1,
                )
            )

    # ------------------------------------------------------------------
    # Internal: class extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_class(
        node: Node,
        functions: list[FunctionInfo],
        classes: list[ClassInfo],
        exports: list[ExportInfo],
    ) -> None:
        """Extract a class_declaration into the classes array."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        method_details: list[MethodInfo] = []
        properties: list[str] = []

        body = node.child_by_field_name("body")
        if body is not None:
            _extract_class_body_members(
                body, method_details, properties, functions, exports
            )

        # Detect inheritance
        inheritance = _extract_java_inheritance(node)

        classes.append(
            ClassInfo(
                name=get_node_text(name_node),
                line_range=(
                    node.start_point[0] + 1,
                    node.end_point[0] + 1,
                ),
                methods=[m.name for m in method_details],
                properties=properties,
                inheritance=inheritance,
                method_details=method_details,
            )
        )

        if _has_modifier(node, "public"):
            exports.append(
                ExportInfo(
                    name=get_node_text(name_node),
                    line_number=node.start_point[0] + 1,
                )
            )

    # ------------------------------------------------------------------
    # Internal: interface extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_interface(
        node: Node,
        functions: list[FunctionInfo],
        interfaces: list[InterfaceInfo],
        exports: list[ExportInfo],
    ) -> None:
        """Extract an interface_declaration into the interfaces list."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return

        method_details: list[MethodInfo] = []
        properties: list[str] = []

        body = node.child_by_field_name("body")
        if body is not None:
            # Interface body contains method_declaration nodes (signatures)
            for method_node in find_children(body, _METHOD_DECLARATION):
                meth_name_node = method_node.child_by_field_name("name")
                if meth_name_node is not None:
                    m_name = get_node_text(meth_name_node)
                    params_node = method_node.child_by_field_name("parameters")
                    params = _extract_params(params_node)
                    return_type = _extract_return_type(method_node)
                    method_details.append(
                        MethodInfo(
                            name=m_name,
                            line_range=(
                                method_node.start_point[0] + 1,
                                method_node.end_point[0] + 1,
                            ),
                            params=params,
                            return_type=return_type,
                        )
                    )

            # Interface can also contain constant_declaration (fields)
            for field in find_children(body, _CONSTANT_DECLARATION):
                for decl in find_children(field, _VARIABLE_DECLARATOR):
                    decl_name = decl.child_by_field_name("name")
                    if decl_name is not None:
                        properties.append(get_node_text(decl_name))

        # Detect super interfaces
        extends: list[str] = _extract_java_super_interfaces(node)

        interfaces.append(
            InterfaceInfo(
                name=get_node_text(name_node),
                line_range=(
                    node.start_point[0] + 1,
                    node.end_point[0] + 1,
                ),
                methods=method_details,
                properties=properties,
                extends=extends,
            )
        )

        if _has_modifier(node, "public"):
            exports.append(
                ExportInfo(
                    name=get_node_text(name_node),
                    line_number=node.start_point[0] + 1,
                )
            )


# ---------------------------------------------------------------------------
# Internal: class body member extraction
# ---------------------------------------------------------------------------


def _extract_class_body_members(
    body: Node,
    method_details: list[MethodInfo],
    properties: list[str],
    functions: list[FunctionInfo],
    exports: list[ExportInfo],
) -> None:
    """Extract methods, constructors, and fields from a class_body node."""
    for child in body.children:
        if child.type == _METHOD_DECLARATION:
            _extract_method(child, method_details, functions, exports)
        elif child.type == _CONSTRUCTOR_DECLARATION:
            _extract_constructor(child, method_details, functions, exports)
        elif child.type == _FIELD_DECLARATION:
            _extract_field(child, properties, exports)


def _extract_method(
    node: Node,
    method_details: list[MethodInfo],
    functions: list[FunctionInfo],
    exports: list[ExportInfo],
) -> None:
    """Extract a method_declaration into methods and functions lists."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return

    name = get_node_text(name_node)
    params_node = node.child_by_field_name("parameters")
    params = _extract_params(params_node)
    return_type = _extract_return_type(node)

    is_static = _has_modifier(node, "static")
    if _has_modifier(node, "private"):
        visibility = "private"
    elif _has_modifier(node, "protected"):
        visibility = "protected"
    else:
        visibility = "public"

    method_details.append(
        MethodInfo(
            name=name,
            line_range=(
                node.start_point[0] + 1,
                node.end_point[0] + 1,
            ),
            params=params,
            return_type=return_type,
            is_static=is_static,
            visibility=visibility,
        )
    )

    functions.append(
        FunctionInfo(
            name=name,
            line_range=(
                node.start_point[0] + 1,
                node.end_point[0] + 1,
            ),
            params=params,
            return_type=return_type,
        )
    )

    if _has_modifier(node, "public"):
        exports.append(
            ExportInfo(
                name=name,
                line_number=node.start_point[0] + 1,
            )
        )


def _extract_constructor(
    node: Node,
    method_details: list[MethodInfo],
    functions: list[FunctionInfo],
    exports: list[ExportInfo],
) -> None:
    """Extract a constructor_declaration into methods and functions lists."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return

    name = get_node_text(name_node)
    params_node = node.child_by_field_name("parameters")
    params = _extract_params(params_node)

    method_details.append(
        MethodInfo(
            name=name,
            line_range=(
                node.start_point[0] + 1,
                node.end_point[0] + 1,
            ),
            params=params,
            is_constructor=True,
        )
    )

    functions.append(
        FunctionInfo(
            name=name,
            line_range=(
                node.start_point[0] + 1,
                node.end_point[0] + 1,
            ),
            params=params,
            # Constructors have no return type
        )
    )

    if _has_modifier(node, "public"):
        exports.append(
            ExportInfo(
                name=name,
                line_number=node.start_point[0] + 1,
            )
        )


def _extract_field(
    node: Node,
    properties: list[str],
    exports: list[ExportInfo],
) -> None:
    """Extract a field_declaration into properties and exports lists."""
    for decl in find_children(node, _VARIABLE_DECLARATOR):
        name_node = decl.child_by_field_name("name")
        if name_node is not None:
            properties.append(get_node_text(name_node))

            if _has_modifier(node, "public"):
                exports.append(
                    ExportInfo(
                        name=get_node_text(name_node),
                        line_number=node.start_point[0] + 1,
                    )
                )


def _extract_java_inheritance(node: Node) -> InheritanceInfo | None:
    """Extract extends and implements from a Java class_declaration."""
    extends: list[str] = []
    implements: list[str] = []

    superclass = find_child(node, _SUPERCLASS)
    if superclass is not None:
        ident = find_child(superclass, _IDENTIFIER)
        if ident:
            extends.append(get_node_text(ident))
        # Could be a type_identifier or scoped_identifier
        scoped = find_child(superclass, _SCOPED_IDENTIFIER)
        if scoped:
            extends.append(get_node_text(scoped))

    super_ifaces = find_child(node, _SUPER_INTERFACES)
    if super_ifaces is not None:
        type_list = find_child(super_ifaces, _TYPE_LIST)
        if type_list is not None:
            implements.extend(
                get_node_text(n)
                for n in find_children(type_list, _IDENTIFIER)
            )
            implements.extend(
                get_node_text(s)
                for s in find_children(type_list, _SCOPED_IDENTIFIER)
            )

    if extends or implements:
        return InheritanceInfo(extends=extends, implements=implements)
    return None


def _extract_java_super_interfaces(node: Node) -> list[str]:
    """Extract super interface names from an interface_declaration."""
    result: list[str] = []
    extends_clause = find_child(node, "extends_interfaces")
    if extends_clause is not None:
        type_list = find_child(extends_clause, _TYPE_LIST)
        if type_list is not None:
            result.extend(
                get_node_text(n)
                for n in find_children(type_list, _IDENTIFIER)
            )
            result.extend(
                get_node_text(s)
                for s in find_children(type_list, _SCOPED_IDENTIFIER)
            )
    return result
