"""Use a LionAGI agent to investigate API timeouts from a remote server."""

from __future__ import annotations

import asyncio
import os

from lionagi.agent import AgentSpec, create_agent
from lionagi.tools.remote import RemoteApiDiagnosticTool


async def main() -> None:
    config = AgentSpec.compose(
        "remote-api-monitor",
        tools=[],
        system_prompt=(
            "You investigate API latency and timeout failures. Use the remote_api_diagnose "
            "tool first, explain whether the delay is DNS, TCP connect, TLS, time-to-first-byte, "
            "or total response time, and recommend the next verification step. Do not guess "
            "credentials or run unrelated commands."
        ),
    )
    branch = await create_agent(config, load_settings=False)
    branch.register_tools([RemoteApiDiagnosticTool().to_tool()])

    request = {
        "host": os.environ["REMOTE_API_SSH_HOST"],
        "endpoint": os.environ["REMOTE_API_ENDPOINT"],
        "user": os.environ.get("REMOTE_API_SSH_USER"),
        "key_path": os.environ.get("REMOTE_API_SSH_KEY"),
        "timeout": int(os.environ.get("REMOTE_API_TIMEOUT_MS", "30000")),
    }
    result = await branch.operate(
        instruction=(
            "Diagnose this remote API request using the registered diagnostic tool. "
            f"Probe parameters: {request}"
        )
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())