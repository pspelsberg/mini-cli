import re
import html
import asyncio
from core.base_agent import BaseAgent
try:
    from rich.console import Console
    console = Console()
except ImportError:
    class MockConsole:
        def print(self, *args, **kwargs):
            pass
    console = MockConsole()

class ResearchAgent(BaseAgent):
    """Secure agent for web searches with robust prompt injection protection & content sandboxing."""
    def __init__(self):
        self._name = "Research-Agent"
        
    @property
    def name(self) -> str:
        return self._name

    def _sanitize_web_content(self, text: str) -> str:
        if not text:
            return ""

        # Comprehensive prompt injection detection patterns
        injection_patterns = [
            r"\b(ignore\s+(all\s+)?(previous|prior|above)\s+instructions)\b",
            r"\b(system\s+override|disregard\s+instructions|system\s+prompt)\b",
            r"\b(forget\s+all\s+(previous\s+)?rules)\b",
            r"\b(you\s+are\s+now\s+in\s+dan\s+mode)\b",
            r"\b(new\s+system\s+instruction)\b",
            r"<<<FILE_START:",
            r"<<<MSG:",
            r"\[ASK_USER:",
        ]

        sanitized = text
        for pattern in injection_patterns:
            if re.search(pattern, sanitized, re.IGNORECASE):
                console.print(f"[bold red][{self.name}][/bold red] Prompt injection detected in web data! Blocking matched segment.")
                sanitized = re.sub(pattern, "[INJECTION_ATTEMPT_FILTERED]", sanitized, flags=re.IGNORECASE)

        # Escape XML and control characters to prevent prompt enclave escaping
        sanitized = html.escape(sanitized, quote=False)
        sanitized = sanitized.replace("```", "'''")

        return sanitized

    async def search_and_summarize(self, query: str) -> str:
        console.print(f"   -> [bold cyan][{self.name}][/bold cyan] Starting secure web search...")
        await asyncio.sleep(0.5)
        
        try:
            def _search():
                from duckduckgo_search import DDGS
                return DDGS().text(query, max_results=3)
                
            results = await asyncio.to_thread(_search)
            raw_web_content = "\n\n".join([f"Quelle: {r.get('href', '')}\nInhalt: {r.get('body', '')}" for r in results])
        except ImportError:
            raw_web_content = "pip install duckduckgo-search is missing."
        except Exception as e:
            console.print(f"[dim]Web search failed: {e}[/dim]")
            raw_web_content = "No web results found."

        safe_content = self._sanitize_web_content(raw_web_content)
        xml_wrapped = f"\n<untrusted_web_data>\n{safe_content}\n</untrusted_web_data>\n"
        return xml_wrapped
