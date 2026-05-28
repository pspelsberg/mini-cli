import time
import asyncio
from rich.console import Console

console = Console()

class RateLimitGuard:
    def __init__(self, tpm_limit: int = 100000):
        self.tpm_limit = tpm_limit
        self.current_tokens_per_min = 0
        self.last_reset = time.time()

    async def check_and_add(self, tokens: int):
        while True:
            now = time.time()
            if now - self.last_reset > 60:
                self.current_tokens_per_min = 0
                self.last_reset = now
                
            if self.current_tokens_per_min + tokens <= self.tpm_limit:
                self.current_tokens_per_min += tokens
                break
                
            sleep_time = max(0.1, 60 - (now - self.last_reset))
            console.print(f"[bold red]Rate-Limit Warning![/bold red] Waiting {sleep_time:.1f}s for token reset...")
            await asyncio.sleep(sleep_time)

class SecurityGuard:
    """Risk classification for potentially destructive commands."""
    @staticmethod
    def is_safe(command: str) -> bool:
        import re
        cmd_clean = " ".join(command.lower().split())
        
        # 1. rm with both recursive (-r, -R, --recursive) and force (-f, --force) flags
        if re.search(r"\brm\b", cmd_clean):
            has_recursive = bool(re.search(r"\brm\b.*\s+(-[a-z]*r[a-z]*|--recursive)\b", cmd_clean))
            has_force = bool(re.search(r"\brm\b.*\s+(-[a-z]*f[a-z]*|--force)\b", cmd_clean))
            if has_recursive and has_force:
                return False
                
        # 2. mkfs commands
        if re.search(r"\bmkfs\b", cmd_clean):
            return False
            
        # 3. dd commands
        if re.search(r"\bdd\b", cmd_clean):
            return False
            
        # 4. Redirects to block devices
        if re.search(r"(>|>>)\s*/dev/(sd[a-z]|nvme[0-9]|vd[a-z]|loop[0-9])", cmd_clean):
            return False
            
        # 5. Docker prune commands
        if re.search(r"\bdocker\b.*\bprune\b", cmd_clean):
            return False
            
        # Legacy/fallback keyword blacklist
        dangerous_keywords = ["rm -rf", "mkfs", "> /dev/sda", "docker system prune"]
        for kw in dangerous_keywords:
            if kw in cmd_clean:
                return False
                
        return True

