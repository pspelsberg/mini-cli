import asyncio
from rich.console import Console
from core.base_agent import BaseAgent
from core.models import AgentTask, BuildResponse
from core.i18n import t, get_language
from providers import ProviderFactory
from tools.command_runner import CommandRunner, CommandTimeoutError
from agents.build_agent import _parse_block_format, _parse_json_format, _FILE_START, _MSG_START, _MSG_END, _FILE_END

console = Console()

class TestAgent(BaseAgent):
    __test__ = False
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Test-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def generate_tests(self, task: AgentTask, context: str) -> BuildResponse:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] TDD-Phase: Generating failing test (RED-Phase)...",
                        f"[bold yellow][{self.name}][/bold yellow] TDD-Phase: Generiere fehlschlagenden Test (RED-Phase)..."))
        
        lang = get_language()
        if lang == "de":
            prompt = (
                f"Du bist ein Test-Driven-Development (TDD) Experte. Für die folgende Aufgabe sollst du "
                f"ausschließlich die zugehörigen Unit-Tests (z.B. mit pytest) schreiben.\n"
                f"Aufgabe: {task.description}\n"
                f"Hier ist der Projektkontext:\n{context}\n"
                "Schreibe NOCH NICHT die eigentliche Implementierung, sondern nur die Tests in eine eigene Testdatei.\n\n"
                "WICHTIG: ANTWORTE IM FOLGENDEN BLOCK-FORMAT (kein JSON):\n"
                f"{_MSG_START}Kurze Erklärung{_MSG_END}\n"
                f"{_FILE_START}test_xxx.py{_MSG_END}\n"
                "...kompletter Test-Dateiinhalt...\n"
                f"{_FILE_END}\n"
            )
        else:
            prompt = (
                f"You are a Test-Driven Development (TDD) expert. For the following task, you should "
                f"exclusively write the corresponding unit tests (e.g. using pytest).\n"
                f"Task: {task.description}\n"
                f"Here is the project context:\n{context}\n"
                "Do NOT write the actual implementation yet, only the tests in their own test file.\n\n"
                "IMPORTANT: ANSWER IN THE FOLLOWING BLOCK FORMAT (no JSON):\n"
                f"{_MSG_START}Brief explanation{_MSG_END}\n"
                f"{_FILE_START}test_xxx.py{_MSG_END}\n"
                "...complete test file content...\n"
                f"{_FILE_END}\n"
            )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)

        if not response.success:
            return BuildResponse(success=False, message=f"LLM Fehler: {response.message}")

        raw_content = response.code_generated or ""

        result = _parse_block_format(raw_content)
        if result is None:
            result = _parse_json_format(raw_content)
        if result is None:
            console.print(t(
                f"[dim]Could not parse TestAgent response. Snippet:[/dim]\n{raw_content[:500]}",
                f"[dim]TestAgent-Antwort konnte nicht geparst werden. Ausschnitt:[/dim]\n{raw_content[:500]}"
            ))
            return BuildResponse(success=False, message="Ungültiges Format vom Modell erhalten.")

        message, mods = result
        return BuildResponse(success=True, message=message, modifications=mods, tokens_used=response.tokens_used)

    async def run_tests(self) -> tuple[bool, str]:
        import os
        import sys
        
        # 1. Detect language / framework by file inspection
        is_node = os.path.exists("package.json")
        is_go = os.path.exists("go.mod")
        is_rust = os.path.exists("Cargo.toml")
        is_php = os.path.exists("composer.json")
        
        # Define command and display message based on detected language
        if is_node:
            test_cmd = ["npm", "test"]
            lang_msg_en = "Running Node.js test suite (npm test)..."
            lang_msg_de = "Führe Node.js-Test-Suite aus (npm test)..."
        elif is_go:
            test_cmd = ["go", "test", "./..."]
            lang_msg_en = "Running Go test suite (go test)..."
            lang_msg_de = "Führe Go-Test-Suite aus (go test)..."
        elif is_rust:
            test_cmd = ["cargo", "test"]
            lang_msg_en = "Running Rust test suite (cargo test)..."
            lang_msg_de = "Führe Rust-Test-Suite aus (cargo test)..."
        elif is_php:
            test_cmd = ["vendor/bin/phpunit"]
            lang_msg_en = "Running PHP test suite (phpunit)..."
            lang_msg_de = "Führe PHP-Test-Suite aus (phpunit)..."
        else:
            test_cmd = [sys.executable, "-m", "pytest"]
            lang_msg_en = "Running Python test suite in sandbox (pytest)..."
            lang_msg_de = "Führe Python-Test-Suite in der Sandbox aus (pytest)..."
            
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] {lang_msg_en}",
                        f"[bold yellow][{self.name}][/bold yellow] {lang_msg_de}"))
        await asyncio.sleep(0.5)
        
        try:
            result = await CommandRunner.run_async(test_cmd, timeout=15)
            
            if result.returncode == 0:
                return True, "All tests passed successfully."
                
            # Treat empty test suite (code 5 for pytest) as success
            if not is_node and not is_go and not is_rust and not is_php and result.returncode == 5:
                return True, "No tests present."
            
            if "No module named pytest" in result.stderr:
                console.print(t("[dim]pytest not installed, skipping tests.[/dim]",
                                "[dim]pytest nicht installiert, überspringe Tests.[/dim]"))
                return True, ""
                
            return False, f"Tests failed:\n{result.stdout}\n{result.stderr}"
        except CommandTimeoutError:
            return False, f"Test execution ({test_cmd[0]}) in sandbox aborted after 15 seconds (timeout/infinite loop)."
        except Exception as e:
            return False, f"Error executing tests: {e}"
