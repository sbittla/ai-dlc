"""Start the MCP server over stdio and call it like an agent's client would (optional).

    pip install -e ".[mcp]"
    python scripts/try_client.py --target starter

It lists the tools, runs one legitimate query and one injection attempt, and
prints what came back. Requires the MCP Python SDK (mcp==2.3.0).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

LAB = Path(__file__).resolve().parent.parent


async def main(target: str) -> None:
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "relaymcp.server", "--db", str(LAB / "data" / "relay-test.sql"),
                                         "--audit", str(LAB / "evidence" / "mcp-audit.jsonl")],
                                   cwd=str(LAB / target))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("tools:", [t.name for t in tools.tools])
            for args in ({"template": "overdue_tasks", "params": {"project_id": 2, "as_of": "2026-11-08"}, "limit": 3},
                         {"template": "tasks_by_project", "params": {"project_id": "1 OR 1=1"}}):
                result = await session.call_tool("query", {"request": args})
                print(json.dumps(args), "->", result.content[0].text.replace("\n", " ")[:200])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", choices=["starter", "solution"], default="starter")
    asyncio.run(main(ap.parse_args().target))
