#!/usr/bin/env python3
"""Hit MCP tool call using the mcp SDK directly.

Usage: _hit_sdk.py hit_health
       _hit_sdk.py hit_scan '{"subreddits":["HousingUK"],"keywords":["valuation"],"limit":3}'

Must be run with a Python that has the `mcp` package installed.

Configuration:
  HIT_MCP_ROOT     Path to the hitman-red repo. Defaults to a sibling
                   `hitman-red` folder beside this project, then common local/VPS paths.
  HIT_MCP_COMMAND  Python executable used to launch Hit MCP. Defaults to the
                   hitman-red venv Python when present, otherwise this Python.
  HIT_MCP_ARGS     JSON list of args for the command. Defaults to ["-m", "src.mcp_server"].
"""
import asyncio, json, os, sys, shlex
from pathlib import Path


from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


HERE = Path(__file__).resolve().parent


def _existing_path(*candidates: str | Path) -> Path | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists():
            return path.resolve()
    return None


def _hit_root() -> Path:
    configured = os.getenv("HIT_MCP_ROOT") or os.getenv("HITMAN_RED_ROOT")
    root = _existing_path(
        configured,
        HERE.parent / "hitman-red",
        Path("/opt/hitman-red"),
        Path.home() / "hitman-red",
        Path.home() / "hitman-red-main",
    )
    if not root:
        raise RuntimeError("Set HIT_MCP_ROOT to the hitman-red repo path")
    return root


def _hit_command(root: Path) -> str:
    configured = os.getenv("HIT_MCP_COMMAND")
    if configured:
        return configured
    if os.name == "nt":
        return sys.executable
    venv_python = root / "venv" / "bin" / "python"
    return str(venv_python if venv_python.exists() else Path(sys.executable))


def _hit_args() -> list[str]:
    configured = os.getenv("HIT_MCP_ARGS")
    if not configured:
        return ["-m", "src.mcp_server"]
    try:
        parsed = json.loads(configured)
        if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
            return parsed
    except Exception:
        pass
    return shlex.split(configured)


def server_parameters() -> StdioServerParameters:
    root = _hit_root()
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    return StdioServerParameters(
        command=_hit_command(root),
        args=_hit_args(),
        env=env,
        cwd=str(root),
    )


async def call_tool(name: str, args: dict = None) -> dict | None:
    try:
        async with stdio_client(server_parameters()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, args or {})
                content = result.content
                if content:
                    return {"raw": content[0].text, "success": True}
                return {"raw": str(result), "success": True}
    except Exception as e:
        return {"raw": str(e), "success": False}


def call_tool_sync(name: str, args: dict = None) -> dict | None:
    try:
        return asyncio.run(call_tool(name, args))
    except Exception as e:
        return {"raw": str(e), "success": False}


if __name__ == "__main__":
    # CLI: python _hit_sdk.py hit_health
    # CLI: python _hit_sdk.py hit_scan '{"subreddits":["HousingUK"],"keywords":["valuation"],"limit":3}'
    name = sys.argv[1] if len(sys.argv) > 1 else "hit_health"
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    result = call_tool_sync(name, args)
    print(json.dumps(result, indent=2, default=str)[:5000])
