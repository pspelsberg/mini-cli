import asyncio
import os
import json
import re
from rich.console import Console
from core.models import AgentTask, BuildResponse, FileModification
from core.i18n import t, get_language
from core.base_agent import BaseAgent
from providers import ProviderFactory

console = Console()

# ── Delimiter constants – chosen to never appear in source code ──────────────
_FILE_START = "<<<FILE_START:"
_FILE_END   = "<<<FILE_END>>>"
_MSG_START  = "<<<MSG:"
_MSG_END    = ">>>"


def _parse_block_format(raw: str) -> tuple[str, list[FileModification]] | None:
    """
    Parse the structured block format:

        <<<MSG:brief description>>>
        <<<FILE_START:path/to/file.py>>>
        ... file content ...
        <<<FILE_END>>>

    Returns (message, [FileModification]) or None if the format is not present.
    """
    if _FILE_START not in raw:
        return None

    # Extract optional message
    msg = ""
    msg_match = re.search(
        re.escape(_MSG_START) + r"(.*?)" + re.escape(_MSG_END),
        raw, re.DOTALL
    )
    if msg_match:
        msg = msg_match.group(1).strip()

    # Extract all file blocks
    pattern = (
        re.escape(_FILE_START) + r"(.+?)" + re.escape(_MSG_END) +   # path after <<<FILE_START:  ...>>>
        r"\n(.*?)" +                                                   # content
        re.escape(_FILE_END)
    )
    mods: list[FileModification] = []
    for match in re.finditer(pattern, raw, re.DOTALL):
        raw_path = match.group(1).strip()
        content  = match.group(2)

        # Security: block path traversal
        normalized = os.path.normpath(raw_path)
        if normalized.startswith("/") or ".." in normalized:
            console.print(t(
                f"[bold red]WARNING:[/bold red] LLM attempted path traversal to {raw_path}. Blocked.",
                f"[bold red]WARNUNG:[/bold red] LLM versuchte Path Traversal nach {raw_path}. Blockiert."
            ))
            normalized = os.path.basename(raw_path)

        mods.append(FileModification(filepath=normalized, content=content))

    return (msg, mods) if mods else None


def _parse_json_format(raw: str) -> tuple[str, list[FileModification]] | None:
    """
    Fallback: parse the legacy JSON format. Attempts progressive error recovery:
      1. strict=False  (tolerate raw newlines / tabs inside strings)
      2. backslash repair  (double-escape sequences like \\w that are invalid in JSON)
      3. json-repair library (if installed)
    """
    # Strip markdown code fences
    json_str = raw.replace("```json", "").replace("```", "").strip()

    # Try to isolate the outermost JSON object
    json_match = re.search(r'\{.*\}', json_str, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)

    data: dict | None = None

    # Attempt 1: tolerant parse
    try:
        data = json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        pass

    # Attempt 2: repair backslash escapes
    if data is None:
        try:
            fixed = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', r'\\\\', json_str)
            data = json.loads(fixed, strict=False)
        except json.JSONDecodeError:
            pass

    # Attempt 3: json-repair library (optional dependency)
    if data is None:
        try:
            from json_repair import loads as repair_loads  # type: ignore
            data = repair_loads(json_str)
        except Exception:
            pass

    if data is None or not isinstance(data, dict):
        return None

    mods: list[FileModification] = []
    modifications = data.get("modifications", [])
    if isinstance(modifications, list):
        for m in modifications:
            if not isinstance(m, dict):
                continue
            raw_path = m.get("filepath", "unknown.txt")
            normalized = os.path.normpath(raw_path)
            if normalized.startswith("/") or ".." in normalized:
                console.print(t(
                    f"[bold red]WARNING:[/bold red] LLM attempted path traversal to {raw_path}. Blocked.",
                    f"[bold red]WARNUNG:[/bold red] LLM versuchte Path Traversal nach {raw_path}. Blockiert."
                ))
                normalized = os.path.basename(raw_path)
            mods.append(FileModification(filepath=normalized, content=m.get("content", "")))

    return (data.get("message", ""), mods)


