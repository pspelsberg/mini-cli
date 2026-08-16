try:
    from rich.console import Console
    console = Console()
except ImportError:
    class MockConsole:
        def print(self, *args, **kwargs):
            pass
    console = MockConsole()

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
    """Risk classification and enforcement against destructive commands and sandbox escapes."""
    @staticmethod
    def is_safe(command: str) -> bool:
        import re
        import shlex
        if not command or not command.strip():
            return True

        cmd_clean = " ".join(command.strip().lower().split())

        # 1. Block destructive Unix file operations (rm with recursive/force or root targets)
        if re.search(r"\brm\b", cmd_clean):
            # Check for recursive flag (-r, -R, -fr, -rf, --recursive)
            has_recursive = bool(re.search(r"\brm\b.*(\s+-[a-z0-9]*r[a-z0-9]*|\s+--recursive)\b", cmd_clean))
            has_force = bool(re.search(r"\brm\b.*(\s+-[a-z0-9]*f[a-z0-9]*|\s+--force)\b", cmd_clean))
            # Blocking rm with recursive and force
            if has_recursive and has_force:
                return False
            # Block rm targeting root or system directories
            if re.search(r"\brm\s+.*(/\s*$|/\*|~|/\w+)", cmd_clean):
                return False

        # 2. Filesystem & disk destruction
        if re.search(r"\b(mkfs|dd|fdisk|parted|sfdisk|wipefs|shred|truncate\s+-s\s*0)\b", cmd_clean):
            return False

        # 3. Block device redirects
        if re.search(r"(>|>>)\s*/dev/(sd[a-z]|nvme[0-9]|vd[a-z]|loop[0-9]|mem|kmem)", cmd_clean):
            return False

        # 4. Dangerous docker destruction
        if re.search(r"\bdocker\b.*\b(system\s+prune|volume\s+prune|container\s+prune)\b", cmd_clean):
            return False

        # 5. Dangerous search & destroy commands (find -delete, find -exec rm)
        if re.search(r"\bfind\b.*(\s+-delete|\s+-exec\s+rm\b)", cmd_clean):
            return False

        # 6. Fork bombs
        if ":(){ :|:& };:" in cmd_clean or ":(){:|:&};:" in cmd_clean.replace(" ", ""):
            return False

        # 7. Shell payload decoding & execution tricks (base64 -d | sh, eval)
        if "base64 -d" in cmd_clean or "base64 --decode" in cmd_clean:
            if re.search(r"\|\s*(ba)?sh\b", cmd_clean):
                return False

        # 8. Dangerous Python/interpreter one-liners that delete root or run unvetted shell
        if re.search(r"\bpython[0-9.]*\s+-c\s+.*(shutil\.rmtree|os\.remove|os\.system|subprocess\.call|subprocess\.popen)", cmd_clean):
            return False

        # 9. Chroot / permissions destruction targeting root
        if re.search(r"\b(chmod|chown)\s+(-[a-z0-9]*r[a-z0-9]*\s+)?(777|000|\w+:\w+)\s+(/|/\*|/etc|/var|/usr)(\s|$)", cmd_clean):
            return False

        # 10. Direct keyword matches
        dangerous_keywords = ["rm -rf", "rm -fr", "rm -r -f", "mkfs", "> /dev/sda", "docker system prune"]
        for kw in dangerous_keywords:
            if kw in cmd_clean:
                return False

        return True

