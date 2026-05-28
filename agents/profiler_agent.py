import asyncio
from typing import List, Tuple
from rich.console import Console

from core.models import FileModification
from core.base_agent import BaseAgent
from providers import ProviderFactory
from core.i18n import t

console = Console()

class ProfilerAgent(BaseAgent):
    """
    Skill 8: Performance Profiling
    Identifies bottlenecks and inefficient data structures.
    Performs (simulated) performance checks.
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Profiler-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def profile_code(self, modifications: List[FileModification]) -> Tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Performing performance profiling...",
                        f"[bold yellow][{self.name}][/bold yellow] Führe Performance-Analyse durch..."))
        await asyncio.sleep(0.5)

        if not modifications:
            return True, "Keine Code-Änderungen zum Profilen."

        prompt = (
            "Du bist ein Performance-Experte. Analysiere den folgenden Code auf potenzielle Engpässe "
            "(z.B. O(N^2) Schleifen, ineffiziente Lookups, fehlendes Caching).\n"
            "Schlage effizientere Datenstrukturen oder Algorithmen vor.\n"
            "Wenn du gravierende Leistungsprobleme findest, antworte mit 'BOTTLENECK: <Grund>'.\n"
            "Wenn die Performance angemessen erscheint, antworte exakt mit 'PASS'.\n\n"
        )
        
        for mod in modifications:
            prompt += f"--- {mod.filepath} ---\n{mod.content}\n\n"
            
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            if result.startswith("BOTTLENECK"):
                return False, result
                
        return True, "Keine kritischen Performance-Engpässe gefunden."
