import subprocess
import asyncio
from typing import List, Optional
from dataclasses import dataclass
from tools.security import SecurityGuard

@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

class CommandTimeoutError(Exception):
    """Error when a command exceeds the timeout limit."""
    pass

def _limit_resources():
    """Drops resource limits in the subprocess to enforce a lightweight sandbox on UNIX."""
    try:
        import resource
        # Limit CPU time to 30 seconds
        resource.setrlimit(resource.RLIMIT_CPU, (30, 35))
        # Limit virtual memory (address space) to 3 GB
        resource.setrlimit(resource.RLIMIT_AS, (3 * 1024 * 1024 * 1024, 4 * 1024 * 1024 * 1024))
        # Limit generated file size to 100 MB
        resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 110 * 1024 * 1024))
    except (ImportError, ValueError, OSError):
        pass

class CommandRunner:
    """
    Central Command-Runner for all CLI calls (except interactive ones like LSP).
    Replaces direct subprocess.run() calls for centralized timeout and security handling.
    """
    @staticmethod
    def run(command: List[str], timeout: int = 15, cwd: Optional[str] = None) -> CommandResult:
        cmd_str = " ".join(command)
        if not SecurityGuard.is_safe(cmd_str):
            raise PermissionError(f"Security Block: Command '{cmd_str}' is classified as dangerous and execution is blocked!")
            
        try:
            import sys
            kwargs = {}
            if sys.platform != "win32":
                kwargs["preexec_fn"] = _limit_resources

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                check=False,
                **kwargs
            ) # nosec B603 B607
            return CommandResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr
            )
        except subprocess.TimeoutExpired:
            raise CommandTimeoutError(f"Command timed out after {timeout} seconds.")

    @staticmethod
    async def run_async(command: List[str], timeout: int = 15, cwd: Optional[str] = None) -> CommandResult:
        cmd_str = " ".join(command)
        if not SecurityGuard.is_safe(cmd_str):
            raise PermissionError(f"Security Block: Command '{cmd_str}' is classified as dangerous and execution is blocked!")
            
        try:
            import sys
            kwargs = {}
            if sys.platform != "win32":
                kwargs["preexec_fn"] = _limit_resources

            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                **kwargs
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                return CommandResult(
                    returncode=proc.returncode if proc.returncode is not None else 0,
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace")
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass  # nosec B110
                await proc.wait()
                raise CommandTimeoutError(f"Command timed out after {timeout} seconds.")
        except Exception as e:
            if isinstance(e, CommandTimeoutError):
                raise
            raise

