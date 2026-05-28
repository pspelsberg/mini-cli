import asyncio
import os
import sys
from pathlib import Path
from typing import List
from rich.console import Console

from core.models import FileModification
from core.base_agent import BaseAgent
from core.i18n import t
from tools.command_runner import CommandRunner

console = Console()

class QAAgent(BaseAgent):
    """
    Skill 1: Quality Assurance & Code Integrity
    Validates generated code modifications against linting standards (Ruff).
    """
    def __init__(self):
        self._name = "QA-Agent"

    @property
    def name(self) -> str:
        return self._name

    async def validate_code(self, modifications: List[FileModification]) -> tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Starting linting validation...",
                        f"[bold yellow][{self.name}][/bold yellow] Starte Linting-Validierung..."))
        await asyncio.sleep(0.5)
        
        import shutil
        workspace_dir = Path(os.getcwd()).resolve()
        
        for mod in modifications:
            filepath = mod.filepath
            # Validate path safety
            try:
                resolved_path = Path(filepath).resolve()
                if not resolved_path.is_relative_to(workspace_dir):
                    console.print(t(f"[bold red]WARNING: QA validation blocked path traversal to {filepath}[/bold red]",
                                    f"[bold red]WARNUNG: QA-Validierung verhinderte Path Traversal nach {filepath}[/bold red]"))
                    continue
            except (RuntimeError, OSError) as e:
                console.print(f"[dim]Path resolution error for {filepath}: {e}[/dim]")
                continue

            # Non-blocking check for file existence
            exists = await asyncio.to_thread(resolved_path.exists)
            if not exists:
                continue
                
            # 1. Python Linting (Ruff)
            if filepath.endswith('.py'):
                try:
                    result = await CommandRunner.run_async([sys.executable, "-m", "ruff", "check", "--fix", filepath])
                    if result.returncode != 0:
                        error_output = result.stderr + result.stdout
                        if "No module named ruff" in error_output:
                            console.print(t("[dim]Ruff not found, skipping Python linting.[/dim]",
                                            "[dim]Ruff nicht gefunden, überspringe Python-Linting.[/dim]"))
                            continue
                        return False, t(f"Linter error in {filepath}:\n{result.stdout}\n{result.stderr}",
                                       f"Linter-Fehler in {filepath}:\n{result.stdout}\n{result.stderr}")
                except Exception as e:
                    return False, t(f"Failed to execute Python linting (Ruff) for {filepath}: {e}",
                                   f"Ausführung des Python-Linting (Ruff) für {filepath} fehlgeschlagen: {e}")
                    
            # 2. JS/TS Linting (ESLint)
            elif filepath.endswith(('.js', '.ts', '.jsx', '.tsx')):
                if shutil.which("eslint"):
                    try:
                        result = await CommandRunner.run_async(["eslint", "--fix", filepath])
                        if result.returncode != 0:
                            return False, t(f"ESLint error in {filepath}:\n{result.stdout}\n{result.stderr}",
                                           f"ESLint-Fehler in {filepath}:\n{result.stdout}\n{result.stderr}")
                    except OSError as e:
                        console.print(f"[dim]ESLint execution error: {e}[/dim]")
                else:
                    console.print(t(f"[dim]ESLint not found, skipping linting for {filepath}.[/dim]",
                                    f"[dim]ESLint nicht gefunden, überspringe Linting für {filepath}.[/dim]"))
                
        return True, t("Code is error-free.", "Code ist fehlerfrei.")
