from sideclaw.tools.shell import ExecTool


async def test_exec_simple_command():
    tool = ExecTool(timeout=10)
    result = await tool.execute(command="echo hello")
    assert "hello" in result


async def test_exec_captures_stderr():
    tool = ExecTool(timeout=10)
    result = await tool.execute(command="echo error >&2")
    assert "error" in result


async def test_exec_timeout():
    tool = ExecTool(timeout=1)
    result = await tool.execute(command="sleep 10")
    assert "timeout" in result.lower() or "timed out" in result.lower()


async def test_exec_nonzero_exit():
    tool = ExecTool(timeout=10)
    result = await tool.execute(command="exit 1")
    assert "exit code" in result.lower() or result.strip() == ""
