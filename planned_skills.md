# Der ultimative Guide: 20 Essentielle Skills für Coding Agent CLIs

Erstellt für Peppi von Lotti.

## 1. TDD- & Test-First-Workflow - [x] IMPLEMENTIERT (TestAgent, TDD-Red-Phase in Orchestrator)

Dieser Skill transformiert den Agenten von einem reinen Code-Schreiber zu einem Qualitätsgaranten. Im Kern geht es darum, dass der Agent niemals produktiven Code erstellt, ohne vorher die Erwartungshaltung in Form eines automatisierten Tests (Unit Test) definiert zu haben.
- **Vorgehensweise:** Der Agent analysiert die Anforderung, identifiziert Grenzfälle und schreibt zunächst einen Test, der fehlschlägt (Red). Danach wird der Code implementiert (Green) und anschließend refaktorisiert.
- **Vorteile:** Dies minimiert Bugs von Anfang an und sorgt für eine extrem hohe Testabdeckung.
- **Technische Umsetzung:** Integration von Frameworks wie Pytest, Jest oder Vitest. Der Agent nutzt die CLI, um die Tests in Echtzeit auszuführen und das Feedback-Loop zu schließen. Dies ist besonders wertvoll in Linux-Umgebungen wie Bazzite, wo Container-basierte Testläufe Standard sind.

---

## 2. Code-Reviewer & Simplifier - [x] IMPLEMENTIERT (ReviewAgent)

Ein Agent mit diesem Skill fungiert als automatisierter Senior-Entwickler. Er scannt bestehende Dateien nicht nur auf Fehler, sondern auf Eleganz und Lesbarkeit.
- **Abstraktionsebene:** Er erkennt 'Code Smells' wie zu lange Funktionen, tiefe Verschachtelungen oder redundante Logik.
- **Refactoring:** Der Agent schlägt aktiv Vereinfachungen vor, etwa die Nutzung von funktionalen Patterns (Map/Reduce) anstelle von komplexen Schleifen.
- **Kognitive Last:** Ziel ist es, die Komplexität so gering wie möglich zu halten, damit menschliche Entwickler den Code schneller verstehen. Er nutzt Tools wie 'clippy' für Rust oder 'pylint' für Python, um Best Practices zu erzwingen.

---

## 3. Frontend-Design-Feinschliff - [x] IMPLEMENTIERT (FrontendAgent)

Dieser Skill überbrückt die Lücke zwischen Design und Code. Er geht über das bloße Erstellen von HTML/CSS hinaus und versteht visuelle Hierarchien.
- **Design-Systeme:** Der Agent nutzt bestehende Tailwind-Konfigurationen oder CSS-Variablen, um Konsistenz zu wahren.
- **Responsivität:** Er generiert Code, der auf Mobilgeräten, Tablets und Desktops gleichermaßen funktioniert, ohne dass der Nutzer explizit 'Mobile First' fordern muss.
- **Barrierefreiheit (A11y):** Der Agent achtet auf ARIA-Labels, Kontrastverhältnisse und Tastaturnavigation. Er simuliert Screenreader-Verhalten, um die Usability zu prüfen.

---

## 4. Architektur- & Pattern-Validierung - [x] IMPLEMENTIERT (ArchitectureAgent)

Sicherstellung, dass das Projekt strukturell gesund bleibt. Ein Coding Agent muss verstehen, ob er sich in einer Microservices-Umgebung, einem Monolithen oder einer Clean Architecture befindet.
- **Einhaltung von Regeln:** Er verhindert, dass Geschäftslogik in den UI-Layer sickert oder dass zirkuläre Abhängigkeiten entstehen.
- **Design Patterns:** Er schlägt die Verwendung von Singleton, Factory oder Observer Patterns vor, wenn die Problemstellung dies erfordert.
- **Skalierbarkeit:** Der Agent plant Datei- und Ordnerstrukturen so, dass sie auch bei wachsendem Funktionsumfang übersichtlich bleiben.

---

## 5. API-Generator & Typ-Sicherheit - [x] IMPLEMENTIERT (ApiAgent)

Moderne Entwicklung lebt von klaren Schnittstellen. Dieser Skill sorgt dafür, dass Datenflüsse zwischen Frontend und Backend robust sind.
- **Schema-First:** Der Agent generiert TypeScript-Interfaces oder Rust-Structs basierend auf API-Definitionen (z.B. OpenAPI/Swagger).
- **Validierung:** Er erstellt Validierungs-Logik (z.B. mit Zod oder Pydantic), um sicherzustellen, dass fehlerhafte Daten bereits an der Systemgrenze abgefangen werden.
- **Dokumentation:** Jede API wird automatisch so dokumentiert, dass andere Entwickler (oder Agenten) sie sofort nutzen können.

