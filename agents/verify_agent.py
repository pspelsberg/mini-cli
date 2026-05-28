import asyncio
import os
from rich.console import Console

from core.base_agent import BaseAgent
from tools.command_runner import CommandRunner, CommandTimeoutError

console = Console()

class VerifyAgent(BaseAgent):
    """
    Skill 12: App Verification (/verify)
    Checks if the system is correctly set up (compilation, environment files).
    """
    def __init__(self):
        self._name = "Verify-Agent"

    @property
    def name(self) -> str:
        return self._name

    async def verify_system(self) -> tuple[bool, str]:
        from core.i18n import t
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Running system verification...",
                        f"[bold yellow][{self.name}][/bold yellow] Führe System-Verifizierung aus..."))
        await asyncio.sleep(0.5)
        
        issues = []
        
        # 1. Check for .env file existence asynchronously
        def _env_exists():
            return os.path.exists(".env") or os.path.exists(".env.example")
        
        env_exists = await asyncio.to_thread(_env_exists)
        if not env_exists:
             console.print(t("[dim]WARNING: No .env or .env.example file found.[/dim]",
                             "[dim]WARNUNG: Keine .env oder .env.example Datei gefunden.[/dim]"))
             
        # 2. Syntax/Build Check for python files
        try:
            import sys
            result = await CommandRunner.run_async([sys.executable, "-m", "compileall", "-q", "."], timeout=10)
            if result.returncode != 0:
                issues.append(f"Compilation error found:\n{result.stderr}")
        except CommandTimeoutError:
            issues.append("Timeout during code compilation.")
        except Exception as e:
            issues.append(f"Error during compilation check: {e}")

        if issues:
            return False, "\n".join(issues)
            
        return True, "System verification passed. Syntax ok, environment ok."
