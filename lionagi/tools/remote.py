# Copyright (c) 2023-2025, HaiyangLi <quantocean.li at gmail dot com>
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import shlex
import urllib.parse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lionagi.ln.concurrency import run_sync
from lionagi.protocols.action.tool import Tool

from ._subprocess import _subprocess_sync
from .base import LionTool


class RemoteApiDiagnosticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = Field(..., description="Remote SSH hostname or IP address.")
    endpoint: str = Field(..., description="HTTP or HTTPS API endpoint to probe.")
    user: str | None = Field(None, description="SSH username. Uses the local default when omitted.")
    key_path: str | None = Field(None, description="Path to the SSH private key on the local machine.")
    timeout: int = Field(default=30_000, ge=1, le=300_000, description="Probe timeout in milliseconds.")

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("endpoint must be an absolute http:// or https:// URL")
        return value


def _build_probe_command(endpoint: str, timeout_ms: int) -> str:
    timeout_seconds = max(1, timeout_ms // 1000)
    format_string = (
        "status=%{http_code} dns=%{time_namelookup} connect=%{time_connect} "
        "tls=%{time_appconnect} first_byte=%{time_starttransfer} total=%{time_total}"
    )
    return (
        "curl --silent --show-error --output /dev/null "
        f"--connect-timeout {timeout_seconds} --max-time {timeout_seconds} "
        f"--write-out {shlex.quote(format_string)} -- {shlex.quote(endpoint)}"
    )


def _remote_probe_sync(request: RemoteApiDiagnosticRequest) -> dict:
    target = f"{request.user}@{request.host}" if request.user else request.host
    command = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={max(1, request.timeout // 1000)}"]
    if request.key_path:
        command.extend(["-i", request.key_path])
    command.extend([target, _build_probe_command(request.endpoint, request.timeout)])

    result = _subprocess_sync(
        command,
        False,
        request.timeout / 1000,
        None,
        timeout_ms=request.timeout,
    )
    response = {
        "success": result["returncode"] == 0,
        "host": request.host,
        "endpoint": request.endpoint,
        "return_code": result["returncode"],
        "stdout": result["stdout"].strip(),
        "stderr": result["stderr"].strip(),
        "timed_out": result.get("timed_out", False),
    }
    if response["success"]:
        response["diagnosis"] = "Remote curl completed; compare the timing fields to locate the slow phase."
    elif response["timed_out"]:
        response["diagnosis"] = "SSH or the remote curl probe exceeded the timeout."
    elif "Could not resolve hostname" in response["stderr"]:
        response["diagnosis"] = "The local SSH client could not resolve the remote host."
    elif "Connection timed out" in response["stderr"]:
        response["diagnosis"] = "SSH could not connect to the remote host before its connect timeout."
    elif "curl" in response["stderr"].lower():
        response["diagnosis"] = "SSH reached the host, but the remote curl request failed."
    else:
        response["diagnosis"] = "The remote probe failed before returning HTTP timing data."
    return response


class RemoteApiDiagnosticTool(LionTool):
    is_lion_system_tool = True
    system_tool_name = "remote_api_diagnose"

    def __init__(self):
        self._tool = None

    async def handle_request(self, request: RemoteApiDiagnosticRequest) -> dict:
        if isinstance(request, dict):
            request = RemoteApiDiagnosticRequest(**request)
        return await run_sync(_remote_probe_sync, request)

    def to_tool(self) -> Tool:
        if self._tool is None:

            async def remote_api_diagnose(**kwargs):
                """Probe an HTTP API from a remote server over SSH.

                Returns SSH status, curl timing fields, and a diagnosis. The SSH
                client must be installed and configured for non-interactive auth.
                This tool only runs a fixed curl probe; it does not accept commands.
                """
                return await self.handle_request(RemoteApiDiagnosticRequest(**kwargs))

            self._tool = Tool(
                func_callable=remote_api_diagnose,
                request_options=RemoteApiDiagnosticRequest,
            )
        return self._tool


__all__ = ["RemoteApiDiagnosticRequest", "RemoteApiDiagnosticTool"]