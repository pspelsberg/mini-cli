import sys
import asyncio
import threading
from rich.console import Console
from rich.panel import Panel
from core.orchestrator import OrchestratorAgent
from core.i18n import t, set_language, get_language, save_config

console = Console()

class StdinReader:
    def __init__(self):
        self.input_queue = asyncio.Queue()
        self.loop = asyncio.get_running_loop()
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        
    def _read_loop(self):
        try:
            for line in sys.stdin:
                self.loop.call_soon_threadsafe(self.input_queue.put_nowait, line)
        except Exception:
            pass

async def repl(orchestrator: OrchestratorAgent, telemetry):
    """Interaktiver REPL Modus mit Unterstützung für 'stop' während der Ausführung"""
    console.print(
        t("[bold]Interactive mode started.[/bold] Type [yellow]'exit'[/yellow] to quit or [yellow]'/help'[/yellow] for menu.",
          "[bold]Interaktiver Modus gestartet.[/bold] Tippe [yellow]'exit'[/yellow] zum Beenden oder [yellow]'/help'[/yellow] für ein Menü.")
    )
    current_mode = "plan"
    
    # StdinReader initialisieren
    stdin_reader = StdinReader()
    
    # Den Stdin-Queue an den UIReporter übergeben, damit dieser auch asynchron lesen kann
    if hasattr(orchestrator, "ui"):
        orchestrator.ui.stdin_queue = stdin_reader.input_queue

    while True:
        try:
            # Flush queue to clear any stale input (e.g. keypresses while agent was running that weren't stop)
            while not stdin_reader.input_queue.empty():
                try:
                    stdin_reader.input_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # Prompt anzeigen in Lila (magenta) / Gelb (yellow) abwechselnd
            console.print(f"[bold yellow]M[/][bold magenta]i[/][bold yellow]n[/][bold magenta]i[/][bold yellow]-[/][bold magenta]C[/][bold yellow]L[/][bold magenta]I[/] [yellow]([/yellow][magenta]{telemetry.provider_name}[/magenta][yellow]|[/yellow][magenta]{current_mode}[/magenta][yellow])>[/yellow] ", end="")
            
            # asynchrone Eingabe lesen
            task_desc = await stdin_reader.input_queue.get()
            task_desc = task_desc.strip()
            
            if task_desc.lower() in ["exit", "quit"]:
                break
            if not task_desc.strip():
                continue

            # Slash-Commands Menu verarbeiten
            if task_desc.startswith("/"):
                parts = task_desc.split(" ", 1)
                cmd = parts[0].lower()
                arg = parts[1].strip() if len(parts) > 1 else ""

                if cmd == "/help":
                    help_en = (
                        "[yellow]/help[/yellow]            - Show this menu\n"
                        "[yellow]/provider <name>[/yellow] - Switch provider (ollama, gemini, anthropic, openai, lmstudio, codestral)\n"
                        "[yellow]/model <name>[/yellow]    - Switch model for current provider (e.g., gemini-1.5-pro, gpt-4o)\n"
                        "[yellow]/agentmodel[/yellow]     - Configure provider/model for specific agents\n"
                        "[yellow]/mode <name>[/yellow]     - Switch mode (plan, build, auto)\n"
                        "[yellow]/language <lang>[/yellow] - Switch language (en, de)\n"
                        "[yellow]/verify[/yellow]          - Run system verification check\n"
                        "[yellow]exit[/yellow]             - Exit CLI"
                    )
                    help_de = (
                        "[yellow]/help[/yellow]            - Zeigt dieses Menü an\n"
                        "[yellow]/provider <name>[/yellow] - Wechselt den Provider (ollama, gemini, anthropic, openai, lmstudio, codestral)\n"
                        "[yellow]/model <name>[/yellow]    - Wechselt das Modell des aktuellen Providers (z.B. gemini-1.5-pro, gpt-4o)\n"
                        "[yellow]/agentmodel[/yellow]     - Konfiguriert Provider/Modell für spezifische Agenten\n"
                        "[yellow]/mode <name>[/yellow]     - Wechselt den Modus (plan, build, auto)\n"
                        "[yellow]/language <lang>[/yellow] - Wechselt die Sprache (en, de)\n"
                        "[yellow]/verify[/yellow]          - Führt eine System-Verifizierung durch\n"
                        "[yellow]exit[/yellow]             - Beendet die CLI"
                    )
                    console.print(Panel(
                        t(help_en, help_de),
                        title=t("[bold blue]🛠️ Available Commands[/bold blue]", "[bold blue]🛠️ Verfügbare Befehle[/bold blue]"),
                        expand=False
                    ))
                    continue
                elif cmd == "/language":
                    if arg in ["en", "de"]:
                        set_language(arg)
                        save_config(arg, current_mode, telemetry.provider_name)
                        console.print(t(f"[bold green]✅ Language successfully switched to '{arg}'.[/bold green]",
                                         f"[bold green]✅ Sprache erfolgreich auf '{arg}' gewechselt.[/bold green]"))
                    else:
                        console.print(t("[bold red]❌ Unknown language.[/bold red] Choose: en, de",
                                        "[bold red]❌ Unbekannte Sprache.[/bold red] Wähle aus: en, de"))
                    continue
                elif cmd == "/provider":
                    valid_providers = ["ollama", "gemini", "anthropic", "openai", "lmstudio", "codestral"]
                    base_provider = arg.split(":", 1)[0].lower()
                    if base_provider in valid_providers:
                        orchestrator = OrchestratorAgent(arg)
                        # Den Stdin-Queue auch an das neue Orchestrator-Instanz übergeben
                        if hasattr(orchestrator, "ui"):
                            orchestrator.ui.stdin_queue = stdin_reader.input_queue
                        telemetry.provider_name = arg
                        save_config(get_language(), current_mode, arg)
                        console.print(t(f"[bold green]✅ Provider successfully switched to '{arg}'.[/bold green]",
                                         f"[bold green]✅ Provider erfolgreich auf '{arg}' gewechselt.[/bold green]"))
                    else:
                        console.print(t(f"[bold red]❌ Unknown provider.[/bold red] Choose from: {', '.join(valid_providers)}",
                                        f"[bold red]❌ Unbekannter Provider.[/bold red] Wähle aus: {', '.join(valid_providers)}"))
                    continue
                elif cmd == "/model":
                    current_provider = telemetry.provider_name.split(":", 1)[0].lower()
                    from providers import ProviderFactory
                    try:
                        p_inst = ProviderFactory.get_provider(current_provider)
                        models_list = p_inst.get_available_models()
                    except Exception as e:
                        console.print(t(f"[bold red]❌ Failed to retrieve models: {e}[/bold red]",
                                        f"[bold red]❌ Modelle konnten nicht abgerufen werden: {e}[/bold red]"))
                        continue

                    if arg:
                        new_model = arg
                    else:
                        if not models_list:
                            console.print(t("[bold red]❌ No models found for this provider.[/bold red]",
                                            "[bold red]❌ Keine Modelle für diesen Provider gefunden.[/bold red]"))
                            continue

                        from rich.table import Table
                        table = Table(show_header=True, header_style="bold cyan", expand=False)
                        table.add_column(t("No.", "Nr."))
                        table.add_column(t("Model Name", "Modellname"))
                        for idx, m_name in enumerate(models_list, 1):
                            table.add_row(str(idx), m_name)
                        
                        console.print(Panel(
                            table,
                            title=t(f"[bold blue]🤖 Available Models for {current_provider}[/bold blue]",
                                    f"[bold blue]🤖 Verfügbare Modelle für {current_provider}[/bold blue]"),
                            expand=False
                        ))

                        prompt_text = t("Select a model number, type a model name, or press Enter to cancel: ",
                                        "Wähle eine Nummer, tippe einen Modellnamen ein oder drücke Enter zum Abbrechen: ")
                        console.print(prompt_text, end="")
                        try:
                            selection = await stdin_reader.input_queue.get()
                            selection = selection.strip()
                        except (KeyboardInterrupt, asyncio.CancelledError):
                            selection = ""

                        if not selection:
                            console.print(t("[yellow]Selection cancelled.[/yellow]", "[yellow]Auswahl abgebrochen.[/yellow]"))
                            continue

                        if selection.isdigit():
                            idx = int(selection) - 1
                            if 0 <= idx < len(models_list):
                                new_model = models_list[idx]
                            else:
                                console.print(t("[bold red]❌ Invalid number.[/bold red]", "[bold red]❌ Ungültige Nummer.[/bold red]"))
                                continue
                        else:
                            new_model = selection

                    new_provider_str = f"{current_provider}:{new_model}"
                    orchestrator = OrchestratorAgent(new_provider_str)
                    if hasattr(orchestrator, "ui"):
                        orchestrator.ui.stdin_queue = stdin_reader.input_queue
                    telemetry.provider_name = new_provider_str
                    save_config(get_language(), current_mode, new_provider_str)
                    console.print(t(f"[bold green]✅ Model successfully set to '{new_model}' (Provider: '{current_provider}').[/bold green]",
                                    f"[bold green]✅ Modell erfolgreich auf '{new_model}' gesetzt (Provider: '{current_provider}').[/bold green]"))
                    continue
                elif cmd == "/mode":
                    if arg in ["plan", "build", "auto"]:
                        current_mode = arg
                        save_config(get_language(), arg, telemetry.provider_name)
                        console.print(t(f"[bold green]✅ Mode successfully switched to '{arg}'.[/bold green]",
                                         f"[bold green]✅ Modus erfolgreich auf '{arg}' gewechselt.[/bold green]"))
                    else:
                        console.print(t("[bold red]❌ Unknown mode.[/bold red] Choose from: plan, build, auto",
                                        "[bold red]❌ Unbekannter Modus.[/bold red] Wähle aus: plan, build, auto"))
                    continue
                elif cmd == "/agentmodel":
                    # Get list of agents requiring provider
                    from core.orchestrator import AGENT_REGISTRY
                    provider_agents = [name for name, info in AGENT_REGISTRY.items() if info[2]]
                    
                    from rich.table import Table
                    table = Table(show_header=True, header_style="bold cyan", expand=False)
                    table.add_column(t("No.", "Nr."))
                    table.add_column(t("Agent Name", "Agent-Name"))
                    table.add_column(t("Current Provider / Model", "Aktueller Provider / Modell"))
                    
                    for idx, name in enumerate(provider_agents, 1):
                        curr = orchestrator.agent_providers.get(name, f"{orchestrator.provider_name} (Default)")
                        table.add_row(str(idx), f"{name.capitalize()}Agent", curr)
                        
                    console.print(Panel(
                        table,
                        title=t("[bold blue]🤖 Configure Agent Models[/bold blue]", "[bold blue]🤖 Agent-Modelle konfigurieren[/bold blue]"),
                        expand=False
                    ))
                    
                    console.print(t("Select an Agent by number, name, or press Enter to cancel: ",
                                    "Wähle einen Agenten nach Nummer, Name oder drücke Enter zum Abbrechen: "), end="")
                    try:
                        selection = await stdin_reader.input_queue.get()
                        selection = selection.strip()
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        selection = ""
                        
                    if not selection:
                        console.print(t("[yellow]Selection cancelled.[/yellow]", "[yellow]Auswahl abgebrochen.[/yellow]"))
                        continue
                        
                    selected_agent = None
                    if selection.isdigit():
                        idx = int(selection) - 1
                        if 0 <= idx < len(provider_agents):
                            selected_agent = provider_agents[idx]
                    else:
                        norm_sel = selection.lower().replace("agent", "")
                        if norm_sel in provider_agents:
                            selected_agent = norm_sel
                            
                    if not selected_agent:
                        console.print(t("[bold red]❌ Invalid Agent selection.[/bold red]", "[bold red]❌ Ungültige Agenten-Auswahl.[/bold red]"))
                        continue
                        
                    # Now select provider
                    valid_providers = ["ollama", "gemini", "anthropic", "openai", "lmstudio", "codestral"]
                    console.print(t(f"Select a provider for {selected_agent.capitalize()}Agent ({', '.join(valid_providers)}): ",
                                    f"Wähle einen Provider für {selected_agent.capitalize()}Agent ({', '.join(valid_providers)}): "), end="")
                    try:
                        prov_sel = await stdin_reader.input_queue.get()
                        prov_sel = prov_sel.strip().lower()
                    except (KeyboardInterrupt, asyncio.CancelledError):
                        prov_sel = ""
                        
                    if not prov_sel:
                        console.print(t("[yellow]Selection cancelled.[/yellow]", "[yellow]Auswahl abgebrochen.[/yellow]"))
                        continue
                        
                    base_provider = prov_sel.split(":", 1)[0].lower()
                    if base_provider not in valid_providers:
                        console.print(t(f"[bold red]❌ Unknown provider: '{prov_sel}'.[/bold red]",
                                        f"[bold red]❌ Unbekannter Provider: '{prov_sel}'.[/bold red]"))
                        continue
                        
                    # Now fetch models for the selected provider
                    from providers import ProviderFactory
                    try:
                        p_inst = ProviderFactory.get_provider(base_provider)
                        models_list = p_inst.get_available_models()
                    except Exception as e:
                        console.print(t(f"[bold red]❌ Failed to retrieve models: {e}[/bold red]",
                                        f"[bold red]❌ Modelle konnten nicht abgerufen werden: {e}[/bold red]"))
                        continue
                        
                    new_model = ""
                    if models_list:
                        m_table = Table(show_header=True, header_style="bold cyan", expand=False)
                        m_table.add_column(t("No.", "Nr."))
                        m_table.add_column(t("Model Name", "Modellname"))
                        for idx, m_name in enumerate(models_list, 1):
                            m_table.add_row(str(idx), m_name)
                            
                        console.print(Panel(
                            m_table,
                            title=t(f"🤖 Available Models for {base_provider}", f"🤖 Verfügbare Modelle für {base_provider}"),
                            expand=False
                        ))
                        
                        console.print(t("Select a model number, type a name, or press Enter for default: ",
                                        "Wähle eine Nummer, tippe einen Namen ein oder drücke Enter für Default: "), end="")
                        try:
                            model_sel = await stdin_reader.input_queue.get()
                            model_sel = model_sel.strip()
                        except (KeyboardInterrupt, asyncio.CancelledError):
                            model_sel = ""
                            
                        if model_sel:
                            if model_sel.isdigit():
                                m_idx = int(model_sel) - 1
                                if 0 <= m_idx < len(models_list):
                                    new_model = models_list[m_idx]
                                else:
                                    console.print(t("[bold red]❌ Invalid number.[/bold red]", "[bold red]❌ Ungültige Nummer.[/bold red]"))
                                    continue
                            else:
                                new_model = model_sel
                                
                    new_agent_provider = f"{base_provider}:{new_model}" if new_model else base_provider
                    
                    # Apply changes to orchestrator
                    orchestrator.agent_providers[selected_agent] = new_agent_provider
                    if selected_agent in orchestrator._agents:
                        del orchestrator._agents[selected_agent]
                        
                    save_config(get_language(), current_mode, telemetry.provider_name, orchestrator.agent_providers)
                    console.print(t(f"[bold green]✅ {selected_agent.capitalize()}Agent successfully set to '{new_agent_provider}'.[/bold green]",
                                     f"[bold green]✅ {selected_agent.capitalize()}Agent erfolgreich auf '{new_agent_provider}' gesetzt.[/bold green]"))
                    continue
                elif cmd == "/verify":
                    console.print(t("[bold yellow]Running system verification...[/bold yellow]",
                                    "[bold yellow]Führe System-Verifizierung aus...[/bold yellow]"))
                    success, msg = await orchestrator.verify_agent.verify_system()
                    if success:
                        console.print(f"[bold green]✅ {msg}[/bold green]")
                    else:
                        console.print(f"[bold red]❌ System verification failed:\n{msg}[/bold red]")
                    continue
                else:
                    console.print(t(f"[bold red]❌ Unknown command: {cmd}.[/bold red] Type /help for a list.",
                                    f"[bold red]❌ Unbekannter Befehl: {cmd}.[/bold red] Tippe /help für eine Liste."))
                    continue

            # Flush queue to clear any stale inputs before processing
            while not stdin_reader.input_queue.empty():
                try:
                    stdin_reader.input_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # Task asynchron starten
            processing_task = asyncio.create_task(orchestrator.process_task(task_desc, mode=current_mode))
            
            try:
                while not processing_task.done():
                    # Wenn der Orchestrator gerade auf eine Eingabe wartet, schlafen wir kurz
                    if getattr(orchestrator.ui, "is_prompting", False):
                        await asyncio.sleep(0.1)
                        continue
                        
                    stdin_task = asyncio.create_task(stdin_reader.input_queue.get())
                    
                    done, pending = await asyncio.wait(
                        [processing_task, stdin_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    for t_item in done:
                        if t_item == processing_task:
                            try:
                                tokens = t_item.result()
                                telemetry.tokens_used += tokens
                            except asyncio.CancelledError:
                                pass
                            except Exception as e:
                                console.print(f"[bold red]Error during task execution: {e}[/bold red]")
                        else:
                            # User has entered input
                            typed_input = t_item.result()
                            if getattr(orchestrator.ui, "is_prompting", False):
                                orchestrator.ui.stdin_queue.put_nowait(typed_input)
                                continue
                            typed_input = typed_input.strip()
                            if typed_input.lower() == "stop":
                                console.print(t("\n[bold red]Stopping agent execution...[/bold red]", 
                                                "\n[bold red]Stoppe Agenten-Ausführung...[/bold red]"))
                                processing_task.cancel()
                                try:
                                    await processing_task
                                except asyncio.CancelledError:
                                    pass
                            else:
                                console.print(t("\n[yellow]Agent is running. Type 'stop' to abort.[/yellow]", 
                                                "\n[yellow]Agent läuft gerade. Tippe 'stop' zum Abbrechen.[/yellow]"))
                    
                    for t_item in pending:
                        if t_item != processing_task:
                            t_item.cancel()
            except KeyboardInterrupt:
                console.print(t("\n[bold red]Cancelled by user (Ctrl+C).[/bold red]", 
                                "\n[bold red]Durch Benutzer abgebrochen (Ctrl+C).[/bold red]"))
                processing_task.cancel()
                try:
                    await processing_task
                except asyncio.CancelledError:
                    pass

        except KeyboardInterrupt:
            break
        except EOFError:
            break

