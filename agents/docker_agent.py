import asyncio
from typing import Tuple
from rich.console import Console

from core.base_agent import BaseAgent
from providers import ProviderFactory
from core.i18n import t

console = Console()

class DockerAgent(BaseAgent):
    """
    Skill 15: Docker & Container Orchestration
    Generates optimized Dockerfiles (multi-stage, distroless) and Docker Compose configurations.
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Docker-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def generate_docker_config(self, project_info: str, needs_compose: bool = False) -> Tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Analyzing project and generating container configuration...",
                        f"[bold yellow][{self.name}][/bold yellow] Analysiere Projekt und generiere Container-Konfiguration..."))
        await asyncio.sleep(0.5)

        if not project_info.strip():
            return False, "Keine Projektinformationen zur Docker-Generierung bereitgestellt."

        prompt = (
            "Du bist ein DevOps Engineer und Docker Experte. Generiere eine optimierte Container-Konfiguration "
            "für folgendes Projekt. Nutze Best Practices wie Multi-Stage Builds, Alpine/Distroless Images "
            "und non-root User für maximale Sicherheit und minimale Image-Größe.\n\n"
            f"Projekt-Info:\n{project_info}\n\n"
        )
        
        if needs_compose:
            prompt += (
                "Erstelle zusätzlich eine 'docker-compose.yml', die alle benötigten Services "
                "(App, Datenbank, Cache etc.) intelligent vernetzt.\n"
                "Antworte exakt mit 'DOCKER_CONFIG_GENERATED:\n<Dockerfile und docker-compose.yml code>'."
            )
        else:
            prompt += "Antworte exakt mit 'DOCKER_CONFIG_GENERATED:\n<Dockerfile code>'."

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            if result.startswith("DOCKER_CONFIG_GENERATED"):
                console.print(t("[dim]Docker configuration successfully generated.[/dim]",
                                "[dim]Docker-Konfiguration erfolgreich generiert.[/dim]"))
                return True, result
                
        return False, "Fehler bei der Generierung der Docker-Konfiguration."
