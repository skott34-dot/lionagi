from __future__ import annotations

from unittest.mock import patch

from lionagi.tools.remote import (
    RemoteApiDiagnosticRequest,
    RemoteApiDiagnosticTool,
    _build_probe_command,
)


def test_probe_command_quotes_endpoint_and_contains_timing_fields():
    command = _build_probe_command("https://api.example.test/health?x=1&y=2", 5_000)

    assert "--connect-timeout 5" in command
    assert "time_namelookup" in command
    assert "'https://api.example.test/health?x=1&y=2'" in command


def test_remote_tool_reports_successful_probe():
    request = RemoteApiDiagnosticRequest(
        host="server.example.test",
        endpoint="https://api.example.test/health",
        user="deploy",
        key_path="C:/keys/deploy",
    )
    result = {
        "returncode": 0,
        "stdout": "status=200 dns=0.01 connect=0.02 tls=0.03 first_byte=0.05 total=0.06",
        "stderr": "",
    }

    with patch("lionagi.tools.remote._subprocess_sync", return_value=result) as run:
        response = __import__("asyncio").run(RemoteApiDiagnosticTool().handle_request(request))

    assert response["success"] is True
    assert "timing fields" in response["diagnosis"]
    assert run.call_args.args[0][:5] == [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=30",
    ]