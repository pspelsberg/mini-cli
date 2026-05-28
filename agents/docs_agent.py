import asyncio
from rich.console import Console
from core.base_agent import BaseAgent
from core.models import AgentTask, BuildResponse
from providers import ProviderFactory
from core.i18n import t
from agents.build_agent import _parse_block_format, _parse_json_format, _FILE_START, _MSG_START, _MSG_END, _FILE_END

console = Console()

class DocsAgent(BaseAgent):
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Docs-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def generate_documentation(self, task: AgentTask, context: str) -> BuildResponse:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Generating system documentation (README, docstrings, Mermaid diagrams)...",
                        f"[bold yellow][{self.name}][/bold yellow] Generiere System-Dokumentation (README, Docstrings, Mermaid-Diagramme)..."))

        prompt = (
            f"Du bist ein technischer Redakteur und Software-Architekt. Erfülle die folgende Dokumentations-Aufgabe: {task.description}\n"
            f"Hier ist der Projektkontext:\n{context}\n"
            "Deine Aufgabe ist es, herausragende Dokumentation zu erstellen. Das kann beinhalten:\n"
            "1. Aktualisierung oder Erstellung der README.md\n"
            "2. Hinzufügen von Docstrings (Google- oder Sphinx-Style) in Code-Dateien\n"
            "3. Erstellen von Mermaid.js Diagrammen zur Visualisierung der Architektur\n\n"
            "WICHTIG: ANTWORTE IM FOLGENDEN BLOCK-FORMAT (kein JSON):\n"
            f"{_MSG_START}Kurze Erklärung was dokumentiert wurde{_MSG_END}\n"
            f"{_FILE_START}pfad/zur/datei.md{_MSG_END}\n"
            "...kompletter Dateiinhalt inklusive Dokumentation...\n"
            f"{_FILE_END}\n"
        )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)

        if not response.success:
            return BuildResponse(success=False, message=f"LLM Fehler: {response.message}")

        raw_content = response.code_generated or ""

        result = _parse_block_format(raw_content)
        if result is None:
            result = _parse_json_format(raw_content)
        if result is None:
            return BuildResponse(success=False, message="JSON Parse Fehler bei Dokumentations-Generierung.")

        message, mods = result
        return BuildResponse(success=True, message=message, modifications=mods, tokens_used=response.tokens_used)