class BuildAgent(BaseAgent):
    def __init__(self, provider_name: str = "ollama"):
        self._name = "Build-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)

    @property
    def name(self) -> str:
        return self._name

    async def generate_code(self, task: AgentTask, context: str, research_data: str = "") -> BuildResponse:
        console.print(t(
            f"[bold yellow][{self.name}][/bold yellow] Generating code via {self.provider.__class__.__name__}...",
            f"[bold yellow][{self.name}][/bold yellow] Generiere Code via {self.provider.__class__.__name__}..."
        ))

        if get_language() == "de":
            prompt = (
                f"Du bist ein Senior Developer und Software-Architekt. Erfülle die folgende Aufgabe: {task.description}\n\n"
                "Beachte beim Schreiben des Codes zwingend die folgenden Grundsätze und Vorgehensweisen:\n"
                "1. Sicherheitsanalyse (Security):\n"
                "   - Vermeide bekannte Sicherheitslücken (orientiere dich an den OWASP Top 10).\n"
                "   - Verwende niemals hardcodierte Secrets oder unsichere Bibliotheken.\n"
                "   - SYSTEM-GUARDS: Falls du XML verarbeitest, verwende 'defusedxml' zum Parsen/Laden. Du darfst und solltest 'xml.etree.ElementTree.Element' für Typ-Annotationen und isinstance-Prüfungen nutzen, da defusedxml selbst kein 'Element'-Attribut anbietet. Vermeide hartcodierten Script-Code (z.B. JavaScript-Strings in Python) und lagere solche Logiken sauber aus.\n"
                "2. Architektur & Design (\"Anti-Spaghetti-Check\"):\n"
                "   - Halte SOLID-Prinzipien und Separation of Concerns ein.\n"
                "   - Vermeide Code Smells (zu lange Methoden/Klassen, tiefe Schachtelungen, redundanter Code).\n"
                "   - MODULARE AUFTEILUNG: Vermeide Monster-Methoden und Riesen-Klassen. Zerlege komplexe Aufgaben in kleine, spezialisierte Hilfsklassen oder Funktionen (z.B. Trennung von Node-Erstellung, Positionierung und Verbindungslogik).\n"
                "3. Logik, Performance & Robustheit:\n"
                "   - Implementiere sauberes, defensives Error Handling.\n"
                "   - Vermeide Performance-Flaschenhälse (z.B. ineffizientes rekursives Iterieren in XML, nutze stattdessen spezifische XPaths).\n"
                "   - DEFENSIVE PROGRAMMIERUNG: Schreibe den Code so, dass er auch fehlerhafte, leere oder manipulierte Eingabedaten abfängt (z.B. Attributprüfungen mit '.get()' statt direktem Dictionary-Zugriff zur Vermeidung von KeyError). Geh nicht nur vom 'Happy Path' aus.\n"
                "4. Sprachliche Konsistenz & Konventionen:\n"
                "   - Code, Variablen und Docstrings auf Englisch.\n"
                "5. Abarbeitung von Plänen (Task & Implementation Plan):\n"
                "   - Lies aufmerksam die Dateien 'task.md' und 'implementationplan.md' (oder 'implementation_plan.md'), falls sie im Projektkontext unter 'PROJECT MASTER PLANS' vorhanden sind.\n"
                "   - Diese Dateien legen die Ziele und den genauen schrittweisen Ablauf nach heutigen Coding-Standards fest.\n"
                "   - Arbeite die Schritte des Implementierungsplans sequenziell ab.\n"
                "   - Markiere den aktuell bearbeiteten Schritt nach erfolgreicher Implementierung als erledigt, indem du das entsprechende Markdown-Dokument änderst (ersetze `- [ ]` durch `- [x]`). Dies ist kritisch für die Fortschrittsverfolgung im Auto-Modus.\n\n"
                f"Hier ist der Projektkontext:\n{context}\n"
                f"Hier sind Web-Recherche Daten:\n{research_data}\n\n"
                "WICHTIG: ANTWORTE IM FOLGENDEN BLOCK-FORMAT. Nutze KEIN JSON, da JSON mit "
                "Code-Inhalten (Docstrings, Regex) nicht zuverlässig funktioniert.\n\n"
                "Format (exakt so einhalten):\n"
                f"{_MSG_START}Kurze Erklärung was du getan hast{_MSG_END}\n"
                f"{_FILE_START}pfad/zur/datei.py{_MSG_END}\n"
                "...kompletter Dateiinhalt hier...\n"
                f"{_FILE_END}\n\n"
                "Mehrere Dateien sind möglich. Wiederhole den FILE_START/FILE_END-Block für jede Datei.\n"
                "Der Dateiinhalt wird DIREKT auf die Festplatte geschrieben – kein Markdown, keine Umrandung."
            )
        else:
            prompt = (
                f"You are a Senior Developer and Software Architect. Fulfill the following task: {task.description}\n\n"
                "When writing the code, you must adhere to the following principles and procedures:\n"
                "1. Security Analysis (Security):\n"
                "   - Avoid known security vulnerabilities (align with OWASP Top 10).\n"
                "   - Never use hardcoded secrets or insecure libraries.\n"
                "   - SYSTEM-GUARDS: If you process XML, use 'defusedxml' for parsing/loading. You can and should use 'xml.etree.ElementTree.Element' for type annotations and isinstance checks, as defusedxml itself does not expose an 'Element' class. Avoid hardcoded script code (e.g. JavaScript strings in Python) and separate such logic cleanly.\n"
                "2. Architecture & Design (\"Anti-Spaghetti Check\"):\n"
                "   - Adhere to SOLID principles and Separation of Concerns.\n"
                "   - Avoid code smells (too long methods/classes, deep nesting, redundant code / DRY principle).\n"
                "   - MODULAR DIVISION: Avoid monster methods and giant classes. Break down complex tasks into small, specialized helper classes or functions (e.g., separation of node creation, positioning, and connection logic).\n"
                "3. Logic, Performance & Robustness:\n"
                "   - Implement clean, defensive error handling.\n"
                "   - Avoid performance bottlenecks (e.g., inefficient recursive iteration in XML, use specific XPaths instead).\n"
                "   - DEFENSIVE PROGRAMMING: Write the code to catch invalid, empty, or manipulated input data (e.g. attribute checks with '.get()' instead of direct dictionary access to avoid KeyError). Do not assume only the 'Happy Path'.\n"
                "4. Language Consistency & Conventions:\n"
                "   - Code, variables, and docstrings must be in English.\n"
                "5. Execution of plans (Task & Implementation Plan):\n"
                "   - Read carefully the files 'task.md' and 'implementationplan.md' (or 'implementation_plan.md') if they exist in the project context under 'PROJECT MASTER PLANS'.\n"
                "   - These files lay out the goals and the exact step-by-step procedure according to today's coding standards.\n"
                "   - Process the steps of the implementation plan sequentially.\n"
                "   - Mark the currently processed step as completed after successful implementation by modifying the corresponding markdown document (replace `- [ ]` with `- [x]`). This is critical for progress tracking in auto mode.\n\n"
                f"Here is the project context:\n{context}\n"
                f"Here is the web research data:\n{research_data}\n\n"
                "IMPORTANT: ANSWER IN THE FOLLOWING BLOCK FORMAT. Do NOT use JSON, as JSON does not work reliably with code contents (docstrings, regex).\n\n"
                "Format (exact match required):\n"
                f"{_MSG_START}Brief explanation of what you did{_MSG_END}\n"
                f"{_FILE_START}path/to/file.py{_MSG_END}\n"
                "...complete file content here...\n"
                f"{_FILE_END}\n\n"
                "Multiple files are possible. Repeat the FILE_START/FILE_END block for each file.\n"
                "The file content is written DIRECTLY to disk - no markdown formatting, no code fences."
            )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.provider.generate, prompt)

        if not response.success:
            return BuildResponse(success=False, message=f"LLM Fehler: {response.message}")

        raw_content = response.code_generated or ""

        # ── Primary: structured block format ──────────────────────────────────
        result = _parse_block_format(raw_content)

        # ── Fallback: legacy JSON format ───────────────────────────────────────
        if result is None:
            console.print(t(
                "[dim]Block format not detected, falling back to JSON parsing...[/dim]",
                "[dim]Block-Format nicht erkannt, versuche JSON-Parsing als Fallback...[/dim]"
            ))
            result = _parse_json_format(raw_content)

        if result is None:
            console.print(t(
                f"[dim]Could not parse BuildAgent response. Snippet:[/dim]\n{raw_content[:500]}",
                f"[dim]BuildAgent-Antwort konnte nicht geparst werden. Ausschnitt:[/dim]\n{raw_content[:500]}"
            ))
            return BuildResponse(success=False, message="Ungültiges Format vom Modell erhalten.")

        message, mods = result
        return BuildResponse(success=True, message=message, modifications=mods, tokens_used=response.tokens_used)
