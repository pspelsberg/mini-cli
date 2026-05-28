import os
import asyncio
from pathlib import Path
from typing import List, Optional
from core.models import FileModification
from core.ui_reporter import UIReporter


class WorkspaceManager:
    """Handles file system operations safely and applies modifications."""
    
    def __init__(self, ui: UIReporter, workspace_dir: Path = None):
        self.ui = ui
        self.workspace_dir = workspace_dir.resolve() if workspace_dir else Path(os.getcwd()).resolve()

    def get_safe_resolved_path(self, filepath: str) -> Optional[Path]:
        """
        Resolves the filepath and checks if it is strictly within the workspace directory.
        Returns the resolved Path object if safe, or None if unsafe.
        """
        try:
            target = Path(filepath).resolve()
            if target.is_relative_to(self.workspace_dir):
                return target
        except Exception:
            return None
        return None

    def _is_safe_path(self, filepath: str) -> bool:
        """Compatibility wrapper for path safety check."""
        return self.get_safe_resolved_path(filepath) is not None

    async def file_exists(self, filepath: str) -> bool:
        """Checks asynchronously if a file exists safely within the workspace."""
        resolved = self.get_safe_resolved_path(filepath)
        if not resolved:
            return False
        return await asyncio.to_thread(resolved.exists)

    async def read_file_content(self, filepath: str) -> Optional[str]:
        """Reads a file asynchronously and safely within the workspace."""
        resolved = self.get_safe_resolved_path(filepath)
        if not resolved:
            return None
        
        def _read():
            with open(resolved, "r", encoding="utf-8") as f:
                return f.read()
        try:
            return await asyncio.to_thread(_read)
        except (IOError, OSError):
            return None

    async def write_file_content(self, filepath: str, content: str) -> bool:
        """Writes a file asynchronously and safely within the workspace."""
        resolved = self.get_safe_resolved_path(filepath)
        if not resolved:
            return False
        
        def _write():
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with open(resolved, "w", encoding="utf-8") as f:
                f.write(content)
        try:
            await asyncio.to_thread(_write)
            return True
        except (IOError, OSError):
            return False

    async def _apply_single_modification(self, mod: FileModification, mode: str, resolved_path: Path) -> bool:
        """Applies a single file modification."""
        try:
            old_content = ""
            exists = await asyncio.to_thread(resolved_path.exists)
            if exists:
                content = await self.read_file_content(mod.filepath)
                if content is not None:
                    old_content = content
            
            if old_content == mod.content:
                self.ui.show_up_to_date(mod.filepath)
                return False
            
            self.ui.show_diff(old_content, mod)
        
            should_write = True
            if mode == "build":
                if not await self.ui.ask_to_apply(mod.filepath):
                    self.ui.show_skip(mod.filepath)
                    should_write = False
            else:
                self.ui.show_auto_write(mod.filepath)

            if should_write:
                self.ui.show_writing(mod.filepath)
                return await self.write_file_content(mod.filepath, mod.content)
            return False
        except (IOError, OSError) as e:
            self.ui.show_io_error(mod.filepath, e)
            return False

    async def apply_modifications(self, modifications: List[FileModification], mode: str) -> List[str]:
        """
        Applies file modifications to the workspace safely.
        """
        files_written = []
        for mod in modifications:
            resolved_path = self.get_safe_resolved_path(mod.filepath)
            if not resolved_path:
                self.ui.show_security_block(mod.filepath)
                continue

            if mode == "plan":
                self.ui.show_plan_mode(mod)
            elif mode in ["build", "auto"]:
                if await self._apply_single_modification(mod, mode, resolved_path):
                    files_written.append(mod.filepath)
        return files_written
