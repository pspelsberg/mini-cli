import asyncio
from rich.console import Console
from core.base_agent import BaseAgent

console = Console()

class ResearchAgent(BaseAgent):
    """Secure agent for web searches with prompt injection protection."""
    def __init__(self):
        self._name = "Research-Agent"
        
    @property
    def name(self) -> str:
        return self._name

    def _sanitize_web_content(self, text: str) -> str:
        dangerous = ["ignore previous instructions", "system override", "forget all", "os.system"]
        lower_text = text.lower()
        for d in dangerous:
            if d in lower_text:
                console.print(f"[bold red][{self.name}][/bold red] Prompt injection detected! Web content blocked.")
                return "[INJECTION ATTEMPT DETECTED - CONTENT BLOCKED]"
        return text

    async def search_and_summarize(self, query: str) -> str:
        console.print(f"   -> [bold cyan][{self.name}][/bold cyan] Starting secure web search...")
        await asyncio.sleep(0.5)
        
        try:
            def _search():
                from duckduckgo_search import DDGS
                return DDGS().text(query, max_results=3)
                
            results = await asyncio.to_thread(_search)
            raw_web_content = "\n\n".join([f"Quelle: {r['href']}\nInhalt: {r['body']}" for r in results])
        except ImportError:
            raw_web_content = "pip install duckduckgo-search is missing."
        except Exception as e:
            console.print(f"[dim]Web search failed: {e}[/dim]")
            raw_web_content = "No web results found."

        safe_content = self._sanitize_web_content(raw_web_content)
        xml_wrapped = f"\n<untrusted_web_data>\n{safe_content}\n</untrusted_web_data>\n"
        return xml_wrapped