---

## 6. Deep Research & Codebase-Exploration - [x] IMPLEMENTIERT (ResearchAgent & LSP)

Der Agent liest nicht nur die aktuelle Datei, sondern 'fühlt' das gesamte Projekt. Er nutzt Indexierung (RAG - Retrieval Augmented Generation), um Zusammenhänge zu verstehen.
- **Kontext-Bewusstsein:** Wenn eine Funktion in Datei A geändert wird, weiß der Agent, dass Datei B davon abhängt und ebenfalls angepasst werden muss.
- **Semantische Suche:** Er findet Code-Passagen nicht nur über Keywords, sondern über deren Bedeutung.
- **Legacy-Verständnis:** Er kann veraltete Code-Teile identifizieren, die durch neue Implementierungen ersetzt werden können.

---

## 7. Automatisches Debugging & Log-Analyse - [x] IMPLEMENTIERT (Self-Healing Loop)

Einer der mächtigsten Skills. Der Agent reagiert auf Fehlermeldungen in der Konsole.
- **Fehler-Kette:** Er analysiert Stack-Traces, versteht die Fehlerursache in der Tiefe und springt zur betroffenen Zeile.
- **Root Cause Analysis:** Er korrigiert nicht nur das Symptom, sondern die Ursache. Er nutzt CLI-Tools wie 'strace' oder 'gdb' unter Linux (Bazzite), um Prozesse zu untersuchen.
- **Iterative Heilung:** Er wendet Fixes an, führt den Code erneut aus und verifiziert das Ergebnis autonom.

---

## 8. Performance-Profiling - [x] IMPLEMENTIERT (ProfilerAgent)

Entwicklung endet nicht bei der Funktionalität; sie muss effizient sein.
- **Engpässe:** Der Agent identifiziert langsame Datenbankabfragen, Speicherlecks oder CPU-intensive Schleifen.
- **Optimierung:** Er schlägt effizientere Datenstrukturen vor (z. B. Map statt Array für Lookups).
- **Benchmarks:** Er führt automatisierte Performance-Tests durch und vergleicht die Metriken vor und nach einer Code-Änderung.

---

## 9. Security-Auditing (Autonomes Pentesting) - [x] IMPLEMENTIERT (SecurityAgent, Bandit, pip-audit)

Sicherheit ist kein Add-on, sondern integraler Bestandteil.
- **Sicherheitslücken:** Der Agent erkennt bekannte Muster wie SQL-Injection, Cross-Site Scripting (XSS) oder unsichere Token-Speicherung.
- **Secret Scanning:** Er verhindert aktiv, dass API-Keys oder Passwörter in das Git-Repository eingecheckt werden.
- **Dependency-Check:** Er prüft externe Bibliotheken auf bekannte Schwachstellen (CVEs) und schlägt sicherere Versionen vor.

---

## 10. Git-Commit- & PR-Writer - [x] IMPLEMENTIERT (GitAgent)

Professionelle Kommunikation nach außen.
- **Semantic Commits:** Der Agent schreibt präzise Commit-Nachrichten (feat, fix, docs, style).
- **Pull Request Beschreibungen:** Er fasst komplexe Änderungen verständlich zusammen, erstellt Checklisten für Reviewer und verlinkt auf relevante Issues.
- **Change Logs:** Er kann automatisch Versionshistorien generieren, die für Menschen lesbar sind.

---

## 11. PRD-to-Issues Planner - [x] IMPLEMENTIERT (PlannerAgent)

Die Fähigkeit, vage Anforderungen in ausführbare Arbeitspakete zu zerlegen.
- **Anforderungsanalyse:** Er liest Produktbeschreibungen (PRDs) und identifiziert technische Teilschritte.
- **Issue-Management:** Er erstellt GitHub- oder GitLab-Issues mit klaren Akzeptanzkriterien.
- **Roadmap-Verständnis:** Er priorisiert Aufgaben so, dass Abhängigkeiten (z.B. DB-Setup vor API-Entwicklung) berücksichtigt werden.

---

## 12. App-Verifizierung (/verify) - [x] IMPLEMENTIERT (VerifyAgent)

Ein automatisierter Check, ob das System nach einer Änderung noch 'lebt'.
- **Build-Check:** Der Agent prüft, ob das Projekt fehlerfrei kompiliert.
- **Integrationstest:** Er startet die App und prüft die wichtigsten Endpunkte oder UI-Elemente.
- **Umgebungskonsistenz:** Er stellt sicher, dass alle notwendigen Umgebungsvariablen (.env) vorhanden sind und die App in der Zielumgebung (z.B. Linux Bazzite Container) lauffähig ist.

