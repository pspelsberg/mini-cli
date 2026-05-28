import json
import subprocess
import os
import re
import atexit
from rich.console import Console

console = Console()

class LSPClient:
    """Real connection to local Language Server Protocol (pylsp) via JSON-RPC. (Singleton)"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LSPClient, cls).__new__(cls)
            cls._instance.process = None
            cls._instance.msg_id = 1
            cls._instance.workspace_uri = f"file://{os.path.abspath(os.getcwd())}"
            cls._instance._indexed = False
            atexit.register(cls._instance.close)
        return cls._instance

    def __init__(self):
        pass

    def __del__(self):
        self.close()

    def close(self):
        """Clean up the pylsp process resources."""
        if hasattr(self, 'process') and self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass  # nosec B110
            finally:
                if hasattr(self.process, 'stdin') and self.process.stdin:
                    try:
                        self.process.stdin.close()
                    except Exception:
                        pass  # nosec B110
                if hasattr(self.process, 'stdout') and self.process.stdout:
                    try:
                        self.process.stdout.close()
                    except Exception:
                        pass  # nosec B110
                if hasattr(self.process, 'stderr') and self.process.stderr:
                    try:
                        self.process.stderr.close()
                    except Exception:
                        pass  # nosec B110
                self.process = None

    def _start_server(self):
        if self.process is None:
            try:
                import shutil
                from tools.security import SecurityGuard
                pylsp_path = shutil.which("pylsp") or "pylsp"
                if not SecurityGuard.is_safe(pylsp_path):
                    raise PermissionError(f"Security Block: Command '{pylsp_path}' is classified as dangerous and execution is blocked!")
                self.process = subprocess.Popen(
                    [pylsp_path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.getcwd()
                )  # nosec B603
                self._send_request("initialize", {"processId": os.getpid(), "rootUri": self.workspace_uri, "capabilities": {}})
                self._wait_for_response()
            except Exception as e:
                console.print(f"[dim]Could not start pylsp: {e}[/dim]")

    def _send_request(self, method, params):
        msg = {"jsonrpc": "2.0", "id": self.msg_id, "method": method, "params": params}
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        if self.process:
            self.process.stdin.write(header + body)
            self.process.stdin.flush()
            self.msg_id += 1
            
    def _send_notification(self, method, params):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        if self.process:
            self.process.stdin.write(header + body)
            self.process.stdin.flush()

    def _wait_for_response(self):
        if not self.process:
            return {}
        content_length = 0
        while True:
            line = self.process.stdout.readline().decode("utf-8")
            if not line:
                return {}
            if line == "\r\n":
                break
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":")[1].strip())
        body = self.process.stdout.read(content_length).decode("utf-8")
        return json.loads(body)

    def get_definitions(self, query: str) -> str:
        self._start_server()
        if not self.process:
            return "LSP server (pylsp) is not available."

        words = set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_]*\b', query))
        if not words:
            return "No symbols found in query."

        results = []
        py_files = []
        for root, dirs, files in os.walk("."):
            if any(skip in root for skip in [".git", "venv", ".pytest_cache", "__pycache__", ".ruff_cache"]):
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root, f))

        if not self._indexed:
            for f in py_files:
                abs_path = os.path.abspath(f)
                uri = f"file://{abs_path}"
                with open(f, "r") as fp:
                    self._send_notification("textDocument/didOpen", {
                        "textDocument": {"uri": uri, "languageId": "python", "version": 1, "text": fp.read()}
                    })
            self._indexed = True

        found_symbols = []
        for f in py_files:
            abs_path = os.path.abspath(f)
            uri = f"file://{abs_path}"
            self._send_request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})
            res = self._wait_for_response()
            symbols = res.get("result", [])
            for sym in symbols:
                name = sym.get("name")
                if name in words:
                    found_symbols.append({
                        "name": name,
                        "file": f,
                        "uri": uri,
                        "range": sym.get("location", {}).get("range")
                    })

        for sym in found_symbols:
            rng = sym["range"]
            if not rng:
                continue
            
            self._send_request("textDocument/references", {
                "textDocument": {"uri": sym["uri"]},
                "position": {"line": rng["start"]["line"], "character": rng["start"]["character"]},
                "context": {"includeDeclaration": False}
              })
            ref_res = self._wait_for_response()
            refs = ref_res.get("result", [])
            
            if refs:
                ref_files = set([r.get("uri").split("/")[-1] for r in refs if r.get("uri")])
                results.append(f"Symbol '{sym['name']}' (defined in {sym['file']}) is referenced in: {', '.join(ref_files)}")

        if not results:
            return "No LSP references found for requested symbols."
            
        return "\n".join(results)
