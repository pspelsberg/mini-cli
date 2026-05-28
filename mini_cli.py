import warnings
warnings.filterwarnings("ignore", message=".*lance is not fork-safe.*")

import sys
import os
import asyncio
import typer
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from core.orchestrator import OrchestratorAgent
from core.repl import repl
from core.i18n import t

console = Console()
app = typer.Typer(help="Mini-CLI Agent", add_completion=False)


class Telemetry:
    """Token Management & Telemetry (TUI Footer)"""

    def __init__(self, provider_name: str = "ollama"):
        self.tokens_used = 0
        self.cache_hits = 0
        self.provider_name = provider_name

    def print_footer(self):
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column(t("Metric", "Metrik"), style="dim")
        table.add_column(t("Value", "Wert"))
        table.add_row(t("Tokens Used", "Tokens Verbraucht"), str(self.tokens_used))
        table.add_row(t("Cache-Hits", "Cache-Hits"), str(self.cache_hits))
        table.add_row("Provider", self.provider_name.capitalize())

        console.print("\n")
        console.print(Panel(table, title=t("[bold blue]📊 TELEMETRY[/bold blue]", "[bold blue]📊 TELEMETRIE[/bold blue]")))


def print_banner():
    ascii_art = [
        r"    __  ____       _          ________    ____",
        r"   /  |/  (_)___  (_)        / ____/ /   /  _/",
        r"  / /|_/ / / __ \/ /  ______/ /   / /    / /  ",
        r" / /  / / / / / / /  /_____/ /___/ /____/ /   ",
        r"/_/  /_/_/_/ /_/_/         \____/_____/___/   ",
    ]
    start_color = (156, 39, 176)  # Lila
    end_color = (255, 255, 0)  # Gelb
    text = Text()
    for i, line in enumerate(ascii_art):
        ratio = i / max(1, len(ascii_art) - 1)
        r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
        color = f"#{r:02x}{g:02x}{b:02x}"
        text.append(line + "\n", style=color)
    text.append("\n" + " " * 8 + "Mini-CLI Edition (v1.0)\n", style="#9c27b0")
    console.print(text)


def check_provider_health(provider: str) -> bool:
    import requests
    base_provider = provider.split(":", 1)[0].lower()
    if base_provider == "ollama":
        url = "http://localhost:11434/"
    elif base_provider == "lmstudio":
        url = "http://127.0.0.1:1234/v1/models"
    elif base_provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    elif base_provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    elif base_provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    elif base_provider == "codestral":
        return bool(os.getenv("CODESTRAL_API_KEY") or os.getenv("MISTRAL_API_KEY"))
    else:
        return False
    
    try:
        response = requests.get(url, timeout=2)
        if base_provider == "lmstudio":
            data = response.json()
            if not data.get("data"):
                # No models loaded in LM Studio
                return False
        return True
    except Exception:
        return False


def autodetect_provider(requested: str) -> str:
    if check_provider_health(requested):
        return requested
        
    # Kaskade: Cloud Provider -> LM Studio -> Ollama
    for p in ["openai", "anthropic", "gemini", "codestral"]:
        if check_provider_health(p):
            return p
            
    if check_provider_health("lmstudio"):
        return "lmstudio"
        
    if check_provider_health("ollama"):
        return "ollama"
        
    return None


