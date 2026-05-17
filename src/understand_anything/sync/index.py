"""增量同步协调器 — 管理文件变更后的重新索引.

v2 plan: 必须优先复用 fingerprint / staleness / change_classifier 模块.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understand_anything.pipeline import Pipeline

logger = logging.getLogger(__name__)


class IncrementalSyncer:
    """增量同步协调器.

    复用现有模块:
      - ``analysis/fingerprint.py``: 文件指纹计算
      - ``analysis/staleness.py``: Git 变更检测和图合并
      - ``analysis/change_classifier.py``: 变更分类决策

    Example::

        syncer = IncrementalSyncer(pipeline)
        syncer.load_fingerprints()
        stats = syncer.sync_all()
    """

    def __init__(
        self,
        pipeline: Pipeline,
        backend: object | None = None,
    ) -> None:
        """初始化同步器.

        Args:
            pipeline: 管道实例 (用于重新分析).
            backend: SQLite 后端实例 (可选).
        """
        self._pipeline = pipeline
        self._backend = backend
        self._fingerprints: dict[str, str] = {}
        self._last_commit: str | None = None

    def load_fingerprints(self) -> None:
        """从持久化加载现有指纹快照."""
        from understand_anything.persistence import load_fingerprints

        project_root = str(self._pipeline._project_root)
        self._fingerprints = load_fingerprints(Path(project_root))
        logger.debug(
            "Loaded %d fingerprints from storage", len(self._fingerprints)
        )

    def sync_all(self) -> dict[str, int]:
        """执行全量重新分析.

        Returns:
            ``{"analyzed": N, "ignored": N, "nodes": N, "edges": N}``.
        """
        result = self._pipeline.run()
        self._fingerprints = result.fingerprints
        return {
            "analyzed": result.analyzed_files,
            "ignored": result.ignored_files,
            "nodes": len(result.graph.nodes),
            "edges": len(result.graph.edges),
        }

    def sync_files(
        self, added: set[str], modified: set[str], deleted: set[str]
    ) -> dict[str, int]:
        """对变更文件进行增量同步.

        使用 fingerprint 模块判断变更类型,
        使用 change_classifier 决定更新策略.

        Args:
            added: 新增文件路径集合.
            modified: 修改文件路径集合.
            deleted: 删除文件路径集合.

        Returns:
            统计信息 dict.
        """
        changed_files = added | modified | deleted
        if not changed_files:
            return {"added": 0, "modified": 0, "deleted": 0}

        logger.info(
            "Change detected: +%d ~%d -%d — checking staleness",
            len(added),
            len(modified),
            len(deleted),
        )

        # 使用 fingerprint 模块检查哪些文件实际发生了变化
        changed = self._compute_changed_files(changed_files)
        if not changed:
            logger.debug("No actual content changes detected (fingerprint match)")
            return {
                "added": len(added),
                "modified": len(modified),
                "deleted": len(deleted),
            }

        # 使用 change_classifier 决定更新策略 (v2: 复用现有模块)
        try:
            from understand_anything.analysis.change_classifier import (
                classify_update,
            )
            from understand_anything.analysis.fingerprint import (
                ChangeAnalysis,
            )

            change_analysis = ChangeAnalysis(
                new_files=list(added),
                deleted_files=list(deleted),
                structurally_changed_files=list(changed & modified),
                cosmetic_only_files=list(changed - modified),
            )

            decision = classify_update(
                change_analysis,
                total_files_in_graph=len(self._fingerprints),
            )
            logger.info(
                "Change classification: %s — %s",
                decision.action,
                decision.reason,
            )

            if decision.action == "SKIP":
                return {
                    "added": len(added),
                    "modified": len(modified),
                    "deleted": len(deleted),
                    "skipped": len(changed_files),
                }
        except ImportError:
            logger.debug(
                "change_classifier not available, doing full re-analysis"
            )

        # 默认: 全量重新分析
        stats = self.sync_all()
        return {
            "added": len(added),
            "modified": len(modified),
            "deleted": len(deleted),
            **stats,
        }

    def get_staleness(
        self, project_dir: str | None = None, last_commit: str | None = None
    ) -> tuple[bool, list[str]]:
        """使用 staleness 模块检查知识图谱是否过期.

        Args:
            project_dir: 项目目录 (默认使用 pipeline 的 project_root).
            last_commit: 上次提交哈希 (默认使用内部记录).

        Returns:
            ``(stale, changed_files)`` 元组.
        """
        from understand_anything.analysis.staleness import is_stale as check_stale

        project = project_dir or str(self._pipeline._project_root)
        commit = last_commit or self._last_commit or "HEAD~1"
        return check_stale(project, commit)

    def merge_graph_update(
        self,
        existing_graph,
        changed_file_paths: list[str],
        new_nodes: list,
        new_edges: list,
        new_commit_hash: str,
    ):
        """使用 staleness 模块的 merge_graph_update 合并增量更新."""
        from understand_anything.analysis.staleness import merge_graph_update

        return merge_graph_update(
            existing_graph=existing_graph,
            changed_file_paths=changed_file_paths,
            new_nodes=new_nodes,
            new_edges=new_edges,
            new_commit_hash=new_commit_hash,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _compute_changed_files(self, candidate_files: set[str]) -> set[str]:
        """使用 fingerprint 模块计算实际变更的文件."""
        from understand_anything.analysis.fingerprint import content_hash

        changed: set[str] = set()
        project_root = self._pipeline._project_root

        for rel_path in candidate_files:
            full_path = project_root / rel_path
            if not full_path.exists():
                changed.add(rel_path)
                continue

            try:
                content = full_path.read_text()
                new_fp = content_hash(content)
                old_fp = self._fingerprints.get(rel_path)
                if new_fp != old_fp:
                    changed.add(rel_path)
            except OSError:
                changed.add(rel_path)

        return changed


__all__ = ["IncrementalSyncer"]
