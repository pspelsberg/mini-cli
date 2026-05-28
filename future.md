# Future Roadmap & Next-Gen Features (Phase 8+)

Dieses Dokument skizziert die fortgeschrittenen architektonischen Erweiterungen für den Mini-CLI Coding Agenten, nachdem die Basis-Meilensteine (Phasen 1-7) erfolgreich abgeschlossen wurden.

## 1. Web Search & Deep Research (Wissen über das Jetzt) - [x] IMPLEMENTIERT
Aktuell ist das Wissen des Agenten auf den Cut-off des jeweiligen LLM-Modells (z. B. GPT-4o oder Claude) beschränkt.
* **Geplantes Feature:** Implementierung eines `WebSearchAgent` (z.B. angebunden an die DuckDuckGo oder Perplexity API).
* **Aktueller Stand:** Der `ResearchAgent` ist integriert! Er nutzt `duckduckgo-search` für aktuelle Webabfragen. Zum Schutz vor Prompt-Injections wird das "Defense in Depth" Muster angewandt:
  - **Sanitizer-Pipeline**: Gefährliche Keywords (`ignore previous instructions`) werden per Heuristik blockiert.
  - **XML-Delimiters**: Web-Daten werden streng in `<untrusted_web_data>` gekapselt.
  - **Privilege Separation**: Der ResearchAgent hat keinerlei Ausführungsrechte, er sammelt nur Kontext.

## 2. Echte Code-Ausführung (Test-Driven Self-Healing) - [x] IMPLEMENTIERT
Ruff als Linter findet Syntaxfehler, aber keine Logikfehler.
* **Geplantes Feature:** Ein `TestAgent`, der nicht nur lintet, sondern den Code bzw. vorhandene Test-Suites (wie `pytest`) **physisch in einer Sandbox ausführt**.
* **Aktueller Stand:** Ein `TestAgent` ist in den Orchestrator (Self-Healing Loop) integriert. Er führt `pytest` in einem Sandbox-Kontext (isoliert mit Timeout) aus. Schlägt ein Test fehl, liest der Agent den Traceback, erkennt den logischen Fehler und startet autonom eine Reparaturschleife, bis alle Tests "grün" sind (Closed-Loop Testing).

## 3. Interaktives Diffing (Human-in-the-Loop für Code) - [x] IMPLEMENTIERT
Aktuell überschreibt der Agent im `--mode build` die Dateien sofort physisch auf der Festplatte. 
* **Geplantes Feature:** Ein interaktives TUI-Overlay (in `Rich` / `Textual`), das ein klassisches Side-by-Side Diff (Rot/Grün) anzeigt, **bevor** die Datei verändert wird.
* **Aktueller Stand:** Der Orchestrator wurde mit einer zentralen Diff-Engine (`difflib` + `rich`) ausgestattet.
  - Im `--mode build` wird nun bei jeder Code-Generierung und bei jedem Repair-Versuch ein klares Diff (alte vs. neue Zeilen) angezeigt und via Prompt (`[y/n]`) bestätigt.
  - Mit `--mode auto` gibt es einen "Yolo-Mode", der diese Abfragen bewusst überspringt, aber das Diff-Logging für Pipelines beibehält.

## 4. Dateiübergreifendes Refactoring (Vollwertiger LSP-Ausbau) - [x] IMPLEMENTIERT
Unser `LSPClient` greift nun dynamisch auf das lokale Code-Wissen zu.
* **Geplantes Feature:** Echte Anbindung an lokale Language Server Protokolle (wie `pyright` oder `pylsp`) via JSON-RPC.
* **Aktueller Stand:** Der `LSPClient` startet nun einen vollwertigen `pylsp` Server im Hintergrund und kommuniziert via JSON-RPC. Wenn der Agent einen Task erhält, extrahiert er automatisch alle Keywords und Symbole (z.B. Klassennamen). Über `textDocument/documentSymbol` und `textDocument/references` fragt er den LSP-Server ab, in welchen Dateien das Symbol definiert und referenziert wird. Die gesamte Import-Kette landet als Kontext im RAG-Speicher des Agenten, sodass er beim Refactoring oder Umbenennen autonom alle beteiligten Dateien mit anpasst.

## 5. Architektur- & Pattern-Validierung (Code-Gesundheit) - [x] IMPLEMENTIERT
Code kann syntaxtechnisch fehlerfrei, architektonisch aber eine Katastrophe sein (Stichwort: "Spaghetti-Code").
* **Geplantes Feature:** Ein dedizierter `ArchitectureAgent`, der Code vor dem Speichern auf Clean-Architecture-Prinzipien prüft (basierend auf den Vorgaben in `planned_skills`).
* **Aktueller Stand:** Der `ArchitectureAgent` wurde integriert. Er validiert jeden vorgeschlagenen Code auf Clean-Architecture-Prinzipien (SRP, keine Spaghetti-Abhängigkeiten) und blockiert ihn bei Verstößen mit konkreten Verbesserungsvorschlägen. Um direkt mit gutem Beispiel voranzugehen, wurde das Projekt selbst vollständig refactored: Der ehemals über 400 Zeilen lange `agents.py` Monolith wurde in eine saubere Struktur (`core/`, `agents/`, `tools/`) mit Interfaces (`BaseAgent`) und entkoppelter Logik überführt.
