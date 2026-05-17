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
from understand_anything.analysis.resolution import (
    ReferenceResolver,
    build_resolution_context,
)
from understand_anything.analysis.resolution.types import UnresolvedRef
from understand_anything.analysis.tour_generator import generate_heuristic_tour
from understand_anything.ignore.filter import filter_files, load_ignore_spec
from understand_anything.languages.registry import LanguageRegistry
from understand_anything.persistence import (
    create_backend,
    save_fingerprints,
    save_graph,
    touch_meta,
)
from understand_anything.schema import ValidationResult, validate_graph
from understand_anything.types import GraphNode

if TYPE_CHECKING:
    from typing import Literal

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
        backend: Literal["json", "sqlite"] = "json",
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
            backend: 持久化后端 (``"json"`` 或 ``"sqlite"``).
        """
        self._project_root = Path(project_root).resolve()
        self._include_gitignore = include_gitignore
        self._include_understandignore = include_understandignore
        self._enable_validation = enable_validation
        self._enable_layer_detection = enable_layer_detection
        self._enable_tour_generation = enable_tour_generation
        self._enable_persistence = enable_persistence
        self._backend_type = backend

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

        # 2.5 框架检测 (Phase 4)
        detected_frameworks = self._detect_frameworks(included_files)
        if detected_frameworks:
            logger.info(
                "Detected frameworks: %s",
                [f.display_name for f in detected_frameworks],
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

        # 2.5 跨文件引用解析 (Phase 2 — 新增)
        self._resolve_cross_file_references(
            builder,
            list(import_resolution_queue),
            analyzed_paths,
            path_to_node_id,
        )

        # 2.6 框架感知解析 (Phase 8 — 产出 graph 节点/边)
        if detected_frameworks:
            self._resolve_frameworks(
                builder,
                list(import_resolution_queue),
                detected_frameworks,
                path_to_node_id,
            )

        # 将检测到的框架注入 builder
        if detected_frameworks:
            builder.set_frameworks([f.display_name for f in detected_frameworks])

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
            _backend_type, sqlite = create_backend(
                self._project_root, backend=self._backend_type
            )
            if sqlite is not None:
                sqlite.save_graph(graph)
                sqlite.save_fingerprints(fingerprints)
                sqlite.close()
            else:
                save_graph(self._project_root, graph)
                save_fingerprints(self._project_root, fingerprints)
            meta = touch_meta(
                self._project_root,
                git_commit_hash=self._git_hash,
                analyzed_files=analyzed,
            )
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

    # 文件发现时排除的目录名
    _EXCLUDED_DIRS = frozenset({
        ".understand-anything",
        ".uv-cache",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".git",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    })

    def _discover_files(self) -> list[Path]:
        """递归扫描项目目录，排除缓存和虚拟环境目录."""
        files: list[Path] = []

        for entry in self._project_root.rglob("*"):
            if not entry.is_file():
                continue
            # 排除位于已知缓存目录下的文件
            if self._EXCLUDED_DIRS.intersection(entry.parts):
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
            if cls.method_details:
                known_functions.update(m.name for m in cls.method_details)

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

    def _resolve_cross_file_references(
        self,
        builder: GraphBuilder,
        queue: list[tuple[str, str, StructuralAnalysis]],
        analyzed_paths: set[str],
        path_to_node_id: dict[str, str],
    ) -> None:
        """跨文件引用解析 (Phase 2).

        构建解析上下文, 收集未解析引用, 执行四级解析策略,
        将高置信度引用添加为图边.

        Args:
            builder: 图构建器.
            queue: ``(file_path, content, analysis)`` 列表.
            analyzed_paths: 已分析文件路径集合.
            path_to_node_id: 路径 → 节点 ID 映射.
        """
        # 构建解析上下文
        import_map: dict[str, dict[str, str]] = {}
        export_map: dict[str, set[str]] = {}
        symbol_map: dict[str, list[tuple[str, str]]] = {}
        language_map: dict[str, str] = {}

        for rel_path, _content, analysis in queue:
            # 导入映射: file -> {import_source: target_file} (通过现有匹配逻辑)
            lang = self._language_registry.get_for_file(rel_path)
            if lang:
                language_map[rel_path] = lang.id

            # 导出映射: file -> {exported_name}
            exports = {e.name for e in analysis.exports}
            if exports:
                export_map[rel_path] = exports

            # 符号映射: symbol_name -> [(file, kind)]
            for fn in analysis.functions:
                symbol_map.setdefault(fn.name, []).append(
                    (rel_path, "function")
                )
            for cls in analysis.classes:
                symbol_map.setdefault(cls.name, []).append(
                    (rel_path, "class")
                )
                for method_name in cls.methods:
                    symbol_map.setdefault(method_name, []).append(
                        (rel_path, "method")
                    )
                for method in cls.method_details or []:
                    symbol_map.setdefault(method.name, []).append(
                        (rel_path, "method")
                    )
            for var in analysis.variables or []:
                symbol_map.setdefault(var.name, []).append(
                    (rel_path, "variable")
                )
            for enum in analysis.enums or []:
                symbol_map.setdefault(enum.name, []).append(
                    (rel_path, "enum")
                )
            for iface in analysis.interfaces or []:
                symbol_map.setdefault(iface.name, []).append(
                    (rel_path, "interface")
                )
            for ta in analysis.type_aliases or []:
                symbol_map.setdefault(ta.name, []).append(
                    (rel_path, "type_alias")
                )

            # 解析导入到文件的映射 (复用现有 _match_import_target)
            file_imports: dict[str, str] = {}
            for imp in analysis.imports:
                resolved = self._match_import_target(
                    imp.source, imp.source, rel_path,
                    analyzed_paths, path_to_node_id,
                )
                if resolved:
                    target_path = resolved.split(":", 1)[-1]
                    file_imports[imp.source] = target_path
            if file_imports:
                import_map[rel_path] = file_imports

        # 解析继承/实现边 (使用全局符号表定位目标节点)
        inheritance_resolved = builder.resolve_inheritance_edges(symbol_map)
        if inheritance_resolved:
            logger.info(
                "Resolved %d inheritance/implementation edges",
                inheritance_resolved,
            )

        # 构建解析上下文
        ctx = build_resolution_context(
            workspace_root=str(self._project_root),
            analyzed_files=analyzed_paths,
            import_map=import_map,
            export_map=export_map,
            symbol_map=symbol_map,
        )

        # 创建解析器
        resolver = ReferenceResolver(ctx)

        # 收集未解析引用
        all_unresolved: dict[str, list[UnresolvedRef]] = {}

        for rel_path, content, analysis in queue:
            unresolved: list[UnresolvedRef] = []

            # 从调用图中收集跨文件调用
            calls = self._plugin_registry.extract_call_graph(
                rel_path, content
            )
            if calls:
                known_local = {fn.name for fn in analysis.functions}
                for cls in analysis.classes:
                    known_local.update(cls.methods)
                    if cls.method_details:
                        known_local.update(m.name for m in cls.method_details)

                for entry in calls:
                    callee_name = self._normalize_call_name(
                        entry.callee, known_local
                    )
                    # Only treat as cross-file if NOT a local call
                    if callee_name is None and entry.callee not in known_local:
                        unresolved.append(
                            UnresolvedRef(
                                source_file=rel_path,
                                symbol=entry.callee,
                                ref_type="call",
                                line_number=entry.line_number,
                                caller_symbol=entry.caller,
                            )
                        )

            # 从导入中收集未解析引用
            for imp in analysis.imports:
                for spec in imp.specifiers:
                    if spec == "*":
                        continue
                    unresolved.append(
                        UnresolvedRef(
                            source_file=rel_path,
                            symbol=spec,
                            ref_type="import",
                            line_number=imp.line_number,
                            import_source=imp.source,
                        )
                    )

            if unresolved:
                all_unresolved[rel_path] = unresolved

        if not all_unresolved:
            logger.debug("No unresolved cross-file references found.")
            return

        # 执行解析
        resolved_refs = resolver.resolve_all(
            all_unresolved, language_map=language_map
        )
        logger.info(
            "Cross-file resolution: %d unresolved → %d resolved",
            sum(len(v) for v in all_unresolved.values()),
            len(resolved_refs),
        )

        # 添加跨文件边 (v2: 仅高置信度 ≥ 0.9)
        added_edges = 0
        for ref in resolved_refs:
            if ref.confidence < 0.9:
                continue

            source_node_id = path_to_node_id.get(ref.unresolved.source_file)
            target_node_id = path_to_node_id.get(ref.target_file)

            if source_node_id is None or target_node_id is None:
                continue

            edge_type = ref.edge_type_hint

            if edge_type == "calls":
                # 精确到函数级别的 call 边
                # 注意: symbol 是 callee, caller_symbol 才是调用方
                caller_func = ref.unresolved.caller_symbol
                if not caller_func:
                    continue  # 没有 caller 信息, 无法构造 call 边
                builder.add_call_edge(
                    caller_file=ref.unresolved.source_file,
                    caller_func=caller_func,
                    callee_file=ref.target_file,
                    callee_func=ref.target_symbol,
                )
            elif edge_type == "imports":
                builder.add_import_edge_by_id(
                    source_node_id, target_node_id
                )
            elif edge_type in ("inherits", "implements"):
                # 继承/实现边: source → target class/interface
                pass  # 继承边已在 graph_builder 中处理
            else:
                # 默认添加通用 references 边
                pass  # references 边是低优先级的, 由框架处理

            added_edges += 1

        logger.info(
            "Cross-file edges added: %d (confidence ≥ 0.5)", added_edges
        )

    def _resolve_frameworks(
        self,
        builder: GraphBuilder,
        queue: list[tuple[str, str, StructuralAnalysis]],
        detected_frameworks: list,
        path_to_node_id: dict[str, str],
    ) -> None:
        """框架感知解析 (Phase 8).

        使用 FrameworkGraphResolver 从源代码中提取框架特有的图节点和边.

        Args:
            builder: 图构建器.
            queue: ``(file_path, content, analysis)`` 列表.
            detected_frameworks: 检测到的 FrameworkConfig 列表.
            path_to_node_id: 路径 → 节点 ID 映射.
        """
        from understand_anything.analysis.resolution.framework_resolver import (
            FrameworkGraphResolver,
        )

        resolver = FrameworkGraphResolver(detected_frameworks)
        total_nodes = 0
        total_edges = 0

        for rel_path, content, _analysis in queue:
            lang = self._language_registry.get_for_file(rel_path)
            lang_id = lang.id if lang else "unknown"

            frame_nodes, frame_edges = resolver.resolve_file(
                rel_path, content, lang_id
            )

            # 添加框架产生的节点
            for node_dict in frame_nodes:
                node = GraphNode.model_validate(node_dict)
                file_id = path_to_node_id.get(rel_path)
                if builder.add_node(node, parent_id=file_id):
                    total_nodes += 1

            # 添加框架产生的边
            for edge_dict in frame_edges:
                from understand_anything.types import EdgeType, GraphEdge

                edge_type = EdgeType(edge_dict["type"])
                edge = GraphEdge(
                    source=edge_dict["source"],
                    target=edge_dict["target"],
                    type=edge_type,
                    direction="forward",
                    weight=edge_dict.get("weight", 1.0),
                    description=edge_dict.get("description"),
                )
                if builder.add_edge(edge):
                    total_edges += 1

        if total_nodes or total_edges:
            logger.info(
                "Framework resolution: %d nodes, %d edges added",
                total_nodes,
                total_edges,
            )

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

    def _detect_frameworks(self, included_files: list[Path]) -> list:
        """检测项目使用的框架 (Phase 4).

        通过扫描清单文件 (package.json, requirements.txt, pom.xml 等)
        并使用 FrameworkRegistry 检测框架.

        Args:
            included_files: 经过 ignore 过滤后的文件列表.

        Returns:
            检测到的 FrameworkConfig 列表.
        """
        from understand_anything.languages.framework_registry import (
            FrameworkRegistry,
        )

        # 常见的清单文件名
        manifest_names = {
            "package.json",
            "requirements.txt",
            "pyproject.toml",
            "Pipfile",
            "setup.cfg",
            "setup.py",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "go.mod",
            "Gemfile",
            "composer.json",
            "Cargo.toml",
        }

        manifests: dict[str, str] = {}
        for file_path_obj in included_files:
            name = file_path_obj.name
            if name in manifest_names:
                content = self._read_file(file_path_obj)
                if content is not None:
                    manifests[name] = content

        if not manifests:
            return []

        registry = FrameworkRegistry.create_default()
        return registry.detect_frameworks(manifests)

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
