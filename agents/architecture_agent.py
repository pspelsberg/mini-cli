import asyncio
from typing import List
from rich.console import Console

from core.models import FileModification
from core.base_agent import BaseAgent
from providers import ProviderFactory
from core.i18n import t

console = Console()

class ArchitectureAgent(BaseAgent):
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Architecture-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def validate_architecture(self, modifications: List[FileModification]) -> tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Checking Clean Architecture principles...",
                        f"[bold yellow][{self.name}][/bold yellow] Prüfe Clean-Architecture-Prinzipien..."))
        await asyncio.sleep(0.5)
        
        if not modifications:
            return True, "Keine Code-Änderungen zu prüfen."

        prompt = (
            "You are a Software Architect. Analyze the following code modifications for Clean Architecture principles "
            "(e.g., Separation of Concerns, dependency directions, SOLID principles).\n"
            "If the architecture is flawed or has serious design issues, reply with "
            "'FAIL: <reason and suggestion for improvement>'.\n"
            "If everything looks clean and correct, reply exactly with 'PASS'.\n\n"
        )
        
        for mod in modifications:
            prompt += f"--- {mod.filepath} ---\n{mod.content}\n\n"
            
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            if result.startswith("FAIL"):
                return False, result
                
        return True, "Architektur ist konform."
