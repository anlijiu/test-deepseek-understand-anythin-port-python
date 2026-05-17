"""框架感知解析 — 将框架检测结果转化为具体的图节点和边.

v2 plan 阶段 8: 第一批支持 FastAPI, Django, React, Spring.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understand_anything.languages.types import FrameworkConfig

# ---------------------------------------------------------------------------
# FastAPI 路由检测
# ---------------------------------------------------------------------------

# 匹配 @app.get("/path") 或 @router.post("/path/{id}")
_FASTAPI_ROUTE_RE = re.compile(
    r'@\s*(?P<app>\w+(?:\.\w+)*)\s*\.\s*(?P<method>get|post|put|delete|patch|head|options)\s*\(\s*["\'](?P<path>[^"\']+)["\']'
)

# 匹配被装饰的下一个函数定义
_FUNC_DEF_RE = re.compile(
    r"(?:async\s+)?def\s+(?P<name>\w+)\s*\([^)]*\)"
)


def extract_fastapi_endpoints(
    file_path: str, content: str
) -> list[dict]:
    """从 Python 文件中提取 FastAPI 端点.

    Args:
        file_path: 源文件路径.
        content: 文件内容.

    Returns:
        端点信息列表, 每个包含:
          - method: HTTP 方法
          - path: 路由路径
          - handler: 处理函数名
          - line_number: 行号
    """
    endpoints: list[dict] = []

    for match in _FASTAPI_ROUTE_RE.finditer(content):
        method = match.group("method").upper()
        path = match.group("path")
        line_number = content[: match.start()].count("\n") + 1

        # 找到装饰器后面的函数定义
        after_decorator = content[match.end() :]
        func_match = _FUNC_DEF_RE.search(after_decorator)
        handler = func_match.group("name") if func_match else "unknown"

        endpoints.append({
            "method": method,
            "path": path,
            "handler": handler,
            "line_number": line_number,
        })

    return endpoints


# ---------------------------------------------------------------------------
# Django URL 路由检测
# ---------------------------------------------------------------------------

_DJANGO_PATH_RE = re.compile(
    r'(?:path|re_path)\s*\(\s*["\'](?P<path>[^"\']+)["\']\s*,\s*(?P<view>\w+)'
)

_DJANGO_URLPATTERNS_RE = re.compile(r"urlpatterns\s*=\s*\[")


def extract_django_endpoints(
    file_path: str, content: str
) -> list[dict]:
    """从 Django urls.py 中提取端点.

    Args:
        file_path: 源文件路径.
        content: 文件内容.

    Returns:
        端点信息列表.
    """
    endpoints: list[dict] = []

    # 只在包含 urlpatterns 的文件中搜索
    if not _DJANGO_URLPATTERNS_RE.search(content):
        return endpoints

    for match in _DJANGO_PATH_RE.finditer(content):
        path = match.group("path")
        view = match.group("view")
        line_number = content[: match.start()].count("\n") + 1

        endpoints.append({
            "method": "GET",  # Django 默认不指定 HTTP 方法
            "path": path,
            "handler": view,
            "line_number": line_number,
        })

    return endpoints


# ---------------------------------------------------------------------------
# Spring 注解检测
# ---------------------------------------------------------------------------

_SPRING_REST_RE = re.compile(r'@(?:Get|Post|Put|Delete|Patch)Mapping\s*\(?\s*(?:value\s*=\s*)?["\'](?P<path>[^"\']*)["\']')
_SPRING_CONTROLLER_RE = re.compile(r"@RestController")


def extract_spring_endpoints(
    file_path: str, content: str
) -> list[dict]:
    """从 Java Spring 控制器中提取端点.

    Args:
        file_path: 源文件路径.
        content: 文件内容.

    Returns:
        端点信息列表.
    """
    endpoints: list[dict] = []

    if not _SPRING_CONTROLLER_RE.search(content):
        return endpoints

    for match in _SPRING_REST_RE.finditer(content):
        path = match.group("path") or "/"
        line_number = content[: match.start()].count("\n") + 1

        # 找下一个方法名
        after_annotation = content[match.end() :]
        func_match = re.search(
            r"(?:public|private|protected)?\s+(?:\w+\s+)?(?P<name>\w+)\s*\(",
            after_annotation,
        )
        handler = func_match.group("name") if func_match else "unknown"

        # 推断 HTTP 方法
        annotation = match.group(0)
        method = "GET"
        for m in ("Post", "Put", "Delete", "Patch", "Get"):
            if m in annotation:
                method = m.upper()
                break

        endpoints.append({
            "method": method,
            "path": path,
            "handler": handler,
            "line_number": line_number,
        })

    return endpoints


# ---------------------------------------------------------------------------
# React 组件检测
# ---------------------------------------------------------------------------

_REACT_COMPONENT_RE = re.compile(
    r"(?:export\s+(?:default\s+)?)?function\s+(?P<name>[A-Z]\w*)\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{"
)

_JSX_COMPONENT_USAGE_RE = re.compile(r"<\s*(?P<name>[A-Z]\w+)\s+")


def extract_react_components(
    file_path: str, content: str
) -> list[dict]:
    """从 TSX/JSX 文件中提取 React 组件.

    Args:
        file_path: 源文件路径.
        content: 文件内容.

    Returns:
        组件信息列表.
    """
    components: list[dict] = []

    for match in _REACT_COMPONENT_RE.finditer(content):
        name = match.group("name")
        # 过滤掉非组件的函数 (useState, useEffect 等 hooks)
        if name.startswith("use") or name in ("Fragment", "Suspense"):
            continue
        line_number = content[: match.start()].count("\n") + 1
        components.append({
            "name": name,
            "type": "component",
            "line_number": line_number,
        })

    return components


# ---------------------------------------------------------------------------
# 框架解析协调器
# ---------------------------------------------------------------------------


class FrameworkGraphResolver:
    """框架感知图解析器.

    对检测到的框架, 解析源代码产生具体的图节点和边.

    目前支持: FastAPI, Django, Spring, React.
    """

    def __init__(self, detected_frameworks: list[FrameworkConfig]) -> None:
        self._frameworks = detected_frameworks
        self._framework_ids = {f.id for f in detected_frameworks}

    def resolve_file(
        self, file_path: str, content: str, language_id: str
    ) -> tuple[list[dict], list[dict]]:
        """解析单个文件, 返回框架感知的节点和边.

        Args:
            file_path: 文件路径.
            content: 文件内容.
            language_id: 语言 ID.

        Returns:
            ``(nodes, edges)`` 元组, 每个为 dict 列表.
        """
        nodes: list[dict] = []
        edges: list[dict] = []

        if language_id == "python":
            self._resolve_python_frameworks(file_path, content, nodes, edges)
        elif language_id in ("typescript", "tsx", "javascript"):
            self._resolve_ts_frameworks(file_path, content, nodes, edges)
        elif language_id == "java":
            self._resolve_java_frameworks(file_path, content, nodes, edges)

        return nodes, edges

    def _resolve_python_frameworks(
        self,
        file_path: str,
        content: str,
        nodes: list[dict],
        edges: list[dict],
    ) -> None:
        """解析 Python 框架 (FastAPI, Django)."""

        if "fastapi" in self._framework_ids:
            endpoints = extract_fastapi_endpoints(file_path, content)
            for ep in endpoints:
                endpoint_id = (
                    f"endpoint:{file_path}:{ep['method']} {ep['path']}"
                )
                handler_id = f"function:{file_path}:{ep['handler']}"
                nodes.append({
                    "id": endpoint_id,
                    "type": "endpoint",
                    "name": f"{ep['method']} {ep['path']}",
                    "file_path": file_path,
                    "line_start": ep["line_number"],
                    "summary": f"FastAPI endpoint: {ep['method']} {ep['path']}",
                    "tags": ["fastapi", "endpoint"],
                    "complexity": "simple",
                })
                edges.append({
                    "source": endpoint_id,
                    "target": handler_id,
                    "type": "references",
                    "weight": 0.8,
                    "description": f"handles {ep['path']}",
                })

        if "django" in self._framework_ids:
            endpoints = extract_django_endpoints(file_path, content)
            for ep in endpoints:
                endpoint_id = (
                    f"endpoint:{file_path}:{ep['path']}"
                )
                handler_id = f"function:{file_path}:{ep['handler']}"
                nodes.append({
                    "id": endpoint_id,
                    "type": "endpoint",
                    "name": f"{ep['path']}",
                    "file_path": file_path,
                    "line_start": ep["line_number"],
                    "summary": f"Django endpoint: {ep['path']} → {ep['handler']}",
                    "tags": ["django", "endpoint"],
                    "complexity": "simple",
                })
                edges.append({
                    "source": endpoint_id,
                    "target": handler_id,
                    "type": "references",
                    "weight": 0.8,
                    "description": f"routes to {ep['handler']}",
                })

    def _resolve_ts_frameworks(
        self,
        file_path: str,
        content: str,
        nodes: list[dict],
        edges: list[dict],
    ) -> None:
        """解析 TypeScript/JS 框架 (React)."""

        if "react" in self._framework_ids:
            components = extract_react_components(file_path, content)
            for comp in components:
                comp_id = f"function:{file_path}:{comp['name']}"
                nodes.append({
                    "id": comp_id,
                    "type": "function",
                    "name": comp["name"],
                    "file_path": file_path,
                    "line_start": comp["line_number"],
                    "summary": f"React component: {comp['name']}",
                    "tags": ["react", "component"],
                    "complexity": "moderate",
                })
                edges.append({
                    "source": f"file:{file_path}",
                    "target": comp_id,
                    "type": "contains",
                    "weight": 1.0,
                })

    def _resolve_java_frameworks(
        self,
        file_path: str,
        content: str,
        nodes: list[dict],
        edges: list[dict],
    ) -> None:
        """解析 Java 框架 (Spring)."""

        if "spring" in self._framework_ids:
            endpoints = extract_spring_endpoints(file_path, content)
            for ep in endpoints:
                endpoint_id = (
                    f"endpoint:{file_path}:{ep['method']} {ep['path']}"
                )
                handler_id = f"function:{file_path}:{ep['handler']}"
                nodes.append({
                    "id": endpoint_id,
                    "type": "endpoint",
                    "name": f"{ep['method']} {ep['path']}",
                    "file_path": file_path,
                    "line_start": ep["line_number"],
                    "summary": f"Spring endpoint: {ep['method']} {ep['path']}",
                    "tags": ["spring", "endpoint"],
                    "complexity": "simple",
                })
                edges.append({
                    "source": endpoint_id,
                    "target": handler_id,
                    "type": "references",
                    "weight": 0.8,
                    "description": f"handles {ep['path']}",
                })


__all__ = [
    "FrameworkGraphResolver",
    "extract_django_endpoints",
    "extract_fastapi_endpoints",
    "extract_react_components",
    "extract_spring_endpoints",
]
