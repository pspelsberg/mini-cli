import asyncio
from typing import Tuple
from rich.console import Console

from core.base_agent import BaseAgent
from providers import ProviderFactory
from core.i18n import t, get_language

console = Console()

class CicdAgent(BaseAgent):
    """
    Skill 14: CI/CD Pipeline-Troubleshooter
    Analysiert Pipeline Logs und korrigiert YAML-Konfigurationen für GitHub Actions / GitLab CI.
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "CICD-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def troubleshoot_pipeline(self, log_content: str, yaml_content: str = "") -> Tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Analyzing CI/CD logs and configuration...",
                        f"[bold yellow][{self.name}][/bold yellow] Analysiere CI/CD Logs und Konfiguration..."))
        await asyncio.sleep(0.5)

        if not log_content.strip():
            return True, "Keine Logs zur Analyse bereitgestellt."

        lang = get_language()
        if lang == "de":
            prompt = (
                "Du bist ein DevOps und CI/CD Experte. Analysiere die folgenden Pipeline-Logs und "
                "die optionale YAML-Konfigurationsdatei, um den Fehlergrund zu finden.\n"
                "Schlage eine konkrete Lösung (z. B. Anpassung im YAML, Caching-Optimierung oder fehlende Dependencies) vor.\n"
                "Wenn du einen Fehler in der YAML-Datei findest, antworte beginnend mit 'YAML_FIX:\n<neuer_yaml_code>'.\n"
                "Ansonsten erkläre das Problem beginnend mit 'ANALYSIS:\n'.\n\n"
                f"Logs:\n{log_content}\n\n"
            )
        else:
            prompt = (
                "You are a DevOps and CI/CD expert. Analyze the following pipeline logs and "
                "the optional YAML configuration file to find the root cause of the error.\n"
                "Suggest a concrete solution (e.g. adjustments in YAML, caching optimization or missing dependencies).\n"
                "If you find an error in the YAML file, reply starting with 'YAML_FIX:\n<new_yaml_code>'.\n"
                "Otherwise explain the issue starting with 'ANALYSIS:\n'.\n\n"
                f"Logs:\n{log_content}\n\n"
            )
        if yaml_content:
            prompt += f"CI/CD Config:\n{yaml_content}\n"
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            if result.startswith("YAML_FIX"):
                console.print(t("[dim]CI/CD configuration (fix proposal) generated.[/dim]",
                                "[dim]CI/CD Konfiguration (Fix-Vorschlag) generiert.[/dim]"))
                return False, result # False signalisiert, dass ein Fix angewendet werden muss
            elif result.startswith("ANALYSIS"):
                return True, result
                
        return False, "Fehler bei der Analyse der Pipeline-Logs."

    async def validate_cicd_configs(self, modifications: list = None) -> tuple[bool, str]:
        """
        Scans the workspace or modified files for CI/CD pipeline configurations (GitHub Workflows, GitLab CI).
        Validates them for YAML syntax and basic security patterns.
        """
        import os
        import yaml
        
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Validating CI/CD pipeline configurations...",
                        f"[bold yellow][{self.name}][/bold yellow] Validierung der CI/CD-Pipeline-Konfigurationen..."))
        await asyncio.sleep(0.1)
        
        cicd_files = []
        
        # If modifications list is passed, check them first
        if modifications:
            for mod in modifications:
                path = mod.filepath.lower()
                if ".github/workflows/" in path or ".gitlab-ci.yml" in path:
                    cicd_files.append((mod.filepath, mod.content))
                    
        # Otherwise scan workspace files
        if not cicd_files:
            for root, _, files in os.walk("."):
                # Exclude virtual environments / build dirs
                if any(x in root for x in [".venv", "venv", "node_modules", ".git", ".github/actions"]):
                    continue
                for f in files:
                    filepath = os.path.join(root, f)
                    if (".github/workflows/" in filepath or f == ".gitlab-ci.yml") and (f.endswith(".yml") or f.endswith(".yaml")):
                        try:
                            with open(filepath, "r", encoding="utf-8") as file:
                                cicd_files.append((filepath, file.read()))
                        except Exception:
                            pass
                            
        if not cicd_files:
            return True, "No CI/CD configuration files found to validate."
            
        for path, content in cicd_files:
            if not content.strip():
                continue
                
            # 1. Parse YAML to check for syntax errors
            try:
                data = yaml.safe_load(content)
            except yaml.YAMLError as exc:
                return False, f"Syntax error in CI/CD file {path}:\n{exc}"
                
            # 2. Check for security issues: unpinned third-party actions
            if ".github/workflows/" in path and data and "jobs" in data:
                for job_name, job_data in data["jobs"].items():
                    if not isinstance(job_data, dict):
                        continue
                    steps = job_data.get("steps", [])
                    if isinstance(steps, list):
                        for step in steps:
                            uses_action = step.get("uses")
                            if uses_action and "@" in uses_action:
                                action_ref = uses_action.split("@")[1]
                                # Check if it's a version tag (v1, v2, etc.) and not a full 40-character SHA hash
                                if len(action_ref) != 40 or not all(c in "0123456789abcdef" for c in action_ref.lower()):
                                    console.print(t(
                                        f"[bold yellow][{self.name} WARNING][/bold yellow] Unpinned third-party action in {path} ({uses_action}). Recommended: pin to commit SHA.",
                                        f"[bold yellow][{self.name} WARNUNG][/bold yellow] Ungepinnte Drittanbieter-Action in {path} ({uses_action}). Empfohlen: Auf Commit-SHA pinnen."
                                    ))
                                    
        return True, "CI/CD configurations are syntactically valid."
