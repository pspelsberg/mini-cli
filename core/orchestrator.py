import os
import asyncio
import logging
import uuid
import importlib
import re
from typing import List, Dict, Any
from core.i18n import t

from core.models import AgentTask, FileModification, BuildResponse
from core.base_agent import BaseAgent
from tools.security import RateLimitGuard


from core.ui_reporter import UIReporter
from core.workspace_manager import WorkspaceManager


AGENT_REGISTRY = {
    "rag": ("agents.rag_agent", "RAGAgent", True),
    "build": ("agents.build_agent", "BuildAgent", True),
    "qa": ("agents.qa_agent", "QAAgent", False),
    "test": ("agents.test_agent", "TestAgent", True),
    "git": ("agents.git_agent", "GitAgent", False),
    "arch": ("agents.architecture_agent", "ArchitectureAgent", True),
    "research": ("agents.research_agent", "ResearchAgent", False),
    "sec": ("agents.security_agent", "SecurityAgent", False),
    "docs": ("agents.docs_agent", "DocsAgent", True),
    "api": ("agents.api_agent", "ApiAgent", True),
    "browser": ("agents.browser_agent", "BrowserAgent", True),
    "cicd": ("agents.cicd_agent", "CicdAgent", True),
    "db": ("agents.database_agent", "DatabaseAgent", True),
    "dep": ("agents.dependency_agent", "DependencyAgent", True),
    "docker": ("agents.docker_agent", "DockerAgent", True),
    "frontend": ("agents.frontend_agent", "FrontendAgent", True),
    "planner": ("agents.planner_agent", "PlannerAgent", True),
    "profiler": ("agents.profiler_agent", "ProfilerAgent", True),
    "review": ("agents.review_agent", "ReviewAgent", True),
    "skill": ("agents.skill_creator_agent", "SkillCreatorAgent", True),
    "verify": ("agents.verify_agent", "VerifyAgent", False),
}


