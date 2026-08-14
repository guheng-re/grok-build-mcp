import json
import os
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP


ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
SESSIONS_FILE = STATE_DIR / "sessions.json"
LOG_DIR = ROOT / "logs"
FINAL_SCHEMA = json.dumps(
    {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "changed_files": {"type": "array", "items": {"type": "string"}},
            "tests": {"type": "array", "items": {"type": "string"}},
            "blockers": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "changed_files", "tests", "blockers"],
        "additionalProperties": False,
    },
    separators=(",", ":"),
)
MODEL = os.environ.get("GROK_MODEL", "grok-4.6")
REASONING_EFFORT = os.environ.get("GROK_REASONING_EFFORT", "xhigh")

mcp = FastMCP("grok_build")


def normalized_cwd(cwd: str) -> str:
    return str(Path(cwd).resolve())


def command_from_path(command_name: str, environment_name: str) -> str:
    configured_command = os.environ.get(environment_name)
    if configured_command:
        return configured_command
    command = f"{command_name}.cmd" if os.name == "nt" else command_name
    return shutil.which(command) or command


def new_session_id() -> str:
    timestamp = int(time.time() * 1000)
    value = (
        (timestamp << 80)
        | (0x7 << 76)
        | (secrets.randbits(12) << 64)
        | (0x2 << 62)
        | secrets.randbits(62)
    )
    return str(uuid.UUID(int=value))


def load_sessions() -> dict[str, str]:
    if not SESSIONS_FILE.exists():
        return {}
    return json.loads(SESSIONS_FILE.read_text(encoding="utf-8"))


def session_for(cwd: str) -> tuple[str, bool]:
    key = normalized_cwd(cwd)
    sessions = load_sessions()
    if key in sessions:
        return sessions[key], True

    return new_session_id(), False


def save_session(cwd: str, session_id: str) -> None:
    key = normalized_cwd(cwd)
    sessions = load_sessions()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    sessions[key] = session_id
    SESSIONS_FILE.write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_result(stdout_log: Path) -> dict[str, Any]:
    payload = json.loads(stdout_log.read_text(encoding="utf-8"))
    result = payload.get("structuredOutput", payload) if isinstance(payload, dict) else payload
    required = {"summary", "changed_files", "tests", "blockers"}
    if not isinstance(result, dict) or set(result) != required:
        raise ValueError("Grok returned an unexpected JSON result")
    return result


@mcp.tool()
def run_grok(prompt: str, cwd: str) -> dict[str, Any]:
    """在指定工作目录中运行或继续运行 Grok Build。"""
    session_id, resumed = session_for(cwd)
    task_id = str(uuid.uuid4())
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stdout_log = LOG_DIR / f"{task_id}.stdout.log"
    stderr_log = LOG_DIR / f"{task_id}.stderr.log"
    prompt_file = LOG_DIR / f"{task_id}.prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    command = [
        command_from_path("grok", "GROK_COMMAND"),
        "--cwd",
        cwd,
        "--model",
        MODEL,
        "--reasoning-effort",
        REASONING_EFFORT,
        "--always-approve",
        "--no-plan",
        "--no-memory",
        "--output-format",
        "json",
        "--json-schema",
        FINAL_SCHEMA,
    ]
    if resumed:
        command.extend(["--resume", session_id])
    else:
        command.extend(["--session-id", session_id])
    command.extend(["--prompt-file", str(prompt_file)])

    try:
        with stdout_log.open("wb") as stdout_file, stderr_log.open("wb") as stderr_file:
            process = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
            )
    except OSError as error:
        if not stdout_log.exists():
            stdout_log.touch()
        if not stderr_log.exists():
            stderr_log.write_text(str(error), encoding="utf-8")
        return {
            "status": "failed",
            "exit_code": None,
            "result": None,
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "error": str(error),
        }

    try:
        result = parse_result(stdout_log)
        parse_error = None
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
        result = None
        parse_error = str(error)

    completed = process.returncode == 0 and result is not None
    if completed and not resumed:
        save_session(cwd, session_id)

    response: dict[str, Any] = {
        "status": "completed" if completed else "failed",
        "exit_code": process.returncode,
        "result": result,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }
    if process.returncode != 0:
        response["error"] = f"Grok exited with code {process.returncode}"
    elif parse_error:
        response["error"] = parse_error
    return response


if __name__ == "__main__":
    mcp.run(transport="stdio")
