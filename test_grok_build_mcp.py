import inspect
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import grok_build_mcp


class GrokServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.patches = [
            patch.object(grok_build_mcp, "STATE_DIR", self.root / "state"),
            patch.object(grok_build_mcp, "SESSIONS_FILE", self.root / "state" / "sessions.json"),
            patch.object(grok_build_mcp, "LOG_DIR", self.root / "logs"),
        ]
        for item in self.patches:
            item.start()
        self.commands: list[tuple[str, ...]] = []

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temporary_directory.cleanup()

    def invoke(
        self,
        stdout: str,
        stderr: str = "",
        exit_code: int = 0,
        cwd: str = "project",
        prompt: str = "完成任务",
    ):
        def run_process(command, stdout, stderr, **kwargs):
            self.commands.append(command)
            stdout.write(stdout_content.encode())
            stderr.write(stderr_content.encode())
            self.assertIs(kwargs["stdin"], grok_build_mcp.subprocess.DEVNULL)
            return SimpleNamespace(returncode=exit_code)

        stdout_content = stdout
        stderr_content = stderr
        with patch.object(grok_build_mcp.subprocess, "run", run_process):
            return grok_build_mcp.run_grok(prompt, str(self.root / cwd))

    def test_tool_exposes_only_prompt_and_cwd(self) -> None:
        self.assertEqual(list(inspect.signature(grok_build_mcp.run_grok).parameters), ["prompt", "cwd"])
        tools = grok_build_mcp.mcp._tool_manager.list_tools()
        self.assertEqual([tool.name for tool in tools], ["run_grok"])
        self.assertEqual(set(tools[0].parameters["properties"]), {"prompt", "cwd"})

    def test_command_is_resolved_from_path_without_running_npm(self) -> None:
        with (
            patch.object(grok_build_mcp.shutil, "which", return_value=r"C:\\npm\\grok.cmd") as which,
            patch.object(grok_build_mcp.subprocess, "check_output") as check_output,
        ):
            command = grok_build_mcp.command_from_path("grok", "GROK_COMMAND")

        self.assertEqual(command, r"C:\\npm\\grok.cmd")
        which.assert_called_once_with("grok.cmd")
        check_output.assert_not_called()

    def test_same_directory_resumes_saved_session(self) -> None:
        payload = json.dumps(
            {"summary": "完成", "changed_files": [], "tests": ["通过"], "blockers": []}
        )
        first = self.invoke(payload)
        second = self.invoke(payload)
        session_id = next(iter(json.loads(grok_build_mcp.SESSIONS_FILE.read_text(encoding="utf-8")).values()))

        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(grok_build_mcp.MODEL, "grok-4.6")
        self.assertEqual(grok_build_mcp.REASONING_EFFORT, "xhigh")
        self.assertIn("--model", self.commands[0])
        self.assertIn(grok_build_mcp.MODEL, self.commands[0])
        self.assertIn("--reasoning-effort", self.commands[0])
        self.assertIn(grok_build_mcp.REASONING_EFFORT, self.commands[0])
        self.assertIn("--no-plan", self.commands[0])
        self.assertIn("--no-memory", self.commands[0])
        self.assertIn("--session-id", self.commands[0])
        self.assertIn(session_id, self.commands[0])
        self.assertEqual(uuid.UUID(session_id).version, 7)
        self.assertIn("--resume", self.commands[1])
        self.assertIn(session_id, self.commands[1])

    def test_different_directories_use_different_sessions(self) -> None:
        payload = json.dumps(
            {"summary": "完成", "changed_files": [], "tests": [], "blockers": []}
        )
        self.invoke(payload, cwd="first")
        self.invoke(payload, cwd="second")
        sessions = json.loads(grok_build_mcp.SESSIONS_FILE.read_text(encoding="utf-8"))

        self.assertEqual(len(sessions), 2)
        self.assertEqual(len(set(sessions.values())), 2)
        self.assertIn("--session-id", self.commands[0])
        self.assertIn("--session-id", self.commands[1])

    def test_parses_grok_structured_output(self) -> None:
        output = json.dumps(
            {
                "text": "最终回复",
                "structuredOutput": {
                    "summary": "完成",
                    "changed_files": [],
                    "tests": [],
                    "blockers": [],
                },
            }
        )
        result = self.invoke(output)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["result"]["summary"], "完成")

    def test_multiline_prompt_is_passed_through_a_utf8_file(self) -> None:
        payload = json.dumps(
            {"summary": "完成", "changed_files": [], "tests": [], "blockers": []}
        )
        prompt = "只改一个点：\n修复多行提示传输。\n运行测试。"

        self.invoke(payload, prompt=prompt)

        command = self.commands[0]
        prompt_file = Path(command[command.index("--prompt-file") + 1])
        self.assertNotIn("--single", command)
        self.assertEqual(prompt_file.read_text(encoding="utf-8"), prompt)

    def test_failures_return_log_paths(self) -> None:
        result = self.invoke("not json", stderr="failure details", exit_code=1)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["exit_code"], 1)
        self.assertIsNone(result["result"])
        self.assertTrue(Path(result["stdout_log"]).exists())
        self.assertTrue(Path(result["stderr_log"]).exists())
        self.assertEqual(Path(result["stderr_log"]).read_text(encoding="utf-8"), "failure details")
        self.assertFalse(grok_build_mcp.SESSIONS_FILE.exists())


if __name__ == "__main__":
    unittest.main()
