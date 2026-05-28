import asyncio
from typing import List
from rich.console import Console
from rich.prompt import Confirm
from core.base_agent import BaseAgent
from tools.command_runner import CommandRunner
from core.i18n import t

console = Console()

class GitAgent(BaseAgent):
    def __init__(self):
        self._name = "Git-Agent"

    @property
    def name(self) -> str:
        return self._name

    async def auto_commit(self, task_desc: str, files_modified: List[str]):
        if not files_modified:
            return
            
        console.print(t("\n[bold green]Git Integration:[/bold green] Preparing auto-commit...",
                        "\n[bold green]Git-Integration:[/bold green] Bereite Auto-Commit vor..."))
        for f in files_modified:
            await CommandRunner.run_async(["git", "add", f])
            
        status = await CommandRunner.run_async(["git", "status", "--porcelain"])
        if status.stdout.strip():
            commit_msg = f"Auto-Commit: {task_desc}"
            
            # Confirm.ask is blocking, so run in a thread
            should_commit = await asyncio.to_thread(
                Confirm.ask,
                t(f"Should the changes be committed with message '{commit_msg}'?",
                  f"Sollen die Änderungen mit Message '{commit_msg}' commited werden?")
            )
            
            if should_commit:
                await CommandRunner.run_async(["git", "commit", "-m", commit_msg])
                console.print(t(f"✅ [bold green][{self.name}][/bold green] Changes successfully committed.",
                                f"✅ [bold green][{self.name}][/bold green] Änderungen erfolgreich commited."))
            else:
                console.print(t("[dim]Commit skipped. Changes are in the staging area.[/dim]",
                                "[dim]Commit übersprungen. Änderungen sind in der Staging-Area.[/dim]"))
        else:
            console.print(t("[dim]No changes found for Git.[/dim]",
                            "[dim]Keine Änderungen für Git gefunden.[/dim]"))