class OrchestratorAgent(BaseAgent):
    """
    Main orchestrator that coordinates specialized agents to complete coding tasks.
    Handles TDD workflow, file modifications, and self-healing loops.
    """

    # Dynamic agent attributes for type hinting
    rag_agent: Any
    build_agent: Any
    qa_agent: Any
    test_agent: Any
    git_agent: Any
    arch_agent: Any
    research_agent: Any
    sec_agent: Any
    docs_agent: Any
    api_agent: Any
    browser_agent: Any
    cicd_agent: Any
    db_agent: Any
    dep_agent: Any
    docker_agent: Any
    frontend_agent: Any
    planner_agent: Any
    profiler_agent: Any
    review_agent: Any
    skill_agent: Any
    verify_agent: Any

    def __init__(
        self,
        provider_name: str = "ollama",
        ui: UIReporter = None,
        workspace_manager: WorkspaceManager = None,
        rate_limit_guard: RateLimitGuard = None,
    ):
        self._name = "Orchestrator"
        self.provider_name = provider_name
        self._agents: Dict[str, Any] = {}
        self.rate_limit_guard = rate_limit_guard or RateLimitGuard()
        self.ui = ui or UIReporter()
        self.workspace_manager = workspace_manager or WorkspaceManager(self.ui)
        from core.memory import MemoryManager

        self.memory_manager = MemoryManager(provider_name=self.provider_name)
        from core.i18n import load_config

        config = load_config()
        self.agent_providers = config.get("agent_providers", {})

    def _get_agent(self, agent_name: str) -> Any:
        """
        Lazy-loads agents to improve startup performance and avoid circular dependencies.
        """
        if agent_name not in self._agents:
            if agent_name in AGENT_REGISTRY:
                module_path, class_name, needs_provider = AGENT_REGISTRY[agent_name]
                module = importlib.import_module(module_path)
                agent_class = getattr(module, class_name)

                if needs_provider:
                    agent_provider = self.agent_providers.get(
                        agent_name, self.provider_name
                    )
                    self._agents[agent_name] = agent_class(agent_provider)
                else:
                    self._agents[agent_name] = agent_class()
                # Pass UI reference to the agent for HITL prompting
                setattr(self._agents[agent_name], "ui", self.ui)
            else:
                raise ValueError(f"Unknown agent: {agent_name}")

        return self._agents[agent_name]

    def __getattr__(self, name: str) -> Any:
        """Dynamically resolve properties ending with '_agent' via the registry."""
        if name.endswith("_agent"):
            agent_key = name[:-6]  # e.g., 'rag' from 'rag_agent'
            if agent_key in AGENT_REGISTRY:
                agent = self._get_agent(agent_key)
                setattr(self, name, agent)
                return agent
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    @property
    def name(self) -> str:
        return self._name

    def _sanitize_error_message(self, error_msg: str) -> str:
        """
        Sanitizes and truncates error logs to prevent prompt injection and keep context size reasonable.
        If the error message exceeds the limit, it retains the first 25% and the last 75% of the limit
        to preserve both the initiation context and the final exception details.
        """
        limit = int(os.getenv("ERROR_LOG_LIMIT", "10000"))
        if len(error_msg) > limit:
            head_len = limit // 4
            tail_len = limit - head_len - 25  # 25 characters for truncation marker
            truncated = f"{error_msg[:head_len]}\n... [TRUNCATED FOR CONTEXT LIMIT] ...\n{error_msg[-tail_len:]}"
        else:
            truncated = error_msg
        return truncated.replace("```", "'''").replace("<", "&lt;").replace(">", "&gt;")

    async def _run_tdd_phase(
        self, task: AgentTask, context: str, is_doc_task: bool = False
    ) -> str:
        """Executes the Test-Driven Development (TDD) red phase."""
        if is_doc_task or task.mode not in ["build", "auto"] or task.id == "repair":
            return context

        self.ui.step(
            f"Delegating to {self.test_agent.name} for TDD (Red-Phase)...",
            f"Delegiere an {self.test_agent.name} für TDD (Red-Phase)...",
        )

        try:
            async with self.ui.spin(
                "Generating failing tests (Red-Phase)…",
                "Generiere fehlschlagende Tests (Red-Phase)…",
            ):
                test_response = await self.test_agent.generate_tests(task, context)
            await self.rate_limit_guard.check_and_add(test_response.tokens_used)
        except Exception as e:
            logging.exception("Error in TDD Phase")
            self.ui.error(f"Error in TDD Phase: {e}", f"Fehler in der TDD Phase: {e}")
            return context

        if test_response.success and test_response.modifications:
            test_files = await self.workspace_manager.apply_modifications(
                test_response.modifications, task.mode
            )
            if test_files:
                self.ui.step(
                    "Running generated tests (they should fail)...",
                    "Führe generierte Tests aus (sollten fehlschlagen)...",
                )
                try:
                    tests_passed, test_msg = await self.test_agent.run_tests()
                    if tests_passed:
                        self.ui.warning(
                            "Tests are already green, even though no implementation exists!",
                            "Tests sind bereits grün, obwohl noch keine Implementierung existiert!",
                        )
                    else:
                        self.ui.error(
                            "Tests failed as expected in TDD. Passing to Build-Agent for Green-Phase.",
                            "Tests schlagen wie in TDD erwartet fehl. Übergebe an Build-Agent für Green-Phase.",
                        )
                        context_parts = [
                            context,
                            t(
                                "\n\n--- TDD Phase ---\nWe wrote this failing test:\n",
                                "\n\n--- TDD Phase ---\nWir haben diesen Test geschrieben, der gerade fehlschlägt:\n",
                            ),
                        ]
                        for m in test_response.modifications:
                            context_parts.append(
                                t(
                                    f"File: {m.filepath}\nCode:\n{m.content}\n\n",
                                    f"Datei: {m.filepath}\nCode:\n{m.content}\n\n",
                                )
                            )
                        context_parts.append(
                            t(
                                f"Error message from test execution:\n{test_msg}\n\nPlease implement the code now (Green-Phase) to make this test pass.",
                                f"Fehlermeldung der Testausführung:\n{test_msg}\n\nBitte implementiere nun den Code (Green-Phase), damit dieser Test erfolgreich durchläuft.",
                            )
                        )
                        context = "".join(context_parts)
                except Exception as e:
                    logging.exception("Error executing tests")
                    self.ui.error(
                        f"Error executing tests: {e}",
                        f"Fehler beim Ausführen der Tests: {e}",
                    )
        return context

    async def _gather_modifications(self, files: List[str]) -> List[FileModification]:
        """Sammelt alle Dateiinhalte für die Validierung."""
        all_mods = []
        for f in files:
            if await self.workspace_manager.file_exists(f):
                content = await self.workspace_manager.read_file_content(f)
                all_mods.append(FileModification(filepath=f, content=content or ""))
            else:
                all_mods.append(FileModification(filepath=f, content=""))
        return all_mods

    async def _run_static_validation(
        self, all_mods: List[FileModification], only_critical: bool
    ) -> List[str]:
        """Führt statische Validierungsprüfungen (QA, Security, Review) parallel aus."""
        static_validators = [
            (self.qa_agent.name, lambda: self.qa_agent.validate_code(all_mods)),
            (self.sec_agent.name, lambda: self.sec_agent.run_vulnerability_scan()),
            (self.sec_agent.name, lambda: self.sec_agent.check_dependencies()),
            (
                self.review_agent.name,
                lambda: self.review_agent.review_code(
                    all_mods, only_critical=only_critical
                ),
            ),
            (
                self.cicd_agent.name,
                lambda: self.cicd_agent.validate_cicd_configs(all_mods),
            ),
        ]

        static_results = await asyncio.gather(
            *(v() for _, v in static_validators), return_exceptions=True
        )

        errors = []
        for (agent_name, _), result in zip(static_validators, static_results):
            if isinstance(result, Exception):
                errors.append(
                    f"[{agent_name}] Exception during static validation: {str(result)}"
                )
            else:
                ok, msg = result
                if not ok:
                    errors.append(f"[{agent_name}] {msg}")
        return errors

    async def _run_dynamic_validation(self) -> List[str]:
        """Führt dynamische Tests aus, falls statische Prüfungen bestanden wurden."""
        errors = []
        self.ui.step(
            f"Static validation passed. Delegating to {self.test_agent.name} for test execution...",
            f"Statische Validierung bestanden. Delegiere an {self.test_agent.name} zur Testausführung...",
        )
        try:
            tests_passed, test_msg = await self.test_agent.run_tests()
            if not tests_passed:
                errors.append(f"[{self.test_agent.name}] {test_msg}")
        except Exception as e:
            logging.exception("Error executing tests")
            errors.append(
                f"[{self.test_agent.name}] Exception during test execution: {str(e)}"
            )

        # Dynamically execute BrowserAgent's E2E test suite if E2E tests exist and we are not unit-testing
        import sys

        if (
            os.path.exists("tests/e2e")
            and "pytest" not in sys.modules
            and os.environ.get("TEST_MODE") != "1"
        ):
            try:
                e2e_passed, e2e_msg = await self.browser_agent.run_e2e_suite()
                if not e2e_passed:
                    errors.append(f"[{self.browser_agent.name}] {e2e_msg}")
            except Exception as e:
                logging.exception("Error executing E2E tests")
                errors.append(
                    f"[{self.browser_agent.name}] Exception during E2E test execution: {str(e)}"
                )

        return errors

    async def _run_self_healing_loop(
        self,
        task: AgentTask,
        initial_build_response: Any,
        files_written: List[str],
        context: str,
    ) -> None:
        """Runs the QA and testing loop to validate code and automatically repair it if needed."""
        if task.mode not in ["build", "auto"]:
            return

        max_retries = 5
        build_response = initial_build_response
        is_valid = False
        repair_history = []

        if hasattr(self.review_agent, "last_findings"):
            self.review_agent.last_findings = None

        attempt = 0
        while attempt <= max_retries:
            self.ui.step(
                f"Running validation suite (Attempt {attempt + 1}/{max_retries + 1})...",
                f"Führe Validierungs-Suite aus (Versuch {attempt + 1}/{max_retries + 1})...",
            )

            try:
                try:
                    # Refresh context to reflect the latest files written on disk
                    context = await self._prepare_context(task, is_refresh=True)
                except Exception as e:
                    logging.warning(
                        f"Failed to refresh context during self-healing: {e}"
                    )

                all_mods = await self._gather_modifications(files_written)

                only_critical = attempt >= 3
                if attempt == 3:
                    self.ui.warning(
                        "Three self-healing attempts failed to pass review. Relaxing review to only check critical issues...",
                        "Drei Self-Healing-Durchläufe haben das Review nicht bestanden. Review wird gelockert, um nur noch kritische Punkte zu prüfen...",
                    )

                # 1. Statische Prüfungen
                errors = await self._run_static_validation(all_mods, only_critical)

                # 2. Dynamische Prüfungen
                if not errors:
                    errors.extend(await self._run_dynamic_validation())
                else:
                    self.ui.warning(
                        "Static validation or review failed. Skipping test execution to avoid executing potentially unsafe/broken code.",
                        "Statische Validierung oder Review fehlgeschlagen. Überspringe Testausführung, um die Ausführung von potenziell unsicherem/fehlerhaftem Code zu vermeiden.",
                    )

                if errors:
                    is_valid = False
                    error_msg = "\n\n".join(errors)
                    
                    # Check if only optimizations are left open
                    only_optimizations = True
                    for err in errors:
                        err_upper = err.upper()
                        if "[REVIEW-AGENT]" not in err_upper:
                            only_optimizations = False
                            break
                        if "[KRITISCH]" in err_upper or "[CRITICAL]" in err_upper or "[WARNUNG]" in err_upper or "[WARNING]" in err_upper:
                            only_optimizations = False
                            break
                    
                    if only_optimizations and attempt < max_retries:
                        prompt_str = t(
                            "Only optimizations are left open. Do you want to continue self-healing? (y/n) [n]: ",
                            "Es sind nur noch Optimierungen offen. Möchtest du mit dem Self-Healing fortfahren? (y/n) [n]: "
                        )
                        if not await self.ui.ask_confirm(prompt_str, default="n"):
                            self.ui.step(
                                "User decided to skip remaining optimizations.",
                                "Nutzer hat sich entschieden, die verbleibenden Optimierungen zu überspringen."
                            )
                            is_valid = True
                            error_msg = ""
                else:
                    is_valid = True
                    error_msg = ""
            except Exception as e:
                logging.exception("Internal exception during validation")
                is_valid = False
                error_msg = f"Internal exception during validation: {str(e)}"

            if is_valid:
                self.ui.success(
                    f"[{self.name}] Validation successful!",
                    f"[{self.name}] Validierung erfolgreich!",
                )

                # Log successful fix in LanceDB
                if repair_history:
                    try:
                        initial_error_msg = repair_history[0][0]
                        logged = await self.memory_manager.add_memory(
                            task.description,
                            initial_error_msg,
                            build_response.modifications,
                        )
                        if logged:
                            self.ui.success(
                                "Successfully logged the error and its solution to LanceDB memory.",
                                "Fehler und dessen Lösung erfolgreich im LanceDB-Speicher protokolliert.",
                            )
                    except Exception as e:
                        logging.warning(f"Error logging to MemoryManager: {e}")

                # If we have open warnings/optimizations, write them to review.md
                if getattr(self.review_agent, "last_findings", None):
                    findings_content = self.review_agent.last_findings
                    md_content = (
                        "# Code-Review: Offene Optimierungen und Warnungen\n\n"
                        "Die kritischen Fehler wurden behoben. Die folgenden verbleibenden Warnungen und "
                        "Optimierungshinweise wurden erfasst:\n\n"
                        f"{findings_content}\n"
                    )
                    write_ok = await self.workspace_manager.write_file_content(
                        "review.md", md_content
                    )
                    if write_ok:
                        self.ui.success(
                            "Review file 'review.md' created with remaining findings.",
                            "Review-Datei 'review.md' mit verbleibenden Hinweisen wurde erstellt.",
                        )
                        if "review.md" not in files_written:
                            files_written.append("review.md")
                    else:
                        self.ui.error(
                            "Failed to write 'review.md' to the workspace.",
                            "Schreiben der Datei 'review.md' in den Workspace fehlgeschlagen.",
                        )
                break
            else:
                self.ui.warning(
                    f"[{self.name}] Validation/Tests failed:\n{error_msg}",
                    f"[{self.name}] Validierung/Tests fehlgeschlagen:\n{error_msg}",
                )
                if attempt >= max_retries:
                    prompt_str = t(
                        f"[{self.name}] Max self-healing retries reached. Grant 3 more attempts? (y/n) [y]: ",
                        f"[{self.name}] Maximale Self-Healing Versuche erreicht. 3 weitere erlauben? (y/n) [y]: ",
                    )
                    if await self.ui.ask_confirm(prompt_str):
                        max_retries += 3
                    else:
                        self.ui.error(
                            f"[{self.name}] Max self-healing retries reached. Aborting.",
                            f"[{self.name}] Maximale Self-Healing Versuche erreicht. Breche ab.",
                        )
                        break

                self.ui.step(
                    "Starting Self-Healing Loop...", "Starte Self-Healing Loop..."
                )

                safe_error_msg = self._sanitize_error_message(str(error_msg))

                # Extract referenced files from error logs (e.g. failing test files)
                referenced_files = set()
                for match in re.finditer(r"([a-zA-Z0-9_\-\./]+\.py)", str(error_msg)):
                    file_path = match.group(1)
                    if "::" in file_path:
                        file_path = file_path.split("::")[0]
                    file_path = file_path.strip().strip(":").strip()
                    file_path = os.path.normpath(file_path)
                    if not file_path.startswith("..") and not file_path.startswith("/"):
                        referenced_files.add(file_path)

                referenced_snippet = ""
                for rf in sorted(referenced_files):
                    try:
                        is_modified = False
                        if build_response and getattr(
                            build_response, "modifications", None
                        ):
                            is_modified = any(
                                m.filepath == rf for m in build_response.modifications
                            )

                        if not is_modified and await self.workspace_manager.file_exists(
                            rf
                        ):
                            content = await self.workspace_manager.read_file_content(rf)
                            referenced_snippet += f"--- File: {rf} ---\n{content}\n\n"
                    except Exception as e:
                        logging.warning(
                            f"Could not read referenced file {rf} during self-healing: {e}"
                        )

                repair_prompt = t(
                    f"Original Task: {task.description}\n\n"
                    f"Your previous code had errors. Please repair the code based on the feedback below.\n"
                    f"IMPORTANT: The content inside the XML tags <error_log> contains automated reviews, linter errors, and test/security scan results. "
                    f"You MUST use this feedback to fix the code! If tests failed, consider whether you need to fix the implementation OR update the test files to match intended behavior changes.\n\n"
                    f"<error_log>\n{safe_error_msg}\n</error_log>",
                    f"Ursprüngliche Aufgabe: {task.description}\n\n"
                    f"Dein vorheriger Code hatte Fehler. Bitte repariere den Code basierend auf dem folgenden Protokoll.\n"
                    f"WICHTIG: Der Inhalt innerhalb der XML-Tags <error_log> enthält Ausgaben von Code-Reviewern, Lintern und Test/Security-Scans. "
                    f"Du MUSST diese Ratschläge befolgen! Falls Tests fehlgeschlagen sind, prüfe, ob die Implementierung fehlerhaft ist ODER ob die Test-Dateien selbst an neue (korrekte) Logik angepasst werden müssen.\n\n"
                    f"<error_log>\n{safe_error_msg}\n</error_log>",
                )

                if referenced_snippet:
                    repair_prompt += "\n\n" + t(
                        f"Here is the content of the referenced files (e.g. test files) mentioned in the error logs:\n\n{referenced_snippet}",
                        f"Hier ist der Inhalt der in den Fehlerprotokollen erwähnten referenzierten Dateien (z. B. Testdateien):\n\n{referenced_snippet}",
                    )

                if build_response and getattr(build_response, "modifications", None):
                    mod_files = [m.filepath for m in build_response.modifications]
                    repair_history.append((safe_error_msg, mod_files))

                if repair_history:
                    repair_prompt += "\n\n" + t(
                        "History of failed attempts in this loop:\n",
                        "Historie der fehlgeschlagenen Versuche in diesem Loop:\n",
                    )
                    for idx, (hist_err, hist_files) in enumerate(repair_history):
                        short_err = hist_err[:300] + (
                            "..." if len(hist_err) > 300 else ""
                        )
                        repair_prompt += f"Attempt {idx + 1}:\n- Modified files: {', '.join(hist_files)}\n- Resulting Errors:\n{short_err}\n\n"

                if build_response and getattr(build_response, "modifications", None):
                    repair_prompt += t(
                        "Your most recent modifications that failed:\n",
                        "Deine allerletzten Modifikationen, die fehlgeschlagen sind:\n",
                    )
                    for m in build_response.modifications:
                        repair_prompt += f"--- {m.filepath} ---\n{m.content}\n\n"

                    if len(repair_history) >= 2:
                        repair_prompt += t(
                            "WARNING: You are stuck in a loop. You have tried to fix this multiple times and it keeps failing. "
                            "Please carefully review the history above to understand why your previous fixes caused new errors. "
                            "Do not repeat the same mistakes! Think step-by-step to find a solution that satisfies ALL constraints.\n\n",
                            "WARNUNG: Du steckst offensichtlich in einer Schleife (z.B. Fix A verursacht Fehler B, Fix B verursacht Fehler A). "
                            "Bitte analysiere die Historie oben genau, um zu verstehen, warum deine Fixes fehlschlagen. "
                            "Wiederhole nicht die gleichen Ansätze! Finde einen Weg, der ALLE Tests und Security-Vorgaben gleichzeitig erfüllt.\n\n",
                        )

                # Query past memories of similar errors
                try:
                    past_memories = await self.memory_manager.find_relevant_memories(
                        str(error_msg), limit=2
                    )
                    if past_memories:
                        memory_str = "\n\n" + t(
                            "--- Past Similar Errors & Solutions (RAG Memory) ---\n",
                            "--- Ähnliche Fehler & Lösungen aus der Vergangenheit (RAG Memory) ---\n",
                        )
                        for idx, mem in enumerate(past_memories):
                            memory_str += f"Past Case {idx + 1}:\n"
                            memory_str += f"- Task: {mem['task_description']}\n"
                            memory_str += f"- Past Error:\n{mem['error_log']}\n"
                            memory_str += "- Solution Modifications:\n"
                            for sm in mem["solution"]:
                                memory_str += (
                                    f"  File: {sm['filepath']}\n{sm['content']}\n"
                                )
                            memory_str += "\n"
                        repair_prompt += memory_str
                except Exception as e:
                    logging.warning(f"Error querying memory during self-healing: {e}")

                try:
                    async with self.ui.spin(
                        "Self-Healing: regenerating code…",
                        "Self-Healing: Code wird neu generiert…",
                    ):
                        build_response = await self.build_agent.generate_code(
                            AgentTask(
                                id="repair", description=repair_prompt, mode=task.mode
                            ),
                            context,
                        )
                    await self.rate_limit_guard.check_and_add(
                        build_response.tokens_used
                    )
                except Exception as e:
                    logging.exception("LLM Error during Self-Healing")
                    self.ui.error(
                        f"LLM Error during Self-Healing: {e}",
                        f"LLM-Fehler während Self-Healing: {e}",
                    )
                    break

                if not build_response or not build_response.modifications:
                    self.ui.warning(
                        "No repair suggestions received. Aborting.",
                        "Keine Reparatur-Vorschläge erhalten. Breche ab.",
                    )
                    break

                try:
                    sec_ok, sec_err = await self.sec_agent.check_secrets(
                        build_response.modifications
                    )
                    if not sec_ok:
                        self.ui.error(
                            f"Repair generation contained secrets, aborting: {sec_err}",
                            f"Repair-Generierung enthielt Secrets, breche ab: {sec_err}",
                        )
                        break
                except Exception as e:
                    logging.exception("Security check failed in Self-Healing")
                    self.ui.warning(
                        f"Security check failed: {e}",
                        f"Sicherheits-Check fehlgeschlagen: {e}",
                    )
                    break

                repair_written = await self.workspace_manager.apply_modifications(
                    build_response.modifications, task.mode
                )
                for f in repair_written:
                    if f not in files_written:
                        files_written.append(f)

            attempt += 1

        if is_valid and files_written:
            try:
                await self.git_agent.auto_commit(task.description, files_written)
            except Exception as e:
                logging.exception("Failed to auto-commit")
                self.ui.warning(
                    f"Failed to auto-commit: {e}", f"Auto-Commit fehlgeschlagen: {e}"
                )

    def _requires_research(self, description: str) -> bool:
        keywords = {"recherchiere", "suche", "search", "research"}
        desc_lower = description.lower()
        return any(kw in desc_lower for kw in keywords)

    def _is_doc_task(self, description: str) -> bool:
        keywords = {
            "doku",
            "dokument",
            "readme",
            "docstring",
            "diagramm",
            "kommentier",
            "doc",
            "documentation",
            "diagram",
            "comment",
        }
        desc_lower = description.lower()
        return any(kw in desc_lower for kw in keywords)

    async def _ensure_standard_files(self) -> None:
        """
        Scans the workspace for task.md and implementationplan.md.
        If they do not exist, they are created with default templates explaining
        their purpose according to modern coding standards and how to work with them.
        """
        task_exists = await self.workspace_manager.file_exists("task.md")
        impl_exists = await self.workspace_manager.file_exists(
            "implementationplan.md"
        ) or await self.workspace_manager.file_exists("implementation_plan.md")

        # 1. Ensure task.md exists
        if not task_exists:
            task_en = (
                "# Task Description\n\n"
                "## Purpose of this File (Coding Standards)\n"
                "This file is the single source of truth for the goals, requirements, constraints, and scope of a programming task. "
                "According to modern agentic coding standards, it ensures that:\n"
                "1. The AI Agent and the Developer align on what needs to be built.\n"
                "2. The boundaries (in-scope vs. out-of-scope) are clearly defined to avoid scope creep.\n"
                "3. Explicit constraints (security, performance, naming conventions) are documented upfront.\n\n"
                "## How to Work with this File\n"
                "- **Review**: The agent reads this file at the start of any build or auto-mode session to understand the high-level objectives.\n"
                "- **Maintain**: If requirements change during discussion, this file is updated.\n\n"
                "---\n\n"
                "## 📋 Task: [Name of the Task]\n\n"
                "### Description\n"
                "[Provide a clear, high-level description of what needs to be implemented or fixed.]\n\n"
                "### Goals & Requirements\n"
                "- [ ] Requirement 1: ...\n"
                "- [ ] Requirement 2: ...\n\n"
                "### Constraints\n"
                "- Language: Python/JS/HTML (as defined)\n"
                "- Keep code clean, modular, and well-tested.\n"
                "- Follow SOLID principles.\n"
            )
            task_de = (
                "# Aufgabenbeschreibung\n\n"
                "## Zweck dieser Datei (Coding-Standards)\n"
                'Diese Datei ist die einzige Quelle der Wahrheit ("Single Source of Truth") für die Ziele, Anforderungen, Randbedingungen und den Umfang einer Programmieraufgabe. '
                "Nach modernen Coding-Standards für Agenten stellt sie Folgendes sicher:\n"
                "1. Der AI-Agent und der Entwickler stimmen sich darüber ab, was gebaut werden soll.\n"
                "2. Die Grenzen (In-Scope vs. Out-of-Scope) werden klar definiert, um unkontrollierten Zuwachs an Anforderungen (Scope Creep) zu vermeiden.\n"
                "3. Explizite Einschränkungen (Sicherheit, Performance, Namenskonventionen) werden vorab dokumentiert.\n\n"
                "## Wie mit dieser Datei gearbeitet wird\n"
                "- **Review**: Der Agent liest diese Datei zu Beginn jeder Build- oder Auto-Modus-Sitzung, um die übergeordneten Ziele zu verstehen.\n"
                "- **Pflege**: Wenn sich Anforderungen während der Diskussion ändern, wird diese Datei aktualisiert.\n\n"
                "---\n\n"
                "## 📋 Aufgabe: [Name der Aufgabe]\n\n"
                "### Beschreibung\n"
                "[Gib eine klare, übergeordnete Beschreibung dessen an, was implementiert oder behoben werden muss.]\n\n"
                "### Ziele & Anforderungen\n"
                "- [ ] Anforderung 1: ...\n"
                "- [ ] Anforderung 2: ...\n\n"
                "### Einschränkungen\n"
                "- Sprache: Python/JS/HTML (wie definiert)\n"
                "- Halte den Code sauber, modular und gut getestet.\n"
                "- Befolge die SOLID-Prinzipien.\n"
            )

            task_content = t(task_en, task_de)
            written = await self.workspace_manager.write_file_content(
                "task.md", task_content
            )
            if written:
                self.ui.success(
                    "task.md was missing and has been created with default templates.",
                    "task.md fehlte und wurde mit Standard-Templates erstellt.",
                )

        # 2. Ensure implementationplan.md exists
        if not impl_exists:
            impl_en = (
                "# Implementation Plan\n\n"
                "## Purpose of this File (Coding Standards)\n"
                "This file outlines the exact step-by-step technical plan to implement the requirements specified in `task.md`. "
                "According to modern coding standards:\n"
                "1. It breaks down complex features into smaller, testable, and manageable tasks.\n"
                "2. It guides build-agents (or auto-mode) to execute the implementation sequentially, minimizing logical errors and design drift.\n"
                "3. It tracks progress so both the agent and human developers know what has been completed.\n\n"
                "## How to Work with this File\n"
                "- **Execution**: The build agent (in build or auto mode) reads this plan.\n"
                "- **Sequential Steps**: The agent executes the tasks step-by-step, starting from the first incomplete item.\n"
                "- **Tracking Progress**: After a step is successfully implemented and validated, the checkbox is marked as complete:\n"
                "  - Change `[ ]` to `[x]` (completed)\n"
                "  - Keep the checklist updated to preserve state between agent runs.\n\n"
                "---\n\n"
                "## 🛠️ Step-by-Step Implementation\n\n"
                "- [ ] **Step 1: Setup and Verification**\n"
                "  - Check the current workspace structure.\n"
                "  - Setup necessary tests or stubs.\n\n"
                "- [ ] **Step 2: Implementation of Core Logic**\n"
                "  - Implement core functionality.\n\n"
                "- [ ] **Step 3: Verification & Review**\n"
                "  - Run tests and static analysis.\n"
                "  - Fix any warnings or errors.\n"
            )
            impl_de = (
                "# Implementierungsplan\n\n"
                "## Zweck dieser Datei (Coding-Standards)\n"
                "Diese Datei beschreibt den genauen, schrittweisen technischen Plan zur Umsetzung der in `task.md` festgelegten Anforderungen. "
                "Nach modernen Coding-Standards:\n"
                "1. Zerlegt sie komplexe Funktionen in kleinere, testbare und überschaubare Aufgaben.\n"
                "2. Führt sie Build-Agenten (oder den Auto-Modus) dazu, die Implementierung sequenziell auszuführen, was Logikfehler und Designabweichungen minimiert.\n"
                "3. Verfolgt sie den Fortschritt, sodass sowohl der Agent als auch der menschliche Entwickler wissen, was bereits erledigt ist.\n\n"
                "## Wie mit dieser Datei gearbeitet wird\n"
                "- **Ausführung**: Der Build-Agent (im Build- oder Auto-Modus) liest diesen Plan.\n"
                "- **Sequenzielle Schritte**: Der Agent führt die Aufgaben Schritt für Schritt aus, beginnend mit dem ersten unvollständigen Punkt.\n"
                "- **Fortschrittsverfolgung**: Nachdem ein Schritt erfolgreich implementiert und validiert wurde, wird das Kontrollkästchen als erledigt markiert:\n"
                "  - Ändere `[ ]` in `[x]` (erledigt)\n"
                "  - Halte die Checkliste aktuell, um den Zustand zwischen Agenten-Durchläufen zu bewahren.\n\n"
                "---\n\n"
                "## 🛠️ Schritt-für-Schritt-Implementierung\n\n"
                "- [ ] **Schritt 1: Einrichtung & Verifikation**\n"
                "  - Überprüfe die aktuelle Workspace-Struktur.\n"
                "  - Richte notwendige Tests oder Stubs ein.\n\n"
                "- [ ] **Schritt 2: Implementierung der Kernlogik**\n"
                "  - Implementiere die Kernfunktionalität.\n\n"
                "- [ ] **Schritt 3: Verifikation & Review**\n"
                "  - Führe Tests und statische Analysen aus.\n"
                "  - Behebe eventuelle Warnungen oder Fehler.\n"
            )

            impl_content = t(impl_en, impl_de)
            written = await self.workspace_manager.write_file_content(
                "implementationplan.md", impl_content
            )
            if written:
                self.ui.success(
                    "implementationplan.md was missing and has been created with default templates.",
                    "implementationplan.md fehlte und wurde mit Standard-Templates erstellt.",
                )

    def _is_start_signal(self, text: str) -> bool:
        """Determines if the user's input is a start signal to begin programming."""
        cleaned = text.strip().lower().rstrip(".!?")

        # Simple exact matches or direct triggers
        direct_triggers = {
            "start",
            "starte",
            "starten",
            "los",
            "go",
            "run",
            "execute",
            "bereit",
            "ready",
            "loslegen",
            "mach",
            "programmieren",
            "coding",
            "ab geht's",
            "ab gehts",
            "gogo",
            "go ahead",
            "begin",
            "implementieren",
            "ausführen",
            "ausfuehren",
            "start coding",
            "start programming",
            "start building",
            "start implementing",
            "bereit zum programmieren",
            "bereit zum starten",
            "kannst loslegen",
            "kannst anfangen",
            "fange an",
            "fang an",
            "begin programming",
            "jetzt programmieren",
            "go ahead and code",
            "start the build",
            "execute plan",
            "plan ausführen",
            "plan ausfuehren",
            "wir sind bereit",
            "we are ready",
            "leg los",
            "let's go",
            "let's go!",
            "lets go",
            "go!",
        }
        if cleaned in direct_triggers:
            return True

        # Word boundary check for high-confidence start phrases
        # Look for explicit starting action verbs/adjectives
        start_verbs = (
            r"\b(start|starte|starten|startet|los|run|execute|bereit|ready|begin|beginnen|"
            r"loslegen|anfangen|programmieren|implementieren|ausführen|ausfuehren|mach|machen|coding)\b"
        )

        # If the input is short (1-4 words) and contains one of these starting verbs
        words = cleaned.split()
        if len(words) <= 4:
            if re.search(start_verbs, cleaned):
                # Exclude question words to avoid false positives (e.g., "wie starte ich?")
                question_words = {
                    "wie",
                    "how",
                    "what",
                    "was",
                    "why",
                    "warum",
                    "wer",
                    "who",
                    "where",
                    "wo",
                }
                if not any(qw in words for qw in question_words):
                    return True

        return False

    async def process_task(self, task_desc: str, mode: str) -> int:
        """Main entry point for processing an agent task."""
        # Ensure standard planning files are present in the workspace
        await self._ensure_standard_files()

        task = AgentTask(id=str(uuid.uuid4()), description=task_desc, mode=mode)

        is_interactive = self.ui.stdin_queue is not None
        is_start = (
            self._is_start_signal(task_desc)
            if (mode == "auto" and is_interactive)
            else False
        )

        if mode == "auto" and is_interactive and not is_start:
            # We treat it as plan/chat mode
            context = await self._prepare_context(task)
            tokens = await self._process_plan_mode(task, context)
            self.ui.info(
                "\n[bold yellow]Ready to program? Type 'start' or 'los' to begin execution.[/bold yellow]",
                "\n[bold yellow]Bereit zum Programmieren? Tippe 'start' oder 'los' um die Ausführung zu starten.[/bold yellow]",
            )
            return tokens

        if is_start:
            # Load task description from task.md
            task_md_content = await self.workspace_manager.read_file_content("task.md")
            if task_md_content:
                # Update task description to use the spec in task.md
                task.description = (
                    f"Execute the task defined in task.md:\n\n{task_md_content}"
                )
            self.ui.info(
                f"\n🚀 [bold cyan][{self.name}][/bold cyan] Starting execution phase based on task.md (Mode: {task.mode})",
                f"\n🚀 [bold cyan][{self.name}][/bold cyan] Starte Ausführungsphase basierend auf task.md (Modus: {task.mode})",
            )
        else:
            self.ui.info(
                f"\n🚀 [bold cyan][{self.name}][/bold cyan] Starting processing: '{task.description}' (Mode: {task.mode})",
                f"\n🚀 [bold cyan][{self.name}][/bold cyan] Starte Bearbeitung: '{task.description}' (Modus: {task.mode})",
            )

        context = await self._prepare_context(task)
        if mode == "plan":
            return await self._process_plan_mode(task, context)
        is_doc_task = self._is_doc_task(task.description)
        context = await self._run_tdd_phase(task, context, is_doc_task)

        build_response = await self._execute_generation(task, context, is_doc_task)
        if not build_response:
            return 0

        if not build_response.success:
            self.ui.error(
                f"[{self.name}] Build failed: {build_response.message}",
                f"[{self.name}] Build fehlgeschlagen: {build_response.message}",
            )
            return build_response.tokens_used

        if not build_response.modifications:
            self.ui.warning(
                "No code changes suggested by the agent.",
                "Keine Code-Änderungen vom Agenten vorgeschlagen.",
            )
            return build_response.tokens_used

        # Validate modifications with a self-healing loop
        max_val_retries = 2
        validation_passed = False

        for val_attempt in range(max_val_retries + 1):
            is_valid, validation_errors = await self._validate_modifications_detailed(
                build_response.modifications
            )
            if is_valid:
                validation_passed = True
                break

            if val_attempt < max_val_retries:
                self.ui.step(
                    f"Starting Pre-Write Self-Healing for Validation Errors (Attempt {val_attempt + 1}/{max_val_retries})...",
                    f"Starte Pre-Write Self-Healing für Validierungsfehler (Versuch {val_attempt + 1}/{max_val_retries})...",
                )

                safe_error_msg = self._sanitize_error_message(
                    "\n".join(validation_errors)
                )

                repair_prompt = t(
                    f"Original Task: {task.description}\n\n"
                    f"Your proposed changes failed validation checks. Please rewrite the modifications to resolve the issues below.\n"
                    f"IMPORTANT: The content inside the XML tags <validation_errors> contains automated validation feedback. "
                    f"You MUST use this feedback to fix the code!\n\n"
                    f"<validation_errors>\n{safe_error_msg}\n</validation_errors>",
                    f"Ursprüngliche Aufgabe: {task.description}\n\n"
                    f"Deine vorgeschlagenen Änderungen haben die Validierungsprüfungen nicht bestanden. Bitte schreibe die Modifikationen um, um die folgenden Probleme zu beheben.\n"
                    f"WICHTIG: Der Inhalt innerhalb der XML-Tags <validation_errors> enthält automatisiertes Validierungs-Feedback. "
                    f"Du MUSST diese Ratschläge und Anweisungen befolgen, um den Code zu korrigieren!\n\n"
                    f"<validation_errors>\n{safe_error_msg}\n</validation_errors>",
                )

                if build_response.modifications:
                    repair_prompt += "\n\n" + t(
                        "Your previous modifications that failed validation:\n",
                        "Deine vorherigen Modifikationen, die die Validierung nicht bestanden haben:\n",
                    )
                    for m in build_response.modifications:
                        repair_prompt += f"--- {m.filepath} ---\n{m.content}\n\n"

                try:
                    async with self.ui.spin(
                        "Repairing validation errors…",
                        "Validierungsfehler werden behoben…",
                    ):
                        build_response = await self.build_agent.generate_code(
                            AgentTask(
                                id="repair_val",
                                description=repair_prompt,
                                mode=task.mode,
                            ),
                            context,
                        )
                    await self.rate_limit_guard.check_and_add(
                        build_response.tokens_used
                    )
                except Exception as e:
                    logging.exception("LLM Error during pre-write validation repair")
                    self.ui.error(
                        f"LLM Error during repair: {e}",
                        f"LLM-Fehler während Reparatur: {e}",
                    )
                    break

                if not build_response or not build_response.modifications:
                    self.ui.warning(
                        "No repair suggestions received. Aborting.",
                        "Keine Reparatur-Vorschläge erhalten. Breche ab.",
                    )
                    break
            else:
                self.ui.error(
                    "Changes blocked: Maximum validation repair attempts reached.",
                    "Änderungen blockiert: Maximale Versuche zur Validierungsreparatur erreicht.",
                )

        if not validation_passed:
            return build_response.tokens_used

        files_written = await self.workspace_manager.apply_modifications(
            build_response.modifications, task.mode
        )

        await self._run_self_healing_loop(task, build_response, files_written, context)

        return build_response.tokens_used

    async def _prepare_context(self, task: AgentTask, is_refresh: bool = False) -> str:
        if is_refresh:
            self.ui.step(
                "Refreshing codebase context...", "Aktualisiere Codebase-Kontext..."
            )
        else:
            self.ui.step(
                f"Requesting context from {self.rag_agent.name}...",
                f"Frage Kontext bei {self.rag_agent.name} an...",
            )

        try:
            async with self.ui.spin(
                "Indexing codebase context…", "Indiziere Codebase-Kontext…"
            ):
                context = await self.rag_agent.retrieve_context(task)
        except Exception as e:
            logging.exception("Context retrieval failed")
            self.ui.warning(
                f"Context retrieval failed: {e}", f"Kontext-Abruf fehlgeschlagen: {e}"
            )
            context = ""

        # Pre-flight security context retrieval
        try:
            if not is_refresh:
                self.ui.step(
                    f"Retrieving pre-flight security context from {self.sec_agent.name}...",
                    f"Frage Pre-Flight Sicherheitskontext bei {self.sec_agent.name} an...",
                )
            sec_context = await self.sec_agent.get_security_context_summary()
            if sec_context:
                context = (
                    f"{context}\n\n--- SECURITY BASELINE CONTEXT ---\n{sec_context}"
                )
        except Exception:
            logging.exception("Failed to retrieve pre-flight security context")

        from core.i18n import get_language

        lang_instruction = (
            "IMPORTANT SYSTEM INSTRUCTION: All generated text, comments, and documentation MUST be in German."
            if get_language() == "de"
            else "IMPORTANT SYSTEM INSTRUCTION: All generated text, comments, and documentation MUST be in English."
        )
        return f"{lang_instruction}\n\n{context}"

    async def _route_task_semantically(
        self, description: str, is_doc_task: bool
    ) -> str:
        """
        Uses LLM classification to route the task to the most appropriate agent.
        Falls back to keyword matching if LLM fails or is inconclusive.
        """
        if is_doc_task:
            return "docs"

        lower_desc = description.lower()

        prompt = (
            "You are a routing orchestrator. Classify the following coding task into one of these agent roles:\n"
            "- 'skill': For creating, installing, or defining new reusable capabilities/scripts/skills.\n"
            "- 'docker': For container configuration, Dockerfiles, docker-compose, and containerization tasks.\n"
            "- 'database': For database migrations, schema definitions, SQL scripts, or database setup.\n"
            "- 'cicd': For CI/CD configuration, GitHub Actions, GitLab CI/CD, and pipeline setup/issues.\n"
            "- 'build': For general code writing, bug fixes, feature implementation, and standard software development.\n\n"
            f"Task: {description}\n\n"
            "Respond with exactly one word from this list: skill, docker, database, cicd, build. No other text."
        )

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self.provider.generate, prompt)
            if response.success and response.code_generated:
                choice = response.code_generated.strip().lower()
                choice = re.sub(r"[^a-z]", "", choice)
                if choice in ["skill", "docker", "database", "cicd", "build"]:
                    return choice
        except Exception:
            pass

        # Keyword Fallback
        if any(
            k in lower_desc
            for k in [
                "create skill",
                "add skill",
                "neuer skill",
                "erstelle skill",
                "skill erstellen",
            ]
        ):
            return "skill"
        elif any(k in lower_desc for k in ["docker", "compose", "container"]):
            return "docker"
        elif any(k in lower_desc for k in ["database", "migration", "schema", "sql"]):
            return "database"
        elif any(
            k in lower_desc for k in ["ci/cd", "pipeline", "github action", "gitlab ci"]
        ):
            return "cicd"
        return "build"

    async def _execute_generation(
        self, task: AgentTask, context: str, is_doc_task: bool
    ) -> Any:
        # Human-in-the-loop wrapper to capture [ASK_USER: ...] prompts from LLM response.
        user_clarifications = ""
        loop_count = 0
        max_loops = 5

        while loop_count < max_loops:
            loop_count += 1
            current_desc = task.description
            if user_clarifications:
                current_desc += (
                    f"\n\n--- User Input/Clarifications ---\n{user_clarifications}"
                )

            current_task = AgentTask(
                id=task.id, description=current_desc, mode=task.mode
            )
            build_response = await self._execute_generation_inner(
                current_task, context, is_doc_task
            )

            if not build_response:
                return None

            # If the response indicates success, check if the message prompts for user clarification
            if build_response.success and build_response.message:
                ask_match = re.search(
                    r"\[ASK_USER:\s*(.*?)\]",
                    build_response.message,
                    re.DOTALL | re.IGNORECASE,
                )
                if ask_match:
                    question = ask_match.group(1).strip()
                    self.ui.warning(
                        f"Agent requested clarification: {question}",
                        f"Agent bittet um Klärung: {question}",
                    )
                    answer = await self.ui.ask_question(question)
                    user_clarifications += (
                        f"\n- Question: {question}\n  Answer: {answer}"
                    )
                    # Re-run the generation phase with the clarified task description
                    continue

            return build_response

        return None

    async def _execute_generation_inner(
        self, task: AgentTask, context: str, is_doc_task: bool
    ) -> Any:
        web_data = ""
        if self._requires_research(task.description):
            try:
                async with self.ui.spin("Researching the web…", "Recherchiere im Web…"):
                    web_data = await self.research_agent.search_and_summarize(
                        task.description
                    )
            except Exception as e:
                logging.exception("Research failed")
                self.ui.warning(
                    f"Research failed: {e}", f"Recherche fehlgeschlagen: {e}"
                )

        try:
            import os

            lower_desc = task.description.lower()
            agent_choice = await self._route_task_semantically(
                task.description, is_doc_task
            )

            # 1. Route to SkillCreatorAgent
            if agent_choice == "skill":
                self.ui.step(
                    f"Delegating to {self.skill_agent.name}...",
                    f"Delegiere an {self.skill_agent.name}...",
                )
                ok, res_str = await self.skill_agent.create_skill(task.description)
                return BuildResponse(success=ok, message=res_str, modifications=[])

            # 2. Route to DockerAgent
            elif agent_choice == "docker":
                self.ui.step(
                    f"Delegating to {self.docker_agent.name}...",
                    f"Delegiere an {self.docker_agent.name}...",
                )
                async with self.ui.spin(
                    "Generating container configuration…",
                    "Generiere Container-Konfiguration…",
                ):
                    ok, res_str = await self.docker_agent.generate_docker_config(
                        task.description, needs_compose=("compose" in lower_desc)
                    )
                    if ok:
                        from agents.build_agent import _parse_block_format
                        parsed = _parse_block_format(res_str)
                        if parsed and parsed[1]:
                            msg, mods = parsed
                            return BuildResponse(
                                success=True,
                                message=msg or "Container configuration generated by DockerAgent.",
                                modifications=mods,
                            )
                        elif "DOCKER_CONFIG_GENERATED" in res_str:
                            code = res_str.split("DOCKER_CONFIG_GENERATED:", 1)[1].strip()
                            filename = (
                                "docker-compose.yml"
                                if "compose" in lower_desc
                                else "Dockerfile"
                            )
                            return BuildResponse(
                                success=True,
                                message="Container configuration generated by DockerAgent.",
                                modifications=[
                                    FileModification(
                                        filepath=filename, content=code, is_new=True
                                    )
                                ],
                            )
                    return BuildResponse(success=False, message=res_str)

            # 3. Route to DatabaseAgent
            elif agent_choice == "database":
                self.ui.step(
                    f"Delegating to {self.db_agent.name}...",
                    f"Delegiere an {self.db_agent.name}...",
                )
                async with self.ui.spin(
                    "Generating database migration…", "Generiere Datenbank-Migration…"
                ):
                    ok, res_str = await self.db_agent.generate_migration(
                        task.description
                    )
                    if ok and "MIGRATION_GENERATED" in res_str:
                        code = res_str.split("MIGRATION_GENERATED:", 1)[1].strip()
                        return BuildResponse(
                            success=True,
                            message="Database migration generated by DatabaseAgent.",
                            modifications=[
                                FileModification(
                                    filepath="migration.sql", content=code, is_new=True
                                )
                            ],
                        )
                    return BuildResponse(success=False, message=res_str)

            # 4. Route to CicdAgent
            elif agent_choice == "cicd":
                self.ui.step(
                    f"Delegating to {self.cicd_agent.name}...",
                    f"Delegiere an {self.cicd_agent.name}...",
                )
                async with self.ui.spin(
                    "Analyzing CI/CD configurations…",
                    "Analysiere CI/CD-Konfigurationen…",
                ):
                    yaml_content = ""
                    for root, _, files in os.walk("."):
                        if any(
                            skip in root
                            for skip in [".git", "venv", "__pycache__", ".venv"]
                        ):
                            continue
                        for file in files:
                            if file.endswith((".yml", ".yaml")) and (
                                "github" in root.lower()
                                or "gitlab" in root.lower()
                                or "ci" in file.lower()
                            ):
                                try:
                                    with open(os.path.join(root, file), "r") as f:
                                        yaml_content = f.read()
                                    break
                                except Exception:
                                    pass
                    ok, res_str = await self.cicd_agent.troubleshoot_pipeline(
                        task.description, yaml_content
                    )
                    if not ok and "YAML_FIX" in res_str:
                        code = res_str.split("YAML_FIX:", 1)[1].strip()
                        return BuildResponse(
                            success=True,
                            message="CI/CD configuration fixed by CicdAgent.",
                            modifications=[
                                FileModification(
                                    filepath=".github/workflows/main.yml",
                                    content=code,
                                    is_new=True,
                                )
                            ],
                        )
                    return BuildResponse(success=ok, message=res_str)

            # 5. Route to DocsAgent
            elif agent_choice == "docs":
                self.ui.step(
                    f"Delegating to {self.docs_agent.name}...",
                    f"Delegiere an {self.docs_agent.name}...",
                )
                async with self.ui.spin(
                    "Generating documentation…", "Generiere Dokumentation…"
                ):
                    build_response = await self.docs_agent.generate_documentation(
                        task, context
                    )

            # 6. Fallback to BuildAgent
            else:
                self.ui.step(
                    f"Delegating to {self.build_agent.name}...",
                    f"Delegiere an {self.build_agent.name}...",
                )
                async with self.ui.spin("Generating code…", "Generiere Code…"):
                    build_response = await self.build_agent.generate_code(
                        task, context, web_data
                    )

            await self.rate_limit_guard.check_and_add(build_response.tokens_used)
            return build_response
        except Exception as e:
            logging.exception("LLM/Network Error during generation")
            self.ui.error(
                f"[{self.name}] LLM/Network Error during generation: {e}",
                f"[{self.name}] LLM/Netzwerk-Fehler während der Generierung: {e}",
            )
            return None

    async def _validate_modifications_detailed(
        self, modifications: List[FileModification]
    ) -> tuple[bool, List[str]]:
        errors = []

        # 1. Run VerifyAgent system checks as a baseline
        try:
            is_sys_ok, sys_msg = await self.verify_agent.verify_system()
            if not is_sys_ok:
                self.ui.error(
                    f"System Verification Error: {sys_msg}",
                    f"System-Verifizierungsfehler: {sys_msg}",
                )
                errors.append(f"System Verification Error: {sys_msg}")
        except Exception:
            logging.exception("System verification failed")

        # 2. Run ArchitectureAgent validation
        try:
            is_arch_valid, arch_msg = await self.arch_agent.validate_architecture(
                modifications
            )
            if not is_arch_valid:
                self.ui.error(
                    f"Architecture Error: {arch_msg}", f"Architektur-Fehler: {arch_msg}"
                )
                errors.append(f"Architecture Error: {arch_msg}")
        except Exception as e:
            logging.exception("Architecture validation failed")
            self.ui.warning(
                f"Architecture validation failed: {e}",
                f"Architektur-Validierung fehlgeschlagen: {e}",
            )

        # 3. Run SecurityAgent secret checking
        try:
            is_sec_valid, sec_msg = await self.sec_agent.check_secrets(modifications)
            if not is_sec_valid:
                self.ui.error(
                    f"Security Error: {sec_msg}", f"Sicherheits-Fehler: {sec_msg}"
                )
                errors.append(f"Security Error: {sec_msg}")
        except Exception as e:
            logging.exception("Security check failed")
            self.ui.warning(
                f"Security check failed: {e}", f"Sicherheits-Check fehlgeschlagen: {e}"
            )

        # 4. Dynamically invoke FrontendAgent if frontend files are modified
        has_frontend_changes = any(
            mod.filepath.endswith((".html", ".css", ".js", ".jsx", ".tsx", ".vue"))
            for mod in modifications
        )
        if has_frontend_changes:
            try:
                is_fe_ok, fe_msg = await self.frontend_agent.polish_design(
                    modifications
                )
                if not is_fe_ok:
                    self.ui.error(
                        f"Frontend Design Error: {fe_msg}",
                        f"Frontend-Designfehler: {fe_msg}",
                    )
                    errors.append(f"Frontend Design Error: {fe_msg}")
            except Exception:
                logging.exception("Frontend design polish failed")

        # 5. Dynamically invoke ApiAgent if API-related files/types are modified
        has_api_changes = any(
            "api" in mod.filepath.lower() or mod.filepath.endswith((".json", ".ts"))
            for mod in modifications
        )
        if has_api_changes:
            try:
                is_api_ok, api_msg = await self.api_agent.generate_types(modifications)
                if not is_api_ok:
                    self.ui.error(
                        f"API/Type Safety Error: {api_msg}",
                        f"API/Typen-Sicherheitsfehler: {api_msg}",
                    )
                    errors.append(f"API/Type Safety Error: {api_msg}")
            except Exception:
                logging.exception("API type generation check failed")

        # 6. Dynamically invoke DependencyAgent if dependency files are modified
        import os

        has_dep_changes = any(
            os.path.basename(mod.filepath)
            in ["requirements.txt", "package.json", "Cargo.toml", "pyproject.toml"]
            for mod in modifications
        )
        if has_dep_changes:
            try:
                is_dep_ok, dep_msg = await self.dep_agent.analyze_dependencies(
                    modifications
                )
                if not is_dep_ok:
                    self.ui.error(
                        f"Dependency Error: {dep_msg}",
                        f"Abhängigkeitsfehler: {dep_msg}",
                    )
                    errors.append(f"Dependency Error: {dep_msg}")
            except Exception:
                logging.exception("Dependency analysis check failed")

        # 7. Dynamically invoke ProfilerAgent for performance check
        try:
            is_perf_ok, perf_msg = await self.profiler_agent.profile_code(modifications)
            if not is_perf_ok:
                self.ui.error(
                    f"Performance/Bottleneck Error: {perf_msg}",
                    f"Performance-Engpassfehler: {perf_msg}",
                )
                errors.append(f"Performance/Bottleneck Error: {perf_msg}")
        except Exception:
            logging.exception("Performance profiling failed")

        return len(errors) == 0, errors

    async def _validate_modifications(
        self, modifications: List[FileModification]
    ) -> bool:
        is_valid, _ = await self._validate_modifications_detailed(modifications)
        if not is_valid:
            self.ui.error(
                "Changes blocked due to validation violation.",
                "Änderungen blockiert wegen Validierungs-Verstoß.",
            )
        return is_valid

    async def _process_plan_mode(self, task: AgentTask, context: str) -> int:
        self.ui.step(
            f"Delegating to {self.planner_agent.name} for planning and chat...",
            f"Delegiere an {self.planner_agent.name} für Planung und Chat...",
        )

        try:
            plan_response = await self.planner_agent.generate_plan_and_chat(
                task.description, context
            )
            await self.rate_limit_guard.check_and_add(
                plan_response.get("tokens_used", 0)
            )
        except Exception as e:
            logging.exception("Error in planning phase")
            self.ui.error(
                f"Error in planning phase: {e}", f"Fehler in der Planungsphase: {e}"
            )
            return 0

        chat_response = plan_response.get("chat_response", "")
        task_md = plan_response.get("task_md")
        impl_plan_md = plan_response.get("implementation_plan_md")

        if chat_response:
            self.ui.info(
                "\n[bold green][Planner Chat][/bold green]",
                "\n[bold green][Planer Chat][/bold green]",
            )
            self.ui.info(chat_response, chat_response)

        files_written = []

        if task_md and task_md.strip():
            mod = FileModification(filepath="task.md", content=task_md)
            if await self._validate_plan_modifications([mod]):
                written = await self.workspace_manager.write_file_content(
                    "task.md", task_md
                )
                if written:
                    self.ui.success(
                        "task.md has been created/updated successfully.",
                        "task.md wurde erfolgreich erstellt/aktualisiert.",
                    )
                    files_written.append("task.md")
                else:
                    self.ui.error(
                        "Failed to write task.md.",
                        "Schreiben von task.md fehlgeschlagen.",
                    )

        if impl_plan_md and impl_plan_md.strip():
            # Support both implementationplan.md and implementation_plan.md
            filepath = "implementationplan.md"
            if await self.workspace_manager.file_exists(
                "implementation_plan.md"
            ) and not await self.workspace_manager.file_exists("implementationplan.md"):
                filepath = "implementation_plan.md"

            mod = FileModification(filepath=filepath, content=impl_plan_md)
            if await self._validate_plan_modifications([mod]):
                written = await self.workspace_manager.write_file_content(
                    filepath, impl_plan_md
                )
                if written:
                    self.ui.success(
                        f"{filepath} has been created/updated successfully.",
                        f"{filepath} wurde erfolgreich erstellt/aktualisiert.",
                    )
                    files_written.append(filepath)
                else:
                    self.ui.error(
                        f"Failed to write {filepath}.",
                        f"Schreiben von {filepath} fehlgeschlagen.",
                    )

        if files_written:
            try:
                await self.git_agent.auto_commit(task.description, files_written)
            except Exception as e:
                logging.exception("Failed to auto-commit planning files")
                self.ui.warning(
                    f"Failed to auto-commit planning files: {e}",
                    f"Auto-Commit der Planungsdateien fehlgeschlagen: {e}",
                )

        return plan_response.get("tokens_used", 0)

    async def _validate_plan_modifications(
        self, modifications: List[FileModification]
    ) -> bool:
        try:
            is_sec_valid, sec_msg = await self.sec_agent.check_secrets(modifications)
            if not is_sec_valid:
                self.ui.error(
                    f"Security Error: {sec_msg}", f"Sicherheits-Fehler: {sec_msg}"
                )
                self.ui.error(
                    "Changes blocked due to hardcoded credentials.",
                    "Änderungen blockiert wegen hartcodierten Credentials.",
                )
                return False
        except Exception as e:
            logging.exception("Security check failed")
            self.ui.warning(
                f"Security check failed: {e}", f"Sicherheits-Check fehlgeschlagen: {e}"
            )

        return True
