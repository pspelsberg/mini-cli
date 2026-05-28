import asyncio
from typing import List, Tuple
from rich.console import Console

from core.models import FileModification
from core.base_agent import BaseAgent
from providers import ProviderFactory
from core.i18n import t

console = Console()

class DependencyAgent(BaseAgent):
    """
    Skill 17: Dependency & Update Manager
    Prevents dependency hell, updates libraries, and conducts security audits.
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Dependency-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def analyze_dependencies(self, modifications: List[FileModification]) -> Tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Running dependency audit and update check...",
                        f"[bold yellow][{self.name}][/bold yellow] Führe Dependency-Audit und Update-Check durch..."))
        await asyncio.sleep(0.5)

        if not modifications:
            return True, "Keine Code-Änderungen für den Dependency-Check."

        prompt = (
            "Du bist ein DevOps und Dependency-Management Experte. Analysiere die folgenden Dependency-Dateien "
            "(z.B. requirements.txt, package.json, Cargo.toml):\n"
            "1. Identifiziere veraltete Versionen.\n"
            "2. Finde potenzielle Versionskonflikte (Dependency Hell).\n"
            "3. Prüfe auf bekannte Sicherheitslücken (CVEs) in den angegebenen Versionen.\n"
            "Antworte direkt mit aktualisierten Dependency-Deklarationen (als 'DEPENDENCIES_UPDATED: <code...>').\n"
            "Wenn alle Abhängigkeiten sicher und aktuell sind, antworte exakt mit 'PASS'.\n\n"
        )
        
        has_dependencies = False
        for mod in modifications:
            if any(req_file in mod.filepath for req_file in ["requirements.txt", "package.json", "Cargo.toml", "pyproject.toml", "pom.xml", "build.gradle"]):
                prompt += f"--- {mod.filepath} ---\n{mod.content}\n\n"
                has_dependencies = True
            
        if not has_dependencies:
             return True, "Keine relevanten Dependency-Dateien gefunden."

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            if result.startswith("DEPENDENCIES_UPDATED"):
                return False, result
                
        return True, "Abhängigkeiten sind sicher und aktuell."
