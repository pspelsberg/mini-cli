import asyncio
import json
import re
from rich.console import Console

from core.base_agent import BaseAgent
from core.i18n import t
from providers import ProviderFactory

console = Console()

class PlannerAgent(BaseAgent):
    """
    Skill 11: PRD-to-Issues Planner
    Breaks down vague product requirements (PRDs) into concrete, executable GitHub/GitLab issues.
    Takes dependencies and acceptance criteria into consideration.
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Planner-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def generate_plan_and_chat(self, task_desc: str, context: str) -> dict:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Processing plan and generating response via {self.provider.__class__.__name__}...",
                        f"[bold yellow][{self.name}][/bold yellow] Verarbeite Plan und generiere Antwort via {self.provider.__class__.__name__}..."))

        prompt = (
            f"You are a technical project manager, software architect, and AI assistant.\n"
            f"The user is in planning mode and has sent this message: '{task_desc}'\n\n"
            f"Here is the context of the codebase and previous plans:\n{context}\n\n"
            f"Instructions:\n"
            f"1. Conversational Chat: Chat normally with the user. Answer their questions, discuss architectural designs, ask clarifying questions, or explain technical concepts. Keep the tone helpful and professional.\n"
            f"2. Task Planning ('Task Chaining'):\n"
            f"   - If the user wants to implement a new feature, fix a bug, or execute a programming task, you MUST create or update two files:\n"
            f"     a) 'task.md': A markdown file describing the goals, requirements, constraints, and scope of the task. It serves as the single source of truth.\n"
            f"     b) 'implementationplan.md' (or 'implementation_plan.md'): A step-by-step technical checklist detailing exactly how to build it. Coding agents in build/auto mode will read this plan to execute the steps sequentially.\n"
            f"   - Modern Coding Standards: Both files are essential for separating concerns and keeping state. 'task.md' defines the scope and boundaries (preventing scope creep), while 'implementationplan.md' acts as a sequential progress tracker. Build/auto-mode agents execute tasks step-by-step, updating the checklist by changing `[ ]` to `[x]` upon validation success. Ensure your generated implementation plan contains clear checklists (`- [ ]`) for steps.\n"
            f"   - If the user is just asking a general question and not planning a specific coding task, you should leave these files empty/null in your JSON response.\n"
            f"   - If plans already exist in the context, you can refine, append, or update them based on the user's feedback.\n\n"
            f"Language Instruction: Please respond in the same language as the user's input/request. If the user writes in German, respond in German. If the user writes in English, respond in English.\n\n"
            f"YOU MUST RESPOND EXCLUSIVELY IN JSON format (no other text, no markdown wrapping around the JSON block). Use this schema:\n"
            f"{{\n"
            f"  \"chat_response\": \"<Your conversational response/answer to the user>\",\n"
            f"  \"task_md\": \"<The complete content for task.md or null/empty if no update>\",\n"
            f"  \"implementation_plan_md\": \"<The complete content for the implementation plan or null/empty if no update>\"\n"
            f"}}\n"
        )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)

        if not response.success:
            return {
                "success": False,
                "chat_response": f"Error: {response.message}",
                "task_md": None,
                "implementation_plan_md": None,
                "tokens_used": response.tokens_used
            }

        raw_content = response.code_generated or ""
        try:
            # Try to extract JSON block via Regex
            json_match = re.search(r'\{.*\}', raw_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = raw_content.replace('```json', '').replace('```', '').strip()

            data = json.loads(json_str)
            return {
                "success": True,
                "chat_response": data.get("chat_response", ""),
                "task_md": data.get("task_md"),
                "implementation_plan_md": data.get("implementation_plan_md"),
                "tokens_used": response.tokens_used
            }
        except Exception as e:
            # Fallback if parsing fails: treat the entire generation as the chat response
            console.print(t(f"[dim]JSON Parsing error in PlannerAgent: {e}[/dim]",
                            f"[dim]JSON Parsing Fehler im PlannerAgent: {e}[/dim]"))
            return {
                "success": True,
                "chat_response": raw_content,
                "task_md": None,
                "implementation_plan_md": None,
                "tokens_used": response.tokens_used
            }


    async def plan_issues(self, prd_content: str) -> tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Analyzing PRD and creating issue plan...",
                        f"[bold yellow][{self.name}][/bold yellow] Analysiere PRD und erstelle Issue-Plan..."))
        await asyncio.sleep(0.5)

        if not prd_content.strip():
            return False, "Leere Anforderung. Kann keinen Plan erstellen."

        prompt = (
            "Du bist ein technischer Projektmanager und Lead-Entwickler. "
            "Zerlege die folgende Produktanforderung (PRD) in ausführbare technische Arbeitspakete (Issues).\n"
            "Regeln:\n"
            "1. Jedes Issue braucht einen Titel, eine kurze Beschreibung und klare Akzeptanzkriterien.\n"
            "2. Priorisiere die Issues sinnvoll (z. B. Datenbank vor Frontend).\n"
            "3. Wenn die Anforderung zu ungenau ist, schreibe 'NEED_MORE_INFO: <Fragen>'.\n"
            "4. Wenn du Issues generieren kannst, beginne deine Antwort exakt mit 'ISSUES_GENERATED:\n'.\n\n"
            f"Anforderung:\n{prd_content}\n"
        )
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            if result.startswith("ISSUES_GENERATED"):
                console.print(t("[dim]Issues successfully generated (issue tracker simulation).[/dim]",
                                "[dim]Issues erfolgreich generiert (Simulation des Issue-Trackers).[/dim]"))
                return True, result
            elif result.startswith("NEED_MORE_INFO"):
                return False, result
                
        return False, "Konnte PRD nicht verarbeiten."
