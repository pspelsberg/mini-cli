import asyncio
from typing import List, Tuple
from rich.console import Console

from core.models import FileModification
from core.base_agent import BaseAgent
from providers import ProviderFactory
from core.i18n import t, get_language

console = Console()

class ReviewAgent(BaseAgent):
    """
    Skill 2: Code-Reviewer & Simplifier
    Analyzes existing files for 'code smells', complexity, and readability.
    Suggests refactoring opportunities and simplifications.
    """
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Review-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)
        self.last_findings = None

    @property
    def name(self) -> str:
        return self._name

    async def review_code(self, modifications: List[FileModification], only_critical: bool = False) -> Tuple[bool, str]:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Starting code review and searching for simplifications...",
                        f"[bold yellow][{self.name}][/bold yellow] Starte Code-Review und suche nach Vereinfachungen..."))
        await asyncio.sleep(0.5)
        
        self.last_findings = None
        
        if not modifications:
            return True, "Keine Code-Änderungen zu prüfen."

        lang = get_language()
        if lang == "de":
            prompt = (
                "Du agierst als erfahrener Senior Developer und Software-Architekt. Deine Aufgabe ist es, den bereitgestellten "
                "Code einer tiefgehenden, kritischen Review zu unterziehen. Prüfe den Code anhand etablierter Industriestandards "
                "und strukturiere dein Feedback auf Deutsch in die folgenden Abschnitte:\n\n"
                "1. Sicherheitsanalyse (Security)\n"
                "- Prüfe auf bekannte Sicherheitslücken (orientiere dich an den OWASP Top 10, z. B. Injection, fehlerhafte Authentifizierung, Datenlecks).\n"
                "- Identifiziere Hardcoded Secrets (API-Keys, Passwörter) oder unsichere Bibliotheken.\n"
                "- SYSTEM-GUARDS PRÜFUNG: Melde es als [KRITISCH], wenn 'xml.etree.ElementTree' anstelle von 'defusedxml' für das eigentliche XML-Parsing/Laden verwendet wird. Hinweis: Typhinweise und isinstance-Prüfungen mittels 'xml.etree.ElementTree.Element' sind erlaubt und erwünscht, da defusedxml selbst kein 'Element'-Attribut besitzt. Melde hartcodierte Skriptdateien/Strings als [WARNUNG].\n\n"
                "2. Architektur & Design (\"Anti-Spaghetti-Check\")\n"
                "- Analysiere die Struktur: Werden die SOLID-Prinzipien und Separation of Concerns eingehalten?\n"
                "- Prüfe auf Code Smells (zu lange Methoden/Klassen, tiefe Schachtelungen, redundanter Code / DRY-Prinzip).\n"
                "- Ist die Architektur modular, wartbar und zukunftsfähig?\n"
                "- MODULARITY-CHECK: Melde fehlende Separation of Concerns (z.B. Node-Erstellung, Positionierung, Verbindungslogik in einer einzigen Monster-Methode) als [WARNUNG] und fordere Refactoring in spezialisierte Hilfsklassen/Funktionen.\n\n"
                "3. Logik, Performance & Robustheit\n"
                "- Suche nach versteckten Logikfehlern, Edge Cases, Endlosschleifen oder Memory Leaks.\n"
                "- Prüfe das Error Handling: Werden Fehler sauber abgefangen oder bricht das Programm unkontrolliert ab?\n"
                "- Gibt es offensichtliche Performance-Flaschenhälse?\n"
                "- DEFENSIVE PROGRAMMING CHECK: Melde fehlende Attributvalidierung (z.B. direkter Zugriff über 'attrib[\"x\"]' statt '.get(\"x\")') als [KRITISCH], falls ungültige Eingaben KeyErrors verursachen könnten.\n\n"
                "4. Sprachliche Konsistenz & Konventionen\n"
                "- Der Code selbst (Variablen, Funktionen, Dokumentation/Docstrings) muss sprachlich sauber und konsistent sein (bevorzugt britisches oder amerikanisches Englisch, keine wilden Sprachmischungen wie 'getUserDaten').\n"
                "- Deine Review-Rückmeldung muss komplett auf Deutsch verfasst sein.\n\n"
                "Ausgabeformat:\n"
                "Teile deine Funde pro Abschnitt nach Priorität auf:\n"
                "- [KRITISCH]: Muss sofort behoben werden (Sicherheitslücke, schwerer Logikfehler).\n"
                "- [WARNUNG]: Schlechter Stil oder potenzielle Fehlerquelle (Architektur-Smell, fehlendes Error Handling).\n"
                "- [OPTIMIERUNG]: Clean-Code-Vorschlag für bessere Lesbarkeit.\n"
                "- [Guter Standard]: Der Code entspricht gutem Industriestandard.\n\n"
                "WICHTIG FÜR DEN SELF-HEALING-LOOP: Für jeden Fund unter [KRITISCH], [WARNUNG] oder [OPTIMIERUNG] MUSST du den genauen Dateinamen (z.B. 'src/app.py') und die betroffene Funktion angeben! Andernfalls weiß der Build-Agent nicht, wo er den Fix anwenden soll.\n"
                "Zeige für kritische Punkte und Architektur-Smells konkrete Refactoring-Beispiele (Code-Snippets vor und nach der Optimierung).\n\n"
                "WICHTIG:\n"
                "- Wenn alle Abschnitte dem '[Guter Standard]' entsprechen und keine kritischen Fehler, Warnungen oder Optimierungen vorliegen, antworte exakt und nur mit dem Wort 'PASS' (kein zusätzlicher Text).\n"
                "- Andernfalls gib das strukturierte Feedback komplett auf Deutsch aus.\n\n"
                "Hier ist der zu reviewende Code:\n\n"
            )
        else:
            prompt = (
                "You act as an experienced Senior Developer and Software Architect. Your task is to perform an in-depth, "
                "critical code review of the provided code modifications. Review the code against established industry standards "
                "and structure your feedback in English using the following sections:\n\n"
                "1. Security Analysis\n"
                "- Check for known security vulnerabilities (align with OWASP Top 10, e.g., injection, data leaks, broken authentication).\n"
                "- Identify hardcoded secrets (API keys, passwords) or insecure libraries.\n"
                "- SYSTEM-GUARDS CHECK: Report it as [CRITICAL] if 'xml.etree.ElementTree' is imported/used for actual XML parsing/loading instead of 'defusedxml'. Note: Type hints and isinstance checks using 'xml.etree.ElementTree.Element' are allowed and encouraged, since defusedxml itself does not expose an 'Element' class. Report hardcoded script files/strings as [WARNING].\n\n"
                "2. Architecture & Design (\"Anti-Spaghetti-Check\")\n"
                "- Analyze structure: Are SOLID principles and Separation of Concerns followed?\n"
                "- Check for code smells (methods/classes that are too long, deep nesting, redundant code / DRY principle).\n"
                "- Is the architecture modular, maintainable, and future-proof?\n"
                "- MODULARITY-CHECK: Report missing separation of concerns (e.g. Node generation, positioning, connection logic in a single monster method) as [WARNING] and request refactoring into specialized helpers.\n\n"
                "3. Logic, Performance & Robustness\n"
                "- Look for hidden logic errors, edge cases, infinite loops, or memory leaks.\n"
                "- Check error handling: Are exceptions caught cleanly, or can the program crash unexpectedly?\n"
                "- Are there obvious performance bottlenecks?\n"
                "- DEFENSIVE PROGRAMMING CHECK: Report missing attribute validation (e.g. direct access via 'attrib[\"x\"]' instead of '.get(\"x\")') as [CRITICAL] if invalid input could cause KeyErrors.\n\n"
                "4. Language Consistency & Conventions\n"
                "- The code itself (variables, functions, docstrings) must be clean and consistent (preferably American or British English, no mixed language like 'getUserDaten').\n"
                "- Your review feedback must be written entirely in English.\n\n"
                "Output Format:\n"
                "Categorize your findings per section by priority:\n"
                "- [CRITICAL]: Must be fixed immediately (security vulnerability, severe logic bug).\n"
                "- [WARNING]: Bad style or potential source of bugs (architectural smell, missing error handling).\n"
                "- [OPTIMIZATION]: Clean code suggestion for better readability.\n"
                "- [Good Standard]: Code meets good industry standards.\n\n"
                "IMPORTANT FOR THE SELF-HEALING LOOP: For any [CRITICAL], [WARNING], or [OPTIMIZATION] finding, you MUST specify the exact filename (e.g., 'src/app.py') and the affected function! Otherwise, the build agent will not know where to apply the fix.\n"
                "Provide concrete refactoring examples (before/after code snippets) for critical findings and architectural smells.\n\n"
                "IMPORTANT:\n"
                "- If all sections comply with '[Good Standard]' and there are no critical errors, warnings, or optimizations, reply exactly and only with the word 'PASS' (no extra text).\n"
                "- Otherwise, provide the structured feedback entirely in English.\n\n"
                "Here is the code to review:\n\n"
            )

        for mod in modifications:
            prompt += f"--- {mod.filepath} ---\n{mod.content}\n\n"
            
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)
        
        if response.success and response.code_generated:
            result = response.code_generated.strip()
            result_upper = result.upper()
            
            # Robust detection of actual findings
            has_critical = any(
                "[KRITISCH]" in line.upper() or "[CRITICAL]" in line.upper()
                for line in result.splitlines()
            )
            has_warning = any(
                "[WARNUNG]" in line.upper() or "[WARNING]" in line.upper()
                for line in result.splitlines()
            )
            has_optimization = any(
                "[OPTIMIERUNG]" in line.upper() or "[OPTIMIZATION]" in line.upper()
                for line in result.splitlines()
            )
            
            has_findings = has_critical or has_warning or has_optimization
            
            if only_critical:
                if not has_critical:
                    if has_warning or has_optimization:
                        self.last_findings = result
                    return True, "Code-Review bestanden (nur kritische Dinge betrachtet). Keine kritischen Fehler mehr vorhanden."
                else:
                    return False, f"Code-Review Beanstandungen (Kritisch):\n{result}"
            else:
                if result_upper == "PASS" or not has_findings:
                    return True, "Code-Review bestanden. Alles entspricht dem Guten Standard."
                else:
                    if has_optimization and not (has_critical or has_warning):
                        self.last_findings = result
                    return False, f"Code-Review Beanstandungen:\n{result}"
                
        return False, "Code-Review konnte nicht durchgeführt werden (LLM-Fehler)."

