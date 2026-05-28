import asyncio
import os
import re
from typing import List, Tuple
from rich.console import Console
from core.base_agent import BaseAgent
from core.models import FileModification
from tools.command_runner import CommandRunner
from core.i18n import t

console = Console()

class SecurityAgent(BaseAgent):
    def __init__(self):
        self._name = "Security-Agent"
        self._dependency_cache = None
        self._last_dependency_check_time = 0

    @property
    def name(self) -> str:
        return self._name

    async def _ensure_installed(self, package: str, binary_name: str = None) -> bool:
        """
        Ensures that a package or tool is installed in the current Python environment.
        """
        import importlib.util
        import shutil
        import sys

        # Quick check: Is it already importable?
        if binary_name is None:
            try:
                if importlib.util.find_spec(package) is not None:
                    return True
            except Exception:
                pass
        else:
            # Quick check: Does the binary exist in PATH?
            if shutil.which(binary_name) is not None:
                return True
            # Or is the module importable?
            try:
                if importlib.util.find_spec(package) is not None:
                    return True
            except Exception:
                pass

        # Human-in-the-Loop (HITL) approval
        if "pytest" in sys.modules or os.environ.get("TEST_MODE") == "1":
            approved = True
        else:
            prompt_str = t(f"Security tool/package '{package}' is missing. Install it? (y/n) [y]: ",
                           f"Sicherheits-Tool/Paket '{package}' fehlt. Installieren? (y/n) [y]: ")
            if getattr(self, "ui", None) is not None:
                approved = await self.ui.ask_confirm(prompt_str)
            else:
                from rich.prompt import Confirm
                approved = await asyncio.to_thread(Confirm.ask, prompt_str)

        if not approved:
            console.print(t(f"   -> [bold yellow][{self.name}][/bold yellow] Skipping installation of '{package}' (rejected by user).",
                            f"   -> [bold yellow][{self.name}][/bold yellow] Überspringe Installation von '{package}' (vom Benutzer abgelehnt)."))
            return False

        console.print(t(f"   -> [bold yellow][{self.name}][/bold yellow] Installing missing security package '{package}'...",
                        f"   -> [bold yellow][{self.name}][/bold yellow] Installiere fehlendes Sicherheits-Paket '{package}'..."))
        try:
            # We use sys.executable to install in the same environment (e.g. .venv)
            result = await CommandRunner.run_async([sys.executable, "-m", "pip", "install", package])
            if result.returncode == 0:
                console.print(t(f"   -> [bold green][{self.name}][/bold green] Successfully installed '{package}'.",
                                f"   -> [bold green][{self.name}][/bold green] '{package}' erfolgreich installiert."))
                return True
            else:
                console.print(t(f"   -> [bold red][{self.name}][/bold red] Failed to install '{package}': {result.stderr}",
                                f"   -> [bold red][{self.name}][/bold red] Fehler beim Installieren von '{package}': {result.stderr}"))
                return False
        except Exception as e:
            console.print(t(f"   -> [bold red][{self.name}][/bold red] Exception during installation of '{package}': {e}",
                            f"   -> [bold red][{self.name}][/bold red] Ausnahme bei der Installation von '{package}': {e}"))
            return False

    async def get_security_context_summary(self) -> str:
        """
        Returns a summary of the security status for the BuildAgent.
        Uses caching for dependency checks to avoid performance bottlenecks.
        """
        # Ensure defusedxml is installed
        await self._ensure_installed("defusedxml")

        summary_parts = []
        requirements_path = "requirements.txt"
        if os.path.exists(requirements_path):
            try:
                mtime = os.path.getmtime(requirements_path)
                if self._dependency_cache is None or mtime > self._last_dependency_check_time:
                    ok, msg = await self.check_dependencies()
                    self._dependency_cache = "" if ok else msg
                    self._last_dependency_check_time = mtime
                
                if self._dependency_cache:
                    summary_parts.append(f"VULNERABLE DEPENDENCIES DETECTED:\n{self._dependency_cache}")
            except Exception as e:
                console.print(t(f"[dim]Error caching dependency security context: {e}[/dim]",
                                f"[dim]Fehler beim Cachen des Dependency-Sicherheitskontexts: {e}[/dim]"))

        summary_parts.append(
            "SECURITY GUIDELINES & CONSTRAINTS:\n"
            "- Never hardcode API keys, passwords, or credentials. Use environment variables (.env).\n"
            "- Protect against injection vulnerabilities (e.g. command injection, SQL injection).\n"
            "- When parsing/loading XML, do NOT use xml.etree.ElementTree; use defusedxml instead. However, for type annotations and isinstance checks, use xml.etree.ElementTree.Element (since defusedxml parses to standard Element objects, but its own module lacks the 'Element' attribute)."
        )

        return "\n\n".join(summary_parts)

    async def check_secrets(self, modifications: List[FileModification]) -> Tuple[bool, str]:
        console.print(t(f"   -> [bold yellow][{self.name}][/bold yellow] Running in-memory secret scanning...",
                        f"   -> [bold yellow][{self.name}][/bold yellow] Führe In-Memory Secret-Scanning durch..."))
        secret_patterns = [
            (r"(api_key|apikey|token|password|secret|pwd)\s*=\s*['\"][a-zA-Z0-9_\-]{10,}['\"]", "Potential hardcoded secret or credential found"),
            (r"sk-[a-zA-Z0-9]{48}", "OpenAI API Key found"),
            (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token found"),
            (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID found"),
            (r"amzn\.mws\.[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "Amazon MWS Auth Token found"),
            (r"AIza[0-9A-Za-z\-_]{35}", "Google API Key found"),
            (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "Private Key found"),
            (r"xox[baprs]-[0-9a-zA-Z]{10,48}", "Slack API Token found"),
            (r"sk_live_[0-9a-zA-Z]{24}", "Stripe API Key found"),
            (r"(postgresql|mongodb|mysql|redis)://[a-zA-Z0-9_]+:[a-zA-Z0-9_@.:/]+", "Database connection string containing credentials found")
        ]

        for mod in modifications:
            if mod.filepath.lower().endswith((".md", ".txt", ".rst")):
                continue
            for pattern, description in secret_patterns:
                if re.search(pattern, mod.content, re.IGNORECASE):
                    msg = f"Security risk in {mod.filepath}: {description}. Please use environment variables (.env) instead of hardcoded credentials!"
                    return False, msg
        return True, ""

    async def run_vulnerability_scan(self) -> Tuple[bool, str]:
        console.print(t(f"   -> [bold yellow][{self.name}][/bold yellow] Running vulnerability scan (Bandit & Semgrep)...",
                        f"   -> [bold yellow][{self.name}][/bold yellow] Führe Vulnerability-Scan (Bandit & Semgrep) durch..."))
        await asyncio.sleep(0.1)
        
        errors = []
        
        # 1. Run Bandit (Python SAST)
        await self._ensure_installed("bandit", "bandit")
        try:
            result = await CommandRunner.run_async(["bandit", "-r", ".", "-ll", "-ii", "-q", "-x", "./.venv,./.pytest_cache,./__pycache__,./.ruff_cache"])
            if result.returncode != 0 and result.stdout.strip():
                errors.append(f"Bandit SAST scan found security issues:\n{result.stdout}")
        except Exception as e:
            console.print(t(f"[dim]Error running Bandit: {e}[/dim]",
                            f"[dim]Fehler beim Ausführen von Bandit: {e}[/dim]"))

        # 2. Run Semgrep (Multi-language SAST)
        has_semgrep = await self._ensure_installed("semgrep", "semgrep")
        if has_semgrep:
            try:
                # We use --error to exit with non-zero if findings are found
                result = await CommandRunner.run_async([
                    "semgrep", "scan", "--config=auto", "--quiet", "--error",
                    "--exclude=.venv", "--exclude=venv", "--exclude=.pytest_cache",
                    "--exclude=__pycache__", "--exclude=.ruff_cache", "--exclude=node_modules"
                ])
                if result.returncode != 0 and result.stdout.strip():
                    errors.append(f"Semgrep SAST scan found security issues:\n{result.stdout}")
            except Exception as e:
                console.print(t(f"[dim]Semgrep run failed or offline: {e}. Skipping Semgrep check.[/dim]",
                                f"[dim]Semgrep-Ausführung fehlgeschlagen oder offline: {e}. Überspringe Semgrep-Prüfung.[/dim]"))
                                
        if errors:
            return False, "\n\n".join(errors)
        return True, ""
        
    async def check_dependencies(self) -> Tuple[bool, str]:
        import sys
        
        # 1. Skip global check if we are not in a venv and no requirements.txt exists
        in_venv = sys.prefix != sys.base_prefix or 'VIRTUAL_ENV' in os.environ
        has_reqs = os.path.exists("requirements.txt")
        if not has_reqs and not in_venv:
            console.print(t(f"   -> [bold yellow][{self.name}][/bold yellow] Skipping dependency check (not in virtual environment and no requirements.txt found).",
                            f"   -> [bold yellow][{self.name}][/bold yellow] Überspringe Dependency-Check (keine virtuelle Umgebung und keine requirements.txt gefunden)."))
            return True, ""

        console.print(t(f"   -> [bold yellow][{self.name}][/bold yellow] Checking dependencies for CVEs (pip-audit)...",
                        f"   -> [bold yellow][{self.name}][/bold yellow] Prüfe Abhängigkeiten auf CVEs (pip-audit)..."))
        
        # Ensure pip-audit is installed
        await self._ensure_installed("pip-audit", "pip-audit")

        try:
            cmd = ["pip-audit"]
            if has_reqs:
                cmd = ["pip-audit", "-r", "requirements.txt"]
                
            result = await CommandRunner.run_async(cmd)
            if result.returncode != 0:
                if "command not found" in result.stderr or "No module named" in result.stderr:
                    console.print(t("[dim]pip-audit not installed, skipping dependency check.[/dim]",
                                    "[dim]pip-audit nicht installiert, überspringe Dependency-Check.[/dim]"))
                    return True, ""
                
                # Parse vulnerabilities from pip-audit output
                vulnerabilities = []
                lines = result.stdout.splitlines()
                start_parsing = False
                for line in lines:
                    if "Name" in line and "Version" in line and "ID" in line:
                        start_parsing = True
                        continue
                    if start_parsing:
                        if line.startswith("---") or not line.strip():
                            continue
                        if "Skip Reason" in line or "Name" in line:
                            break
                        parts = line.split()
                        if len(parts) >= 4:
                            pkg_name = parts[0]
                            parts[1]
                            parts[2]
                            fix_version = parts[3]
                            # Filter valid versions
                            if fix_version and not fix_version.startswith("CVE") and not fix_version.startswith("PYSEC") and not fix_version.startswith("GHSA"):
                                vulnerabilities.append((pkg_name, fix_version))
                
                if vulnerabilities:
                    unique_vulns = {}
                    for pkg, fix in vulnerabilities:
                        unique_vulns[pkg] = fix
                    
                    vuln_list_str = ", ".join([f"{pkg} (to {fix})" for pkg, fix in unique_vulns.items()])
                    console.print(t(f"[bold yellow]WARNING: Found fixable vulnerable dependencies: {vuln_list_str}[/bold yellow]",
                                    f"[bold yellow]WARNUNG: Behebbare Sicherheitslücken in Abhängigkeiten gefunden: {vuln_list_str}[/bold yellow]"))
                    
                    # HITL confirmation for auto-upgrade
                    if "pytest" in sys.modules or os.environ.get("TEST_MODE") == "1":
                        approved = True
                    else:
                        prompt_str = t("Would you like the agent to auto-upgrade these packages? (y/n) [y]: ",
                                       "Möchtest du, dass der Agent diese Pakete automatisch aktualisiert? (y/n) [y]: ")
                        if getattr(self, "ui", None) is not None:
                            approved = await self.ui.ask_confirm(prompt_str)
                        else:
                            from rich.prompt import Confirm
                            approved = await asyncio.to_thread(Confirm.ask, prompt_str)
                            
                    if approved:
                        await self._fix_dependencies(unique_vulns)
                        return True, ""
                
                # If not fixable or not approved
                msg = f"Vulnerable dependencies found:\n{result.stdout}\nPlease consider updating the affected packages."
                console.print(t(f"[bold yellow]WARNING: {msg}[/bold yellow]", 
                                f"[bold yellow]WARNUNG: {msg}[/bold yellow]"))
                return True, ""
        except Exception as e:
            console.print(t(f"[dim]Error running pip-audit: {e}[/dim]",
                            f"[dim]Fehler bei pip-audit: {e}[/dim]"))
        return True, ""

    async def _fix_dependencies(self, vulns: dict):
        import sys
        # 1. Update requirements.txt if present
        req_path = "requirements.txt"
        if os.path.exists(req_path):
            try:
                with open(req_path, "r") as f:
                    lines = f.readlines()
                
                new_lines = []
                for line in lines:
                    matched = False
                    for pkg, fix in vulns.items():
                        pattern = r"^(" + re.escape(pkg) + r")([>=<~]*)(.*)$"
                        match = re.match(pattern, line.strip(), re.IGNORECASE)
                        if match:
                            new_lines.append(f"{pkg}=={fix}\n")
                            matched = True
                            break
                    if not matched:
                        new_lines.append(line)
                
                with open(req_path, "w") as f:
                    f.writelines(new_lines)
                console.print(t(f"   -> [bold green][{self.name}][/bold green] Updated requirements.txt.",
                                f"   -> [bold green][{self.name}][/bold green] requirements.txt wurde aktualisiert."))
            except Exception as e:
                console.print(t(f"   -> [bold red][{self.name}][/bold red] Failed to update requirements.txt: {e}",
                                f"   -> [bold red][{self.name}][/bold red] Fehler beim Aktualisieren von requirements.txt: {e}"))

        # 2. Run pip install to update packages in the environment
        for pkg, fix in vulns.items():
            console.print(t(f"   -> [bold yellow][{self.name}][/bold yellow] Upgrading {pkg} to {fix}...",
                            f"   -> [bold yellow][{self.name}][/bold yellow] Aktualisiere {pkg} auf {fix}..."))
            try:
                result = await CommandRunner.run_async([sys.executable, "-m", "pip", "install", f"{pkg}=={fix}"])
                if result.returncode == 0:
                    console.print(t(f"   -> [bold green][{self.name}][/bold green] Successfully upgraded {pkg}.",
                                    f"   -> [bold green][{self.name}][/bold green] {pkg} erfolgreich aktualisiert."))
                else:
                    console.print(t(f"   -> [bold red][{self.name}][/bold red] Failed to upgrade {pkg}: {result.stderr}",
                                    f"   -> [bold red][{self.name}][/bold red] Fehler beim Upgrade von {pkg}: {result.stderr}"))
            except Exception as e:
                console.print(t(f"   -> [bold red][{self.name}][/bold red] Exception upgrading {pkg}: {e}",
                                f"   -> [bold red][{self.name}][/bold red] Ausnahme beim Upgrade von {pkg}: {e}"))