@app.command()
def task(
    description: str = typer.Argument(None, help="Die Aufgabe für den Agenten"),
    mode: str = typer.Option(None, help="Ausführungsmodus (plan, build, auto)"),
    provider: str = typer.Option(
        None, help="LLM Provider (ollama, gemini, anthropic, openai, lmstudio, codestral)"
    ),
    language: str = typer.Option(
        None, help="Sprache / Language (en, de)"
    ),
):
    """Executes a single task or starts the REPL if no task is specified."""
    print_banner()

    # Query workspace directory
    agent_dir = os.path.abspath(os.path.dirname(__file__))
    
    while True:
        choice = typer.prompt(
            t("Do you want to use an existing project folder or create a new one? (existing/new)", 
              "Möchtest du einen bestehenden Projektordner nutzen oder einen neuen erstellen? (existing/new)"), 
            default="existing"
        ).lower()
        
        if choice in ["new", "neu", "n"]:
            parent_dir = typer.prompt(t("Where should the new folder be located? (e.g. ~/Projects)", "Wo soll der neue Ordner liegen? (z.B. ~/Projects)"), default="~/")
            folder_name = typer.prompt(t("What should the new project be named?", "Wie soll das neue Projekt heißen?"))
            workspace_dir = os.path.abspath(os.path.join(os.path.expanduser(parent_dir), folder_name))
            
            try:
                os.makedirs(workspace_dir, exist_ok=True)
                console.print(t(f"[bold green]✅ Created {workspace_dir}[/bold green]", f"[bold green]✅ Ordner {workspace_dir} erstellt[/bold green]"))
            except Exception as e:
                console.print(t(f"[bold red]Error creating directory: {e}[/bold red]", f"[bold red]Fehler beim Erstellen: {e}[/bold red]"))
                continue
        else:
            workspace_dir = typer.prompt(t("Enter the path to the existing workspace directory", "Gib den Pfad zum bestehenden Workspace-Ordner ein"))
            workspace_dir = os.path.abspath(os.path.expanduser(workspace_dir))
            
            if not os.path.exists(workspace_dir):
                console.print(t(f"[bold red]The directory '{workspace_dir}' does not exist.[/bold red]", f"[bold red]Der Ordner '{workspace_dir}' existiert nicht.[/bold red]"))
                continue
                
        if workspace_dir == agent_dir or workspace_dir.startswith(agent_dir + os.sep):
            console.print(t("[bold red]Error: The agent cannot use its own source code directory as a workspace. Please choose another location.[/bold red]", 
                            "[bold red]Fehler: Der Agent darf seinen eigenen Quellcode-Ordner nicht als Workspace nutzen. Bitte wähle einen anderen Ort.[/bold red]"))
            continue
            
        break
        
    os.chdir(workspace_dir)

    # Load and apply configuration
    from core.i18n import load_config, save_config, set_language
    saved_config = load_config()

    # Resolve language
    if not language:
        language = saved_config.get("language", "en")
    set_language(language)

    # Resolve mode
    if not mode:
        mode = saved_config.get("mode", "plan")

    # Resolve provider
    if not provider:
        provider = saved_config.get("provider", "ollama")

    console.print(t(f"[bold green]✅ Working directory set to: {workspace_dir}[/bold green]\n", f"[bold green]✅ Arbeitsverzeichnis gesetzt auf: {workspace_dir}[/bold green]\n"))

    # Provider auto-detection & fallback cascade
    detected_provider = autodetect_provider(provider)
    if detected_provider:
        if detected_provider != provider:
            console.print(t(f"\n[bold yellow]⚠️  Provider '{provider}' not available. Automatic fallback to '{detected_provider}'.[/bold yellow]\n", f"\n[bold yellow]⚠️  Provider '{provider}' nicht verfügbar. Automatischer Fallback auf '{detected_provider}'.[/bold yellow]\n"))
        provider = detected_provider
    else:
        console.print(t("\n[bold red]⚠️  No local provider (LM Studio/Ollama) reachable and no cloud API keys (OpenAI/Anthropic/Gemini) configured.[/bold red]", "\n[bold red]⚠️  Kein lokaler Provider (LM Studio/Ollama) erreichbar und keine Cloud-API-Keys (OpenAI/Anthropic/Gemini) konfiguriert.[/bold red]"))
        choice = typer.prompt(t("Would you like to manually link a cloud provider? (openai/gemini/anthropic/codestral) or 'no' to exit", "Möchtest du manuell einen Cloud-Provider verknüpfen? (openai/gemini/anthropic/codestral) oder 'nein' zum Beenden"), default="no")
        if choice.lower() in ["openai", "gemini", "anthropic", "codestral"]:
            provider = choice.lower()
            console.print(t(f"[bold green]✅ Switching to {provider}... (Please ensure environment variables are set!)[/bold green]\n", f"[bold green]✅ Wechsle zu {provider}... (Bitte stelle sicher, dass die Umgebungsvariablen in der Shell gesetzt sind!)[/bold green]\n"))
        else:
            console.print(t("[bold red]Aborted. Please start a local provider or export an API key.[/bold red]\n", "[bold red]Abbruch. Bitte starte einen lokalen Provider oder exportiere einen API Key (z.B. OPENAI_API_KEY).[/bold red]\n"))
            sys.exit(1)

    # Unix pipe support
    piped_input = ""
    if not sys.stdin.isatty():
        piped_input = sys.stdin.read().strip()

    if piped_input:
        description = (
            f"{description}\n\n[Piped Input]:\n{piped_input}"
            if description
            else f"Verarbeite Piped Input:\n{piped_input}"
        )

    save_config(language, mode, provider)

    telemetry = Telemetry(provider)
    orchestrator = OrchestratorAgent(provider)

    if description:
        # Run the asynchronous orchestrator
        tokens = asyncio.run(orchestrator.process_task(description, mode))
        telemetry.tokens_used += tokens
    else:
        asyncio.run(repl(orchestrator, telemetry))

    telemetry.print_footer()

if __name__ == "__main__":
    app()
