"""文件变更监听 — watchdog 文件监听 (inotify/FSEvents), 2s 防抖.

需要 ``watchdog`` 可选依赖: ``pip install watchdog``.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any, Protocol

    class _ObserverLike(Protocol):
        """watchdog Observer 的最小接口.

        使用 ``Any`` 作为 event_handler 和返回值类型,
        避免与 watchdog 可选依赖的具体类型冲突.
        """

        def schedule(
            self,
            event_handler: Any,
            path: str,
            *,
            recursive: bool = ...,
        ) -> Any: ...
        def start(self) -> None: ...
        def stop(self) -> None: ...
        def join(self) -> None: ...

logger = logging.getLogger(__name__)

# 防抖延迟 (秒)
DEBOUNCE_SECONDS = 2.0


class FileWatcher:
    """文件系统变更监听器.

    基于 watchdog, 在文件变更时触发回调, 内置 2s 防抖.

    Example::

        def handle(added, modified, deleted):
            print(f"Changed: {len(added)} added, {len(modified)} modified")

        watcher = FileWatcher("/path/to/project", on_change=handle)
        watcher.start()
    """

    def __init__(
        self,
        project_root: str | Path,
        on_change: Callable[[set[str], set[str], set[str]], None],
        *,
        debounce_seconds: float = DEBOUNCE_SECONDS,
    ) -> None:
        """初始化文件监听器.

        Args:
            project_root: 项目根目录.
            on_change: 回调函数 ``(added, modified, deleted)``.
            debounce_seconds: 防抖延迟 (默认 2s).
        """
        self._project_root = Path(project_root)
        self._on_change = on_change
        self._debounce_seconds = debounce_seconds
        self._observer: _ObserverLike | None = None
        self._pending: dict[str, float] = {}
        self._running = False

    def start(self) -> None:
        """启动文件监听 (阻塞式).

        如果 ``watchdog`` 未安装, 抛出 ``ImportError``.
        """
        try:
            import watchdog.events as _we
            import watchdog.observers as _wo

            _handler_cls = _we.FileSystemEventHandler
            _observer_cls = _wo.Observer
        except ImportError:
            msg = (
                "watchdog is required for file watching. "
                "Install it with: pip install watchdog"
            )
            logger.exception(msg)
            raise ImportError(msg) from None

        project_root = str(self._project_root)
        watcher_ref = self

        class _Handler(_handler_cls):  # type: ignore[valid-type,misc]
            def on_created(self, event: object) -> None:
                if not getattr(event, "is_directory", False):
                    path = getattr(event, "src_path", "")
                    watcher_ref._on_file_event("created", str(path))

            def on_modified(self, event: object) -> None:
                if not getattr(event, "is_directory", False):
                    path = getattr(event, "src_path", "")
                    watcher_ref._on_file_event("modified", str(path))

            def on_deleted(self, event: object) -> None:
                if not getattr(event, "is_directory", False):
                    path = getattr(event, "src_path", "")
                    watcher_ref._on_file_event("deleted", str(path))

        observer = _observer_cls()
        observer.schedule(_Handler(), project_root, recursive=True)
        observer.start()
        self._observer = observer
        self._running = True
        logger.info(
            "File watcher started on %s (debounce: %.1fs)",
            project_root,
            self._debounce_seconds,
        )

    def stop(self) -> None:
        """停止文件监听."""
        observer = self._observer
        if observer is not None:
            observer.stop()
            observer.join()
            self._observer = None
        self._running = False
        logger.info("File watcher stopped")

    def _on_file_event(self, event_type: str, file_path: str) -> None:
        """防抖处理文件变更事件.

        收集变更文件, 触发防抖回调.
        """
        now = time.time()
        last = self._pending.get(file_path, 0)

        if now - last < self._debounce_seconds:
            self._pending[file_path] = now
            return

        self._pending[file_path] = now

        # 简化处理: 按事件类型分类并触发回调
        added: set[str] = {file_path} if event_type == "created" else set()
        modified: set[str] = (
            {file_path} if event_type == "modified" else set()
        )
        deleted: set[str] = {file_path} if event_type == "deleted" else set()

        try:
            self._on_change(added, modified, deleted)
        except Exception:
            logger.exception("Error in file change callback")


__all__ = ["FileWatcher"]
