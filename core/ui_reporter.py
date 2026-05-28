import asyncio
import difflib
from contextlib import asynccontextmanager
from rich.console import Console
from rich.prompt import Prompt
from rich.status import Status
from rich.syntax import Syntax
from rich.panel import Panel
from core.i18n import t
from core.models import FileModification


class UIReporter:
    """Handles all console interactions and UI elements."""
    
    def __init__(self, console: Console = None):
        self.console = console or Console()
        self.is_prompting = False
        self.stdin_queue = None

    def info(self, msg_en: str, msg_de: str, **kwargs) -> None:
        self.console.print(t(msg_en, msg_de), **kwargs)

    def warning(self, msg_en: str, msg_de: str) -> None:
        self.console.print(t(f"⚠️ [bold yellow]{msg_en}[/bold yellow]", f"⚠️ [bold yellow]{msg_de}[/bold yellow]"))

    def error(self, msg_en: str, msg_de: str) -> None:
        self.console.print(t(f"❌ [bold red]{msg_en}[/bold red]", f"❌ [bold red]{msg_de}[/bold red]"))

    def success(self, msg_en: str, msg_de: str) -> None:
        self.console.print(t(f"✅ [bold green]{msg_en}[/bold green]", f"✅ [bold green]{msg_de}[/bold green]"))

    def step(self, msg_en: str, msg_de: str) -> None:
        self.console.print(t(f"   -> {msg_en}", f"   -> {msg_de}"))

    def show_security_block(self, filepath: str) -> None:
        self.error(f"Security Block: Path '{filepath}' is outside the workspace!",
                   f"Sicherheits-Blockade: Pfad '{filepath}' liegt außerhalb des Workspaces!")

    def show_plan_mode(self, mod: FileModification) -> None:
        self.info(f"\n[bold green]PLAN-MODE: Proposal for {mod.filepath}[/bold green]",
                  f"\n[bold green]PLAN-MODUS: Vorschlag für {mod.filepath}[/bold green]")
        syntax = Syntax(mod.content, "python", theme="monokai", line_numbers=True)
        self.console.print(Panel(syntax, title=mod.filepath, expand=False))
        self.info("[dim]Filesystem was not touched. Run with --mode build to apply changes.[/dim]",
                  "[dim]Dateisystem wurde nicht berührt. Starte mit --mode build um Änderungen anzuwenden.[/dim]")
            
    def show_diff(self, old_content: str, mod: FileModification) -> None:
        diff = list(difflib.unified_diff(
            old_content.splitlines(),
            mod.content.splitlines(),
            fromfile=f"a/{mod.filepath}",
            tofile=f"b/{mod.filepath}",
            lineterm=""
        ))
        if diff:
            diff_text = "\n".join(diff)
            syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
            self.console.print(Panel(syntax, title=f"Diff: {mod.filepath}", expand=False))
        else:
            self.info(f"[dim]No changes in {mod.filepath}[/dim]",
                      f"[dim]Keine Änderungen in {mod.filepath}[/dim]")
                    
    async def ask_confirm(self, prompt_str: str, default: str = "y") -> bool:
        self.is_prompting = True
        try:
            if getattr(self, "stdin_queue", None) is not None:
                self.console.print(prompt_str, end="")
                try:
                    answer = await self.stdin_queue.get()
                    answer = answer.strip()
                    if answer.lower() == "stop":
                        self.console.print(t("\n[bold red]Stopping agent execution...[/bold red]", 
                                             "\n[bold red]Stoppe Agenten-Ausführung...[/bold red]"))
                        raise asyncio.CancelledError()
                    if not answer:
                        answer = default
                except (KeyboardInterrupt, asyncio.CancelledError) as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise
                    answer = "n"
            else:
                def _ask():
                    return Prompt.ask(prompt_str, choices=["y", "n"], default=default)
                answer = await asyncio.to_thread(_ask)
        finally:
            self.is_prompting = False
            
        return answer.lower() == 'y'

    async def ask_to_apply(self, filepath: str) -> bool:
        prompt_str = t(f"Apply changes to {filepath}? (y/n) [y]: ",
                       f"Änderungen für {filepath} übernehmen? (y/n) [y]: ")
        return await self.ask_confirm(prompt_str)

    async def ask_question(self, question_str: str) -> str:
        self.is_prompting = True
        try:
            if getattr(self, "stdin_queue", None) is not None:
                self.console.print(f"[bold yellow]? {question_str}[/bold yellow] ", end="")
                try:
                    answer = await self.stdin_queue.get()
                    answer = answer.strip()
                    if answer.lower() == "stop":
                        raise asyncio.CancelledError()
                except (KeyboardInterrupt, asyncio.CancelledError):
                    raise
            else:
                def _ask():
                    return Prompt.ask(f"[bold yellow]? {question_str}[/bold yellow]")
                answer = await asyncio.to_thread(_ask)
        finally:
            self.is_prompting = False
        return answer
        
    def show_skip(self, filepath: str) -> None:
        self.info(f"[dim]Skipping file: {filepath}[/dim]",
                  f"[dim]Überspringe Datei: {filepath}[/dim]")

    def show_auto_write(self, filepath: str) -> None:
        self.info(f"[bold yellow]AUTO-MODE: Automatically overwriting file {filepath}...[/bold yellow]",
                  f"[bold yellow]AUTO-MODUS: Überschreibe Datei {filepath} automatisch...[/bold yellow]")

    def show_writing(self, filepath: str) -> None:
        self.step(f"Writing file {filepath}...",
                  f"Schreibe Datei {filepath}...")
                             
    def show_up_to_date(self, filepath: str) -> None:
        self.info(f"[dim]File {filepath} is already up to date.[/dim]",
                  f"[dim]Datei {filepath} ist bereits aktuell.[/dim]")
                             
    def show_io_error(self, filepath: str, error: Exception) -> None:
        self.error(f"I/O Error while processing {filepath}: {error}",
                   f"Fehler beim Verarbeiten von Datei {filepath}: {error}")

    @asynccontextmanager
    async def spin(self, msg_en: str, msg_de: str):
        label = t(f"[cyan]{msg_en}[/cyan]", f"[cyan]{msg_de}[/cyan]")
        with Status(label, console=self.console, spinner="dots") as status:  # noqa: F841
            try:
                yield status
            finally:
                pass  # Status.__exit__ handles cleanup
