import asyncio
from typing import Tuple
from rich.console import Console

from core.base_agent import BaseAgent
from providers import ProviderFactory
from core.i18n import t

from core.models import FileModification
from agents.build_agent import _parse_block_format, _FILE_START, _MSG_START, _MSG_END, _FILE_END

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
            "ANTWORTE IM FOLGENDEN BLOCK-FORMAT:\n"
            f"{_MSG_START}Container configuration generated{_MSG_END}\n"
            f"{_FILE_START}Dockerfile{_MSG_END}\n"
            "# Dockerfile content\n"
            f"{_FILE_END}\n"
        )
        
        if needs_compose:
            prompt += (
                f"{_FILE_START}docker-compose.yml{_MSG_END}\n"
                "# docker-compose.yml content\n"
                f"{_FILE_END}\n"
            )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            console.print(t("[dim]Docker configuration successfully generated.[/dim]",
                            "[dim]Docker-Konfiguration erfolgreich generiert.[/dim]"))
            return True, result
                
        return False, "Fehler bei der Generierung der Docker-Konfiguration."
