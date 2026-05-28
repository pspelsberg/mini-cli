import asyncio
import os
from pathlib import Path
from typing import Tuple
from rich.console import Console
from rich.prompt import Confirm

from core.base_agent import BaseAgent
from providers import ProviderFactory

console = Console()

class SkillCreatorAgent(BaseAgent):
    """
    Skill 18: Skill-Creator (Meta-Skill)
    Enables the agent to design new skills (as Python agents)
    and integrate them into its own system using Human-in-the-Loop (HITL).
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Skill-Creator"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def execute(self, task_description: str, *args, **kwargs) -> Tuple[bool, str]:
        return await self.create_skill(task_description)

    async def create_skill(self, requirement: str) -> Tuple[bool, str]:
        console.print(f"[bold yellow][{self.name}][/bold yellow] Designing new skill based on requirements...")
        await asyncio.sleep(0.5)

        # 1. Design summary and architecture for the new skill
        plan_prompt = (
            "Du bist ein Meta-Agent (Skill-Creator). Der Nutzer möchte eine neue Fähigkeit hinzufügen:\n"
            f"Anforderung: '{requirement}'\n\n"
            "Erstelle eine prägnante Zusammenfassung (max. 3 Sätze) was der Skill tun wird, "
            "welchen Dateinamen (z.B. 'agents/my_new_agent.py') er haben wird.\n"
            "Antworte im Format:\n"
            "DATEI: agents/<name>.py\n"
            "ZUSAMMENFASSUNG: <deine zusammenfassung>"
        )

        loop = asyncio.get_event_loop()
        plan_res = await loop.run_in_executor(None, self.provider.generate, plan_prompt)
        
        if not plan_res.success:
            return False, f"Planning failed: {plan_res.message}"

        plan_text = plan_res.code_generated or plan_res.message
        
        # Parse file name and summary
        file_name = "agents/new_skill_agent.py"
        summary = plan_text
        for line in plan_text.split('\n'):
            if line.startswith("DATEI:"):
                file_name = line.replace("DATEI:", "").strip()
            elif line.startswith("ZUSAMSENFASSUNG:") or line.startswith("ZUSAMMENFASSUNG:"):
                summary = line.replace("ZUSAMMENFASSUNG:", "").replace("ZUSAMSENFASSUNG:", "").strip()

        # Path safety validation to prevent Arbitrary File Write / Path Traversal
        try:
            workspace_dir = Path(os.getcwd()).resolve()
            # If path is relative, resolving it makes it absolute relative to cwd
            target_path = Path(file_name).resolve()
            if not target_path.is_relative_to(workspace_dir):
                return False, f"Security Block: Target path '{file_name}' is outside the workspace!"
        except Exception as e:
            return False, f"Path validation error: {e}"

        # 2. Human-in-the-Loop (HITL)
        console.print("\n[bold magenta]--- New Skill Proposal ---[/bold magenta]")
        console.print(f"[bold]Target File:[/bold] {file_name}")
        console.print(f"[bold]Summary:[/bold] {summary}")
        console.print("[bold magenta]-----------------------------[/bold magenta]\n")
        
        # Test mode workaround or direct user input
        if os.environ.get("TEST_MODE") == "1":
            approved = False  # In tests we reject automatically to avoid mutating the file system
        else:
            approved = await asyncio.to_thread(Confirm.ask, "Soll dieser Skill erstellt und dem System hinzugefügt werden?")

        if not approved:
            return True, "Skill creation cancelled by user."

        # 3. Generate python code once approved
        console.print(f"[bold yellow][{self.name}][/bold yellow] Generating Python code for the new agent...")
        code_prompt = (
            f"Erstelle den Python-Code für den folgenden Agenten: {summary}\n"
            "Der Agent muss von `core.base_agent.BaseAgent` erben und eine `execute(self, *args, **kwargs)` Methode haben.\n"
            "Nutze `rich.console.Console` für Output. Die Antwort darf NUR den reinen Python-Code enthalten, "
            "ohne Markdown-Backticks (```python)."
        )

        code_res = await loop.run_in_executor(None, self.provider.generate, code_prompt)
        if not code_res.success:
            return False, f"Code generation failed: {code_res.message}"

        code = code_res.code_generated.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.endswith("```"):
            code = code[:-3]
        code = code.strip()

        # Write file safely
        try:
            dirname = os.path.dirname(file_name)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            with open(file_name, "w", encoding="utf-8") as f:
                f.write(code)
            console.print(f"[bold green]✅ New skill successfully created in {file_name}![/bold green]")
            
            return True, f"Skill {file_name} created."
        except Exception as e:
            return False, f"Error saving file {file_name}: {e}"
