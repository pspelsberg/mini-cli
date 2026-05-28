import asyncio
from typing import List, Tuple
from rich.console import Console

from core.models import FileModification
from core.base_agent import BaseAgent
from providers import ProviderFactory
from core.i18n import t, get_language

console = Console()

class FrontendAgent(BaseAgent):
    """
    Skill 3: Frontend Design Polish
    Analyzes UI code for design consistency, responsiveness, and accessibility (A11y).
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Frontend-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def polish_design(self, modifications: List[FileModification]) -> Tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Performing frontend design polish (A11y, responsiveness)...",
                        f"[bold yellow][{self.name}][/bold yellow] Führe Frontend-Design-Feinschliff durch (A11y, Responsivität)..."))
        await asyncio.sleep(0.5)

        if not modifications:
            return True, "Keine Code-Änderungen zu prüfen."

        lang = get_language()
        if lang == "de":
            prompt = (
                "Du bist ein Frontend- und UX-Experte. Prüfe den folgenden UI-Code (HTML/CSS/JS/React/Vue etc.) auf:\n"
                "1. Visuelle Hierarchie und konsistentes Design-System (z.B. Tailwind-Klassen).\n"
                "2. Responsivität (Mobile-First-Ansatz).\n"
                "3. Barrierefreiheit / A11y (ARIA-Labels, Kontrast, Tastaturnavigation).\n"
                "Wenn gravierende Accessibility-Mängel oder Layout-Brüche bestehen, antworte mit 'DESIGN_FAIL: <Grund und Lösung>'.\n"
                "Wenn alles gut aussieht, antworte exakt mit 'PASS'.\n\n"
            )
        else:
            prompt = (
                "You are a frontend and UX expert. Review the following UI code (HTML/CSS/JS/React/Vue etc.) for:\n"
                "1. Visual hierarchy and consistent design system (e.g. Tailwind classes).\n"
                "2. Responsiveness (mobile-first approach).\n"
                "3. Accessibility / A11y (ARIA labels, contrast, keyboard navigation).\n"
                "If there are serious accessibility issues or layout breaks, reply with 'DESIGN_FAIL: <Reason and solution>'.\n"
                "If everything looks good, reply exactly with 'PASS'.\n\n"
            )
        
        for mod in modifications:
            prompt += f"--- {mod.filepath} ---\n{mod.content}\n\n"
            
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            if result.startswith("DESIGN_FAIL"):
                return False, result
                
        return True, "Frontend-Design-Prüfung bestanden. Responsivität und A11y in Ordnung."
