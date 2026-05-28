import os
import json
from typing import Any, Dict
from rich.console import Console

console = Console()

class MCPClient:
    """
    Model Context Protocol (MCP) Client for mini-cli.
    Enables agents to query tools and resources from local or remote MCP servers (e.g. Jira, Slack, GitHub, Database).
    Reads server definitions from .mini_cli_config.json under the "mcp_servers" key.
    """
    def __init__(self):
        self.config_path = ".mini_cli_config.json"
        
    def _load_server_configs(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("mcp_servers", {})
            except Exception:
                pass
        return {}

    async def fetch_ticket_context(self) -> str:
        """
        Fetches ticket context by calling the Jira or GitHub issue tools if configured.
        Otherwise falls back to a mock message.
        """
        configs = self._load_server_configs()
        if not configs:
            return "MCP: Keine aktiven Tickets gefunden. (Mock-Modus: Kein Server konfiguriert)"

        # Find configured ticket system (jira or github or linear)
        target_server = None
        for name in ["jira", "github", "linear"]:
            if name in configs:
                target_server = name
                break
                
        if not target_server:
            # Fallback to first available server
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

    async def call_server_tool(self, server_name: str, tool_name: str, arguments: dict) -> Any:
        """
        Connects to the specified stdio MCP server, runs the tool, and returns the result.
        """
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            raise RuntimeError("The 'mcp' Python SDK is not installed. Please install it using pip.")

        configs = self._load_server_configs()
        if server_name not in configs:
            raise ValueError(f"MCP server '{server_name}' is not configured in {self.config_path}")

        server_conf = configs[server_name]
        command = server_conf.get("command")
        args = server_conf.get("args", [])
        env = server_conf.get("env")

        if not command:
            raise ValueError(f"MCP server '{server_name}' config requires a 'command' field.")

        run_env = os.environ.copy()
        if env:
            run_env.update({k: str(v) for k, v in env.items()})

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

        configs = self._load_server_configs()
        if server_name not in configs:
            raise ValueError(f"MCP server '{server_name}' is not configured.")

        server_conf = configs[server_name]
        command = server_conf.get("command")
        args = server_conf.get("args", [])
        env = server_conf.get("env")

        run_env = os.environ.copy()
        if env:
            run_env.update({k: str(v) for k, v in env.items()})

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
