import asyncio
import os
import re
from rich.console import Console
from core.models import AgentTask
from core.base_agent import BaseAgent
from core.i18n import t
from providers import ProviderFactory
from tools.lsp_client import LSPClient
from tools.mcp_client import MCPClient

console = Console()

class RAGAgent(BaseAgent):
    def __init__(self, provider_name: str = "ollama"):
        self._name = "RAG-Agent"
        self.provider = ProviderFactory.get_provider(provider_name)
        self.lsp_client = LSPClient()
        self.mcp_client = MCPClient()

    @property
    def name(self) -> str:
        return self._name

    async def retrieve_context(self, task: AgentTask) -> str:
        console.print(t(f"[bold yellow][{self.name}][/bold yellow] Analyzing local codebase and external interfaces...",
                        f"[bold yellow][{self.name}][/bold yellow] Analysiere lokale Code-Basis und externe Schnittstellen..."))
        await asyncio.sleep(1) 

        # 0. Get list of all files in workspace
        def get_all_workspace_files():
            all_files = []
            abs_workspace = os.path.abspath(os.getcwd())
            for root, _, files in os.walk("."):
                if any(skip in root for skip in [".git", "venv", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".lancedb"]):
                    continue
                for file in files:
                    filepath = os.path.join(root, file)
                    rel_path = os.path.relpath(filepath, ".")
                    if rel_path.startswith("..") or file.endswith((".pyc", ".png", ".jpg", ".webp", ".zip", ".tar.gz")):
                        continue
                    try:
                        abs_file = os.path.abspath(filepath)
                        if not abs_file.startswith(abs_workspace):
                            continue
                        if os.path.islink(filepath):
                            resolved_link = os.path.realpath(filepath)
                            if not resolved_link.startswith(abs_workspace):
                                continue
                        all_files.append(rel_path)
                    except Exception:
                        pass
            return all_files

        all_workspace_files = await asyncio.to_thread(get_all_workspace_files)

        # Build workspace file structure snippet
        file_structure_str = "--- Workspace File Structure ---\n" + "\n".join(f"- {f}" for f in sorted(all_workspace_files)) + "\n\n"

        # 1. Fetch LSP and MCP context
        lsp_context = await asyncio.to_thread(self.lsp_client.get_definitions, task.description)
        mcp_context = await self.mcp_client.fetch_ticket_context()

        lsp_snippet = f"--- LSP Context ---\n{lsp_context}\n\n"
        mcp_snippet = f"--- MCP Context ---\n{mcp_context}\n\n"

        # 2. Fetch Project Master Plans
        def read_project_plans():
            plans = {}
            for f in sorted(all_workspace_files):
                fname = os.path.basename(f).lower()
                if fname in ["implementationplan.md", "task.md", "implementation_plan.md", "planned_skills.md"]:
                    try:
                        with open(f, "r", encoding="utf-8") as doc_file:
                            plans[f] = doc_file.read()
                    except Exception as e:
                        console.print(t(f"[dim]Error reading plan {f}: {e}[/dim]", f"[dim]Fehler beim Lesen des Plans {f}: {e}[/dim]"))
            return plans

        project_plans = await asyncio.to_thread(read_project_plans)
        plans_snippet = ""
        if project_plans:
            plans_content = ""
            for path, content in project_plans.items():
                plans_content += f"--- {path} (MASTER PLAN) ---\n{content}\n\n"
            plans_snippet = f"--- PROJECT MASTER PLANS (STRICTLY FOLLOW THESE GUIDELINES) ---\n{plans_content}\n"

        # 2.5 Fetch relevant memory from past healing cases
        memory_snippet = ""
        try:
            from core.memory import MemoryManager
            mem_mgr = MemoryManager()
            past_memories = await mem_mgr.find_relevant_memories(task.description, limit=2)
            if past_memories:
                memory_content = ""
                for idx, mem in enumerate(past_memories):
                    memory_content += f"Case {idx+1}:\n"
                    memory_content += f"- Task: {mem['task_description']}\n"
                    memory_content += f"- Past Error:\n{mem['error_log']}\n"
                    memory_content += "- Solution Code:\n"
                    for sm in mem['solution']:
                        memory_content += f"  File: {sm['filepath']}\n{sm['content']}\n"
                    memory_content += "\n"
                memory_snippet = f"--- HISTORICAL MEMORY: PAST ERRORS & SOLUTIONS ---\n{memory_content}\n"
        except Exception as e:
            import logging
            logging.debug(f"Failed to fetch past memory context in RAGAgent: {e}")

        # Calculate budget
        max_chars = getattr(self.provider, "max_context_chars", 100000)
        context_budget = max(4000, max_chars - 3000)
        used_budget = len(file_structure_str) + len(lsp_snippet) + len(mcp_snippet) + len(plans_snippet) + len(memory_snippet)
        remaining_budget = context_budget - used_budget

        # 3. Retrieve relevant files based on search keywords
        local_snippets = []
        if remaining_budget > 0:
            stopwords = {
                "the", "a", "an", "and", "or", "but", "if", "then", "else", "to", "for", 
                "in", "on", "at", "by", "with", "from", "up", "down", "of", "out", 
                "is", "was", "are", "were", "be", "been", "being", "have", "has", "had", 
                "do", "does", "did", "please", "task", "run", "make", "create", 
                "implement", "add", "fix", "change", "update", "test", "build",
                "file", "code", "program", "agent", "mini", "cli", "project", "workspace"
            }
            words = re.findall(r'\b[a-zA-Z_]{3,}\b', task.description.lower())
            keywords = {w for w in words if w not in stopwords}

            candidate_files = [
                f for f in all_workspace_files 
                if os.path.basename(f).lower() not in ["implementationplan.md", "task.md", "implementation_plan.md", "planned_skills.md"]
                and f.endswith((".py", ".md", ".json"))
            ]

            # Stage 1: Path/Name matching score (no I/O)
            scored_candidates = []
            for filepath in candidate_files:
                path_score = 0.0
                filepath_lower = filepath.lower()
                if "core/" in filepath_lower or filepath_lower == "mini_cli.py" or filepath_lower == "providers.py":
                    path_score += 5.0
                for kw in keywords:
                    if kw in filepath_lower:
                        path_score += 50.0
                scored_candidates.append((filepath, path_score))

            scored_candidates.sort(key=lambda x: x[1], reverse=True)

            # Stage 2: Content matching score (limited I/O for top candidates)
            final_scores = []
            top_candidates = scored_candidates[:12]
            other_candidates = scored_candidates[12:]

            for filepath, path_score in top_candidates:
                content_score = 0.0
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                        content_lower = content.lower()
                        for kw in keywords:
                            count = content_lower.count(kw)
                            content_score += min(count * 2.0, 30.0)
                except Exception:
                    pass
                final_scores.append((filepath, path_score + content_score))

            for filepath, path_score in other_candidates:
                final_scores.append((filepath, path_score))

            final_scores.sort(key=lambda x: x[1], reverse=True)

            # Add selected file contents to snippets
            for filepath, score in final_scores:
                if remaining_budget <= 200:
                    break
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if not content.strip():
                        continue
                    
                    if len(content) <= remaining_budget:
                        local_snippets.append(f"--- File: {filepath} ---\n{content}\n")
                        remaining_budget -= (len(filepath) + len(content) + 50)
                    else:
                        truncated_content = content[:remaining_budget]
                        local_snippets.append(
                            f"--- File: {filepath} (TRUNCATED to fit context window) ---\n"
                            f"{truncated_content}\n"
                            f"[... Content truncated due to model context length constraints ...]\n"
                        )
                        remaining_budget = 0
                except Exception as e:
                    console.print(t(f"[dim]Error reading {filepath}: {e}[/dim]", 
                                    f"[dim]Fehler beim Lesen von {filepath}: {e}[/dim]"))

        # Combine snippets
        snippets = []
        snippets.append(file_structure_str)
        snippets.append(lsp_snippet)
        snippets.append(mcp_snippet)
        if plans_snippet:
            snippets.append(plans_snippet)
        if memory_snippet:
            snippets.append(memory_snippet)
        snippets.extend(local_snippets)

        final_context = "\n".join(snippets)
        if len(final_context) > context_budget:
            final_context = final_context[:context_budget] + "\n[... Context truncated for safety ...]\n"

        return final_context

