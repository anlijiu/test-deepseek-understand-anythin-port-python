"""Pipeline — 端到端知识图谱构建编排层.

将文件发现、忽略过滤、代码分析、图构建、验证、层级检测、导览生成、
指纹计算和持久化串联为一个完整的分析管道。

Usage::

    pipeline = Pipeline("/path/to/project")
    result = pipeline.run()
    print(f"Analyzed {result.analyzed_files} files")
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from understand_anything.analysis.graph_builder import GraphBuilder
from understand_anything.analysis.layer_detector import detect_layers
from understand_anything.analysis.tour_generator import generate_heuristic_tour
from understand_anything.ignore.filter import filter_files, load_ignore_spec
from understand_anything.languages.registry import LanguageRegistry
from understand_anything.persistence import (
    save_fingerprints,
    save_graph,
    touch_meta,
)
from understand_anything.schema import ValidationResult, validate_graph

if TYPE_CHECKING:
    from understand_anything.plugins.registry import PluginRegistry
    from understand_anything.types import (
        AnalysisMeta,
        KnowledgeGraph,
        Layer,
        StructuralAnalysis,
        TourStep,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PipelineResult
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """端到端管道执行结果.

    Attributes:
        graph: 构建完成的知识图谱.
        validation: 图验证结果.
        layers: 检测到的架构层级列表.
        tour: 启发式导览步骤列表.
        analyzed_files: 成功分析的文件数量.
        ignored_files: 被忽略的文件数量.
        fingerprints: 文件路径到 SHA-256 十六进制摘要的映射.
        meta: 分析元数据（时间戳、git 哈希、文件计数等）.
    """

    graph: KnowledgeGraph
    validation: ValidationResult
    layers: list[Layer] = field(default_factory=list)
    tour: list[TourStep] = field(default_factory=list)
    analyzed_files: int = 0
    ignored_files: int = 0
    fingerprints: dict[str, str] = field(default_factory=dict)
    meta: AnalysisMeta | None = None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class Pipeline:
    """端到端知识图谱构建管道.

    编排文件发现、忽略过滤、代码/非代码分析、图构建、验证、
    层级检测、导览生成、指纹计算和持久化的完整流程.

    Example::

        pipeline = Pipeline("/path/to/project")
        result = pipeline.run()
        print(f"Nodes: {len(result.graph.nodes)}")
    """

    def __init__(
        self,
        project_root: str | Path,
        *,
        git_hash: str | None = None,
        language_registry: LanguageRegistry | None = None,
        plugin_registry: PluginRegistry | None = None,
        include_gitignore: bool = True,
        include_understandignore: bool = True,
        enable_validation: bool = True,
        enable_layer_detection: bool = True,
        enable_tour_generation: bool = True,
        enable_persistence: bool = True,
    ) -> None:
        """初始化管道.

        Args:
            project_root: 项目根目录路径.
            git_hash: Git commit SHA. 为 None 时自动通过 ``git rev-parse HEAD`` 检测.
            language_registry: 语言注册表. 为 None 时自动创建默认实例.
            plugin_registry: 插件注册表. 为 None 时自动创建并注册 TreeSitterPlugin
                和全部 12 个非代码解析器.
            include_gitignore: 是否加载 ``.gitignore`` 规则.
            include_understandignore: 是否加载 ``.understandignore`` 规则.
            enable_validation: 是否在图构建后运行验证.
            enable_layer_detection: 是否运行启发式层级检测.
            enable_tour_generation: 是否运行启发式导览生成.
            enable_persistence: 是否将图/元数据/指纹持久化到磁盘.
        """
        self._project_root = Path(project_root).resolve()
        self._include_gitignore = include_gitignore
        self._include_understandignore = include_understandignore
        self._enable_validation = enable_validation
        self._enable_layer_detection = enable_layer_detection
        self._enable_tour_generation = enable_tour_generation
        self._enable_persistence = enable_persistence

        # Git hash
        self._git_hash = git_hash or self._detect_git_hash()

        # Language registry
        self._language_registry = (
            language_registry or LanguageRegistry.create_default()
        )

        # Plugin registry (auto-create with all parsers if not provided)
        if plugin_registry is not None:
            self._plugin_registry = plugin_registry
        else:
            from understand_anything.plugins.parsers import (
                register_all_parsers,
            )
            from understand_anything.plugins.registry import PluginRegistry
            from understand_anything.plugins.tree_sitter import (
                TreeSitterPlugin,
            )

            self._plugin_registry = PluginRegistry(self._language_registry)
            self._plugin_registry.register(TreeSitterPlugin())
            register_all_parsers(self._plugin_registry)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> PipelineResult:
        """执行完整的知识图谱构建管道.

        Returns:
            PipelineResult 包含图、验证结果、层级、导览、统计信息等.
        """
        # 1. 发现文件
        all_files = self._discover_files()
        logger.info("Discovered %d files", len(all_files))

        # 2. 忽略过滤
        spec = load_ignore_spec(
            self._project_root,
            include_gitignore=self._include_gitignore,
            include_understandignore=self._include_understandignore,
        )
        included_files = filter_files(all_files, spec, project_root=self._project_root)
        ignored_count = len(all_files) - len(included_files)
        logger.info(
            "After filtering: %d included, %d ignored",
            len(included_files),
            ignored_count,
        )

        # 3-4. 构建图
        builder = GraphBuilder(
            project_name=self._project_root.name,
            git_hash=self._git_hash,
            language_registry=self._language_registry,
        )

        analyzed = 0
        analyzed_paths: set[str] = set()
        # path → node_id 映射，确保 import 边指向正确的节点 ID
        # （代码文件 ID 为 file:path，非代码文件 ID 为 {type}:path）
        path_to_node_id: dict[str, str] = {}
        # 两阶段处理：第一阶段分析所有文件构建完整节点集合，
        # 第二阶段解析 import/call 边（需要完整的 analyzed_paths）
        import_resolution_queue: list[
            tuple[str, str, StructuralAnalysis]
        ] = []

        for file_path_obj in included_files:
            rel_path = file_path_obj.as_posix()

            # 读取文件内容
            content = self._read_file(file_path_obj)
            if content is None:
                logger.debug("Skipping unreadable file: %s", rel_path)
                continue

            # 分析文件
            analysis = self._plugin_registry.analyze_file(rel_path, content)

            if analysis is not None:
                # 检查是否是代码文件（有函数/类）还是非代码文件
                if analysis.functions or analysis.classes:
                    node_id = self._process_code_file(
                        builder, rel_path, content, analysis
                    )
                else:
                    node_id = self._process_non_code_file(
                        builder, rel_path, content, analysis
                    )
                analyzed += 1
                analyzed_paths.add(rel_path)
                path_to_node_id[rel_path] = node_id
                import_resolution_queue.append(
                    (rel_path, content, analysis)
                )
            else:
                # 无插件匹配 — 作为通用文件节点添加
                summary = self._infer_summary(rel_path, content)
                node_type = self._resolve_node_type(rel_path)
                complexity = self._detect_complexity(content)
                tags = self._infer_tags(rel_path, analysis)

                if node_type == "file":
                    node_id = builder.add_file(
                        rel_path,
                        summary=summary,
                        tags=tags,
                        complexity=complexity,
                    )
                else:
                    node_id = builder.add_non_code_file(
                        rel_path,
                        node_type=node_type,
                        summary=summary,
                        tags=tags,
                        complexity=complexity,
                    )
                analyzed += 1
                analyzed_paths.add(rel_path)
                path_to_node_id[rel_path] = node_id

        # 第二阶段：在所有文件节点注册完成后解析 import/call 边
        for rel_path, content, analysis in import_resolution_queue:
            self._resolve_and_add_imports(
                builder, rel_path, content, analyzed_paths,
                path_to_node_id,
            )
            self._resolve_and_add_calls(
                builder, rel_path, content, analysis
            )

        # 4. 构建图
        graph = builder.build()
        logger.info("Graph built: %d nodes, %d edges", len(graph.nodes), len(graph.edges))

        # 5. 验证
        validation: ValidationResult
        if self._enable_validation:
            validation = validate_graph(graph.model_dump(by_alias=True))
            logger.info(
                "Validation: success=%s, issues=%d",
                validation.success,
                len(validation.issues),
            )
            # 用验证清理后的数据替换原始图（移除悬空边等）
            if validation.success and validation.data is not None:
                graph = type(graph).model_validate(validation.data)
        else:
            validation = ValidationResult(success=True, errors=[], issues=[])

        # 6. 层级检测
        layers: list[Layer] = []
        if self._enable_layer_detection:
            layers = detect_layers(graph)
            graph.layers = layers
            logger.info("Layers detected: %d", len(layers))

        # 7. 导览生成
        tour: list[TourStep] = []
        if self._enable_tour_generation:
            tour = generate_heuristic_tour(graph)
            graph.tour = tour
            logger.info("Tour steps generated: %d", len(tour))

        # 8. 指纹计算
        fingerprints = self._compute_fingerprints(included_files)

        # 9. 持久化
        meta: AnalysisMeta | None = None
        if self._enable_persistence:
            save_graph(self._project_root, graph)
            meta = touch_meta(
                self._project_root,
                git_commit_hash=self._git_hash,
                analyzed_files=analyzed,
            )
            save_fingerprints(self._project_root, fingerprints)
            logger.info("Persisted graph, meta, and fingerprints")

        # 10. 返回结果
        return PipelineResult(
            graph=graph,
            validation=validation,
            layers=layers,
            tour=tour,
            analyzed_files=analyzed,
            ignored_files=ignored_count,
            fingerprints=fingerprints,
            meta=meta,
        )

    # ------------------------------------------------------------------
    # Internal: file discovery & filtering
    # ------------------------------------------------------------------

    def _discover_files(self) -> list[Path]:
        """递归扫描项目目录，排除目录和 ``.understand-anything/``."""
        files: list[Path] = []
        output_dir_name = ".understand-anything"

        for entry in self._project_root.rglob("*"):
            if not entry.is_file():
                continue
            # 排除 .understand-anything/ 下的所有文件
            if output_dir_name in entry.parts:
                continue
            files.append(entry.relative_to(self._project_root))

        return files

    def _read_file(self, file_path: Path) -> str | None:
        """读取文件内容. 尝试 UTF-8, 检测到 null 字节则跳过（二进制文件）."""
        full_path = self._project_root / file_path
        try:
            raw = full_path.read_bytes()
        except OSError:
            return None

        # 检测二进制文件：包含 null 字节
        if b"\x00" in raw:
            return None

        # 尝试 UTF-8 解码
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            # 回退到 latin-1（始终可解码，但保留内容用于分析）
            return raw.decode("latin-1")

    # ------------------------------------------------------------------
    # Internal: code file processing
    # ------------------------------------------------------------------

    def _process_code_file(
        self,
        builder: GraphBuilder,
        rel_path: str,
        content: str,
        analysis: StructuralAnalysis,
    ) -> str:
        """处理代码文件：注册文件节点及其函数/类子节点.

        Returns:
            分配给该文件的节点 ID.
        """
        summary = self._infer_summary(rel_path, content)
        tags = self._infer_tags(rel_path, analysis)
        complexity = self._detect_complexity_from_analysis(analysis)
        file_summary = f"Source file: {Path(rel_path).name}"

        # 为函数/类生成摘要
        summaries: dict[str, str] = {}
        for fn in analysis.functions:
            summaries[fn.name] = f"Function: {fn.name}"
        for cls in analysis.classes:
            summaries[cls.name] = f"Class: {cls.name}"

        return builder.add_file_with_analysis(
            rel_path,
            analysis,
            summary=summary,
            tags=tags,
            complexity=complexity,
            file_summary=file_summary,
            summaries=summaries,
        )

    def _process_non_code_file(
        self,
        builder: GraphBuilder,
        rel_path: str,
        content: str,
        analysis: StructuralAnalysis,
    ) -> str:
        """处理非代码文件：注册带子节点的非代码文件节点.

        Returns:
            分配给该文件的节点 ID.
        """
        node_type = self._resolve_node_type(rel_path)
        summary = self._infer_summary(rel_path, content)
        tags = self._infer_tags(rel_path, analysis)
        complexity = self._detect_complexity(content)

        return builder.add_non_code_file_with_analysis(
            rel_path,
            node_type=node_type,
            summary=summary,
            tags=tags,
            complexity=complexity,
            definitions=analysis.definitions or None,
            services=analysis.services or None,
            endpoints=analysis.endpoints or None,
            steps=analysis.steps or None,
            resources=analysis.resources or None,
        )

    # ------------------------------------------------------------------
    # Internal: import & call graph resolution
    # ------------------------------------------------------------------

    def _resolve_and_add_imports(
        self,
        builder: GraphBuilder,
        rel_path: str,
        content: str,
        analyzed_paths: set[str],
        path_to_node_id: dict[str, str],
    ) -> None:
        """解析文件的 import 并为已知目标创建 import 边.

        使用 ``path_to_node_id`` 映射查找目标的真实节点 ID，
        确保对非代码文件（document:path、config:path 等）生成正确的边.
        """
        imports = self._plugin_registry.resolve_imports(rel_path, content)
        if not imports:
            return

        source_id = path_to_node_id[rel_path]

        for imp in imports:
            # 尝试多种方式匹配目标文件，返回目标节点 ID
            target_id = self._match_import_target(
                imp.source, imp.resolved_path, rel_path,
                analyzed_paths, path_to_node_id,
            )
            if target_id:
                builder.add_import_edge_by_id(source_id, target_id)

    def _resolve_and_add_calls(
        self,
        builder: GraphBuilder,
        rel_path: str,
        content: str,
        analysis: StructuralAnalysis,
    ) -> None:
        """提取 call graph 并添加 call 边（仅限同文件内调用）.

        跨文件调用和外库调用需要完整的 import/specifier 解析才能确定
        callee 所在文件，当前版本暂不处理.
        """
        calls = self._plugin_registry.extract_call_graph(rel_path, content)
        if not calls:
            return

        # 仅添加同文件内的已知函数/方法之间的 call 边
        known_functions = {fn.name for fn in analysis.functions}
        for cls in analysis.classes:
            known_functions.update(cls.methods)

        for entry in calls:
            caller_name = self._normalize_call_name(entry.caller, known_functions)
            if caller_name is None:
                continue

            # 解析 callee 名称：树解析器对 ``self.log()`` 会报告 ``self.log``,
            # 需要提取点号后面的方法名来匹配已知函数列表
            callee_name = self._normalize_call_name(entry.callee, known_functions)
            if callee_name is None:
                continue

            builder.add_call_edge(
                caller_file=rel_path,
                caller_func=caller_name,
                callee_file=rel_path,
                callee_func=callee_name,
            )

    @staticmethod
    def _normalize_call_name(
        name: str, known_functions: set[str]
    ) -> str | None:
        """Return a known same-file function/method name for a call endpoint."""
        if name in known_functions:
            return name
        if "." in name:
            _, _, method_part = name.rpartition(".")
            if method_part in known_functions:
                return method_part
        return None

    def _match_import_target(
        self,
        source: str,
        resolved_path: str,
        rel_path: str,
        analyzed_paths: set[str],
        path_to_node_id: dict[str, str],
    ) -> str | None:
        """尝试将 import 解析结果匹配到已分析文件的节点 ID.

        匹配策略（按优先级）:
        1. 将 resolved_path 转为项目相对路径，精确匹配
        2. 从源文件目录解析 import source，匹配已分析文件
        3. 对上述路径添加常见扩展名 (.ts/.py/.js) 再匹配

        Args:
            source: 原始 import 源字符串（如 ``"./utils"``）.
            resolved_path: 插件解析后的路径（可能是绝对路径）.
            rel_path: 当前文件的相对路径.
            analyzed_paths: 已分析的文件路径集合.
            path_to_node_id: 文件路径到节点 ID 的映射.

        Returns:
            匹配到的目标节点 ID（如 ``file:src/utils.ts`` 或
            ``document:src/styles.css``），匹配失败返回 None.
        """
        if not resolved_path and not source:
            return None

        candidates: list[str] = []

        # 策略 1：将 resolved_path 转为项目相对路径
        if resolved_path:
            p = Path(resolved_path)
            if p.is_absolute():
                with contextlib.suppress(ValueError):
                    candidates.append(
                        p.relative_to(self._project_root).as_posix()
                    )
            else:
                candidates.append(p.as_posix())

        # 策略 2：从源文件目录解析 import source（相对导入）
        if source and source.startswith("."):
            source_dir = Path(rel_path).parent
            # 基于 project_root 解析，避免 Path.resolve() 依赖 CWD
            resolved = (
                self._project_root / source_dir / source
            ).resolve()
            with contextlib.suppress(ValueError):
                candidates.append(
                    resolved.relative_to(self._project_root).as_posix()
                )

        # 匹配候选路径（精确匹配或添加常见扩展名），
        # 通过 path_to_node_id 返回正确的节点 ID
        common_extensions = (".ts", ".tsx", ".js", ".jsx", ".py", ".pyw")
        for candidate in candidates:
            if candidate in analyzed_paths:
                return path_to_node_id[candidate]
            for ext in common_extensions:
                with_ext = candidate + ext
                if with_ext in analyzed_paths:
                    return path_to_node_id[with_ext]

        return None

    # ------------------------------------------------------------------
    # Internal: node type resolution
    # ------------------------------------------------------------------

    def _resolve_node_type(self, file_path: str) -> str:
        """根据文件扩展名/名称推断节点类型.

        映射规则:
            - ``.md`` → ``document``
            - ``.yaml``/``.yml``/``.toml``/``.json``/``.env`` → ``config``
            - ``.sql``/``.graphql``/``.gql``/``.proto`` → ``schema``
            - ``Dockerfile``/``Makefile``/``.sh`` → ``pipeline``
            - ``.tf`` → ``resource``
            - 其他 → ``document``
        """
        name_lower = Path(file_path).name.lower()
        suffix = Path(file_path).suffix.lower()

        # Document types
        if suffix in (".md", ".mdx", ".rst", ".txt"):
            return "document"

        # Config types
        if suffix in (".yaml", ".yml", ".toml", ".json", ".jsonc", ".env"):
            return "config"

        # Schema types
        if suffix in (".sql", ".graphql", ".gql", ".proto"):
            return "schema"

        # Pipeline/build types
        if name_lower in ("dockerfile", "makefile", "jenkinsfile"):
            return "pipeline"
        if suffix in (".sh", ".bash", ".zsh", ".mk"):
            return "pipeline"

        # Infrastructure types
        if suffix in (".tf", ".tfvars"):
            return "resource"

        return "document"

    # ------------------------------------------------------------------
    # Internal: complexity detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_complexity(content: str) -> str:
        """基于文件内容行数推断复杂度.

        - 0-50 行 → ``simple``
        - 51-200 行 → ``moderate``
        - 201+ 行 → ``complex``
        """
        line_count = content.count("\n") + 1
        if line_count <= 50:
            return "simple"
        if line_count <= 200:
            return "moderate"
        return "complex"

    @staticmethod
    def _detect_complexity_from_analysis(analysis: StructuralAnalysis) -> str:
        """基于函数/类数量推断复杂度.

        - 0-2 个符号 → ``simple``
        - 3-8 个符号 → ``moderate``
        - 9+ 个符号 → ``complex``
        """
        count = len(analysis.functions) + len(analysis.classes)
        if count <= 2:
            return "simple"
        if count <= 8:
            return "moderate"
        return "complex"

    # ------------------------------------------------------------------
    # Internal: summary & tags inference
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_summary(file_path: str, content: str) -> str:
        """从文件名和内容推断人类可读摘要."""
        name = Path(file_path).name
        line_count = content.count("\n") + 1
        return f"{name} ({line_count} lines)"

    @staticmethod
    def _infer_tags(
        file_path: str, analysis: StructuralAnalysis | None
    ) -> list[str]:
        """从文件路径和分析结果推断标签."""
        tags: list[str] = []
        suffix = Path(file_path).suffix.lower()
        name_lower = Path(file_path).name.lower()

        # Language tag
        lang_map: dict[str, str] = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
        }
        if suffix in lang_map:
            tags.append(lang_map[suffix])

        # File role tags
        if name_lower in ("dockerfile", "makefile"):
            tags.append("build")
        if "test" in file_path.lower():
            tags.append("test")
        if suffix in (".yaml", ".yml", ".toml", ".json", ".env"):
            tags.append("config")
        if suffix in (".md", ".mdx"):
            tags.append("documentation")

        # Domain tags from analysis
        if analysis is not None:
            if analysis.services:
                tags.append("services")
            if analysis.endpoints:
                tags.append("api")
            if analysis.resources:
                tags.append("infrastructure")
            if analysis.definitions:
                tags.append("schema")

        return sorted(set(tags))

    # ------------------------------------------------------------------
    # Internal: fingerprints & git hash
    # ------------------------------------------------------------------

    def _compute_fingerprints(
        self, files: list[Path]
    ) -> dict[str, str]:
        """计算所有文件的 SHA-256 内容指纹.

        Args:
            files: 项目相对路径列表.

        Returns:
            文件路径（POSIX 风格）到 SHA-256 十六进制摘要的映射.
        """
        fingerprints: dict[str, str] = {}
        for file_path_obj in files:
            content = self._read_file(file_path_obj)
            if content is not None:
                sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
                fingerprints[file_path_obj.as_posix()] = sha
            else:
                fingerprints[file_path_obj.as_posix()] = "binary-skipped"
        return fingerprints

    def _detect_git_hash(self) -> str:
        """通过 ``git rev-parse HEAD`` 检测当前 commit SHA.

        Returns:
            Git commit SHA 字符串，失败时返回 ``"unknown"``.
        """
        import shutil

        git_path = shutil.which("git")
        if git_path is None:
            return "unknown"

        try:
            result = subprocess.run(
                [git_path, "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self._project_root,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return "unknown"
