import asyncio
from typing import Tuple
from rich.console import Console

from core.base_agent import BaseAgent
from providers import ProviderFactory
from core.i18n import t

console = Console()

class DatabaseAgent(BaseAgent):
    """
    Skill 16: Database Migration Assistant
    Generates safe schema migrations (Alembic/Prisma/SQL), rollback plans,
    and suggests performance indices.
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Database-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def generate_migration(self, schema_changes: str) -> Tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Analyzing schema changes and generating migration...",
                        f"[bold yellow][{self.name}][/bold yellow] Analysiere Schema-Änderungen und generiere Migration..."))
        await asyncio.sleep(0.5)

        if not schema_changes.strip():
            return False, "Keine Schema-Änderungen bereitgestellt."

        prompt = (
            "Du bist ein Senior Database Administrator. Analysiere die folgenden gewünschten "
            "Änderungen am Datenbank-Schema. Generiere basierend darauf:\n"
            "1. Das Migrations-Skript (Up-Migration, z.B. in SQL oder Alembic).\n"
            "2. Eine sichere Rollback-Strategie (Down-Migration) ohne Datenverlust.\n"
            "3. Vorschläge für Indizes zur Performance-Optimierung.\n\n"
            "Antworte direkt mit dem fertigen Code (als 'MIGRATION_GENERATED:\n<Code>').\n\n"
            f"Gewünschte Änderungen:\n{schema_changes}\n"
        )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            if result.startswith("MIGRATION_GENERATED"):
                console.print(t("[dim]Database migration successfully generated.[/dim]",
                                "[dim]Datenbank-Migration erfolgreich generiert.[/dim]"))
                return True, result
                
        return False, "Fehler bei der Generierung der Datenbank-Migration."
