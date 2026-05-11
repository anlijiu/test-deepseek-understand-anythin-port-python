"""AST traversal helper functions for tree-sitter.

Python port of the base extractor utilities — synchronous, using native
tree-sitter bindings instead of the Node.js WASM API.

Key differences from the Node.js web-tree-sitter API:
  - ``node.text`` returns ``bytes``, needs ``.decode("utf-8")``
  - ``node.children`` is a Python list (no ``childCount`` / ``child(i)`` loops)
  - No manual memory management (Python GC handles it)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from tree_sitter import Node


def traverse(node: Node, visitor: Callable[[Node], None]) -> None:
    """Depth-first traversal of the AST, calling ``visitor`` on every node.

    Args:
        node: Root AST node to start traversal from.
        visitor: Callback invoked for each visited node.
    """
    visitor(node)
    for child in node.children:
        traverse(child, visitor)


def find_child(node: Node, type_name: str) -> Node | None:
    """Return the first direct child whose ``.type`` matches *type_name*.

    Args:
        node: Parent node to search.
        type_name: AST node type to look for (e.g. ``"identifier"``).

    Returns:
        The matching child node, or ``None`` if not found.
    """
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def find_children(node: Node, type_name: str) -> list[Node]:
    """Return all direct children whose ``.type`` matches *type_name*.

    Args:
        node: Parent node to search.
        type_name: AST node type to filter by.

    Returns:
        List of matching child nodes (may be empty).
    """
    return [child for child in node.children if child.type == type_name]


def has_child_of_type(node: Node, type_name: str) -> bool:
    """Return ``True`` if *node* has at least one direct child of *type_name*.

    Args:
        node: Parent node to check.
        type_name: AST node type to test for.

    Returns:
        ``True`` if a matching direct child exists.
    """
    return any(child.type == type_name for child in node.children)


def get_string_value(node: Node) -> str:
    """Extract the unquoted string value from a string literal node.

    Handles ``string_fragment`` children (tree-sitter 0.24+) and falls
    back to stripping quote characters from the node text.

    Args:
        node: A ``string``, ``template_string``, or similar AST node.

    Returns:
        The raw string content without surrounding quotes.
    """
    for child in node.children:
        if child.type == "string_fragment":
            child_text = child.text
            if child_text is not None:
                return child_text.decode("utf-8")
    text_bytes = node.text
    if text_bytes is not None:
        return text_bytes.decode("utf-8").strip("'\"`")
    return ""


def get_node_text(node: Node) -> str:
    """Return the decoded UTF-8 source text of *node*.

    Args:
        node: Any tree-sitter AST node.

    Returns:
        The source code text represented by this node.
    """
    text_bytes = node.text
    if text_bytes is not None:
        return text_bytes.decode("utf-8")
    return ""


def get_named_children(node: Node) -> list[Node]:
    """Return all *named* children of *node* (excluding anonymous tokens).

    Args:
        node: Any tree-sitter AST node.

    Returns:
        List of named child nodes.
    """
    return [child for child in node.children if child.is_named]


def find_first_ancestor_of_type(node: Node, type_name: str) -> Node | None:
    """Walk up the tree and return the first ancestor with type *type_name*.

    Args:
        node: Starting node.
        type_name: AST node type to look for.

    Returns:
        The matching ancestor node, or ``None`` if not found.
    """
    current = node.parent
    while current is not None:
        if current.type == type_name:
            return current
        current = current.parent
    return None


def collect_nodes_of_type(node: Node, type_name: str) -> list[Node]:
    """Collect all descendant nodes (including *node*) with type *type_name*.

    Args:
        node: Root node to search from.
        type_name: AST node type to collect.

    Returns:
        List of all matching nodes in the subtree.
    """
    result: list[Node] = []

    def _collect(n: Node) -> None:
        if n.type == type_name:
            result.append(n)

    traverse(node, _collect)
    return result