---

## 13. Browser-Use & E2E-Testing - [x] IMPLEMENTIERT (BrowserAgent)

Der Agent nutzt den Browser wie ein Mensch.
- **Automatisierung:** Er schreibt und führt Playwright- oder Cypress-Skripte aus.
- **Visuelle Validierung:** Er erkennt, wenn CSS-Änderungen das Layout zerschießen.
- **User Journeys:** Er testet komplette Abläufe (Login -> Warenkorb -> Checkout), um sicherzustellen, dass die Logik im Browser hält.

---

## 14. CI/CD Pipeline-Troubleshooter - [x] IMPLEMENTIERT (CicdAgent)

Behebung von Fehlern in der Automatisierungskette.
- **Pipeline-Logs:** Der Agent liest GitHub Actions oder GitLab CI Logs aus und versteht, warum ein Build fehlgeschlagen ist.
- **YAML-Expertise:** Er korrigiert Konfigurationsfehler in CI-Dateien.
- **Caching-Optimierung:** Er verbessert die Build-Geschwindigkeit durch intelligentes Layer-Caching.

---

## 15. Docker- & Container-Orchestrierung - [x] IMPLEMENTIERT (DockerAgent)

Moderne Entwicklung findet in Containern statt.
- **Dockerfile-Optimierung:** Der Agent erstellt effiziente Multi-Stage-Builds.
- **Compose-Management:** Er konfiguriert komplexe Setups mit Datenbanken, Caches und Proxies.
- **Linux-Expertise:** Er nutzt Bazzite-spezifische Container-Vorteile für die lokale Entwicklung und sorgt für Portabilität.

---

## 16. Datenbank-Migrations-Assistent - [x] IMPLEMENTIERT (DatabaseAgent)

Daten sind das wertvollste Gut eines Projekts.
- **Schema-Evolution:** Der Agent generiert Migrationen (SQL, Prisma, Alembic) ohne Datenverlust.
- **Rollback-Strategien:** Er plant, wie Änderungen im Notfall rückgängig gemacht werden können.
- **Performance-Indizes:** Er erkennt, welche Spalten indiziert werden müssen, um die Abfragegeschwindigkeit zu erhöhen.

---

## 17. Dependency- & Update-Manager - [x] IMPLEMENTIERT (DependencyAgent)

Vermeidung von 'Dependency Hell'.
- **Versionierung:** Der Agent hält Bibliotheken aktuell, ohne das Projekt zu brechen.
- **Konfliktlösung:** Er löst Inkompatibilitäten zwischen verschiedenen Paketen auf.
- **Audit:** Er führt regelmäßig Sicherheits-Audits der Abhängigkeiten durch.

---

## 18. Skill-Creator (Meta-Skill) - [x] IMPLEMENTIERT (SkillCreatorAgent)

Der Agent lernt, sich selbst zu verbessern.
- **Automatisierung von Workflows:** Wenn eine Aufgabe oft wiederholt wird, schreibt der Agent ein Skript dafür und fügt es seinem eigenen Werkzeugkasten hinzu.
- **Wissens-Repository:** Er dokumentiert Projektspezifika in einer 'AGENT.md', um bei zukünftigen Aufgaben schneller zu sein.
- **Tool-Integration:** Er kann neue CLI-Tools eigenständig erlernen und nutzen.

---

## 19. Multi-Step Orchestration (Sub-Agenten) - [x] IMPLEMENTIERT (OrchestratorAgent)

Komplexe Probleme werden in Teams gelöst.
- **Delegation:** Ein Haupt-Agent teilt Aufgaben an spezialisierte Sub-Instanzen auf (z.B. ein Experte für CSS, einer für DB).
- **Zusammenführung:** Er koordiniert die Ergebnisse der Sub-Agenten und stellt sicher, dass der Gesamtplan eingehalten wird.
- **Status-Tracking:** Er behält den Überblick über langlaufende Prozesse.

---

## 20. Auto-Dokumentations-Generator - [x] IMPLEMENTIERT (DocsAgent)

Code ist nur so gut wie seine Beschreibung.
- **Docstrings & Kommentare:** Der Agent schreibt klaren, beschreibenden Text direkt in den Code.
- **README-Management:** Er hält die Hauptdokumentation des Projekts aktuell.
- **Diagramme:** Er generiert Mermaid.js oder PlantUML Diagramme, um Systemarchitekturen visuell darzustellen.

---
