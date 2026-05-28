import asyncio
from typing import List, Tuple
from rich.console import Console

from core.models import FileModification
from core.base_agent import BaseAgent
from providers import ProviderFactory

console = Console()

class ApiAgent(BaseAgent):
    """
    Skill 5: API-Generator & Type Safety
    Generates types, interfaces, and validation logic (e.g., Pydantic, Zod) 
    for API endpoints.
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "API-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def generate_types(self, modifications: List[FileModification]) -> Tuple[bool, str]:
        console.print(f"[bold yellow][{self.name}][/bold yellow] Analysiere Code und generiere Typ-Sicherheit/Validierung...")
        await asyncio.sleep(0.5)

        if not modifications:
            return True, "Keine Code-Änderungen für die Typ-Generierung."

        prompt = (
            "Du bist ein Backend- und API-Architektur-Experte. Analysiere den folgenden Code "
            "(z.B. JSON-Daten, Controller-Methoden oder Swagger-Dumps) und generiere:\n"
            "1. Strikte Typen (TypeScript Interfaces, Rust Structs oder Python Dataclasses).\n"
            "2. Validierungs-Code (z.B. Zod Schemas oder Pydantic Models).\n"
            "3. Kurze API-Dokumentation (Docstrings oder OpenAPI Annotations).\n"
            "Antworte direkt mit dem fertigen Code (als 'TYPES_GENERATED: <code...>').\n"
            "Wenn der Code bereits perfekt typisiert ist, antworte exakt mit 'PASS'.\n\n"
        )
        
        for mod in modifications:
            prompt += f"--- {mod.filepath} ---\n{mod.content}\n\n"
            
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            if result.startswith("TYPES_GENERATED"):
                return False, result # false = Code muss eingefügt werden
                
        return True, "Typ-Sicherheit bereits gewährleistet oder generiert."
