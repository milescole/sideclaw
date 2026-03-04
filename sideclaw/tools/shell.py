"""Shell execution tool."""

import asyncio
from typing import Any

from sideclaw.tools.base import Tool


class ExecTool(Tool):
    """Execute shell commands."""

    def __init__(self, timeout: int = 60) -> None:
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        return "Execute a shell command and return its output"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"}
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs) -> str:
        command = kwargs["command"]
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
            output = stdout.decode() + stderr.decode()
            if proc.returncode != 0:
                output += f"\n(exit code {proc.returncode})"
            return output.strip() if output.strip() else "(no output)"
        except TimeoutError:
            proc.kill()
            return f"Error: Command timed out after {self._timeout}s"
        except (OSError, ValueError, UnicodeDecodeError) as e:
            return f"Error: {e}"
