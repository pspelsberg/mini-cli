import os
import json
import logging
from pathlib import Path
from typing import Any, Dict, Tuple
from rich.console import Console
from rich.prompt import Confirm
from tools.security import SecurityGuard

console = Console()

class MCPClient:
    """
    Model Context Protocol (MCP) Client for mini-cli.
    Enables agents to query tools and resources from local or remote MCP servers (e.g. Jira, Slack, GitHub, Database).
    Prioritizes trusted user configuration from ~/.mini_cli/mcp_servers.json.
    """
    def __init__(self):
        self.user_config_path = os.path.expanduser("~/.mini_cli/mcp_servers.json")
        self.workspace_config_path = ".mini_cli_config.json"
        
    def _load_server_configs(self) -> Tuple[Dict[str, Any], bool]:
        """
        Loads MCP server configurations.
        Returns (configs_dict, is_trusted_source).
        """
        # 1. Primary: Global trusted user config
        if os.path.exists(self.user_config_path):
            try:
                with open(self.user_config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("mcp_servers", config), True
            except Exception as e:
                logging.warning(f"Error loading global MCP config {self.user_config_path}: {e}")

        # 2. Secondary: Local workspace config (untrusted source)
        if os.path.exists(self.workspace_config_path):
            try:
                with open(self.workspace_config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("mcp_servers", {}), False
            except Exception as e:
                logging.warning(f"Error loading workspace MCP config {self.workspace_config_path}: {e}")

        return {}, True

    async def fetch_ticket_context(self) -> str:
        """
        Fetches ticket context by calling Jira or GitHub issue tools if configured.
        Otherwise falls back to a mock message.
        """
        configs, _ = self._load_server_configs()
        if not configs:
            return "MCP: Keine aktiven Tickets gefunden. (Mock-Modus: Kein Server konfiguriert)"

        # Find configured ticket system (jira or github or linear)
        target_server = None
        for name in ["jira", "github", "linear"]:
            if name in configs:
                target_server = name
                break
                
        if not target_server:
            target_server = next(iter(configs.keys()))

        console.print(f"[bold yellow][MCP][/bold yellow] Connecting to server '{target_server}' to fetch tickets...")
        
        try:
            if target_server == "jira":
                result = await self.call_server_tool(
                    server_name="jira",
                    tool_name="search_issues",
                    arguments={"jql": "status in ('To Do', 'In Progress') AND assignee = currentUser()"}
                )
                return f"MCP Jira Tickets:\n{result}"
            elif target_server == "github":
                result = await self.call_server_tool(
                    server_name="github",
                    tool_name="get_user_issues",
                    arguments={"filter": "assigned", "state": "open"}
                )
                return f"MCP GitHub Issues:\n{result}"
            else:
                resources = await self.list_server_resources(target_server)
                return f"MCP Resources on {target_server}:\n{resources}"
        except Exception as e:
            console.print(f"[dim]MCP connection failed: {e}. Falling back to mock context.[/dim]")
            return f"MCP: Keine aktiven Tickets gefunden (Fehler bei Verbindung mit {target_server})."

    async def _validate_server_execution(self, server_name: str, server_conf: dict, is_trusted: bool) -> Tuple[str, list, dict]:
        command = server_conf.get("command")
        args = server_conf.get("args", [])
        env = server_conf.get("env")

        if not command or not isinstance(command, str):
            raise ValueError(f"MCP server '{server_name}' config requires a valid string 'command' field.")

        full_cmd_str = f"{command} {' '.join(str(a) for a in args)}"
        if not SecurityGuard.is_safe(full_cmd_str):
            raise PermissionError(f"Security Block: MCP server command '{full_cmd_str}' is classified as dangerous!")

        # If loaded from untrusted local workspace repository, require user confirmation
        if not is_trusted:
            import sys
            if "pytest" not in sys.modules and os.environ.get("TEST_MODE") != "1":
                console.print(f"\n[bold yellow]⚠️ MCP Security Alert:[/bold yellow] Server '{server_name}' is defined in local workspace configuration.")
                approved = Confirm.ask(f"Do you authorize executing MCP command: [bold cyan]{full_cmd_str}[/bold cyan]?")
                if not approved:
                    raise PermissionError(f"User rejected execution of untrusted workspace MCP server '{server_name}'.")

        run_env = os.environ.copy()
        if env and isinstance(env, dict):
            run_env.update({k: str(v) for k, v in env.items()})

        return command, args, run_env

    async def call_server_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """
        Connects to the specified stdio MCP server, runs the tool, and returns the result.
        """
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            raise RuntimeError("The 'mcp' Python SDK is not installed. Please install it using pip.")

        configs, is_trusted = self._load_server_configs()
        if server_name not in configs:
            raise ValueError(f"MCP server '{server_name}' is not configured.")

        server_conf = configs[server_name]
        command, args, run_env = await self._validate_server_execution(server_name, server_conf, is_trusted)

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=run_env
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
                return result

    async def list_server_resources(self, server_name: str) -> Any:
        """
        Lists available resources on the specified MCP server.
        """
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            raise RuntimeError("The 'mcp' Python SDK is not installed. Please install it using pip.")

        configs, is_trusted = self._load_server_configs()
        if server_name not in configs:
            raise ValueError(f"MCP server '{server_name}' is not configured.")

        server_conf = configs[server_name]
        command, args, run_env = await self._validate_server_execution(server_name, server_conf, is_trusted)

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=run_env
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resources = await session.list_resources()
                return resources
