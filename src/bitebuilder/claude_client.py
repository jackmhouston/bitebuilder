from __future__ import annotations

import json
import os
import subprocess


class ClaudeCodeError(RuntimeError):
    """Raised when the local Claude Code CLI fails."""


class ClaudeCodeClient:
    def __init__(self, command: str = "claude") -> None:
        self.command = command

    def generate_json(
        self,
        model: str | None,
        prompt: str,
        auth_token: str | None = None,
        timeout: float = 180.0,
    ) -> dict:
        command = [self.command, "-p", "--output-format", "json"]
        if model:
            command.extend(["--model", model])
        command.append(prompt)

        env = os.environ.copy()
        if auth_token:
            env["ANTHROPIC_AUTH_TOKEN"] = auth_token

        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except FileNotFoundError as exc:
            raise ClaudeCodeError(
                f"Claude Code CLI not found: {self.command}. Install it or change the command path."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCodeError("Claude Code timed out before returning a response.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            detail = stderr.splitlines()[-1] if stderr else f"exit code {exc.returncode}"
            raise ClaudeCodeError(f"Claude Code request failed: {detail}") from exc

        return _parse_claude_json_output(completed.stdout)


def _parse_claude_json_output(stdout: str) -> dict:
    text = stdout.strip()
    if not text:
        raise ClaudeCodeError("Claude Code returned an empty response.")

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaudeCodeError("Claude Code did not return valid JSON output.") from exc

    result_text = payload.get("result")
    if not isinstance(result_text, str) or not result_text.strip():
        raise ClaudeCodeError("Claude Code JSON output did not include a model result.")

    try:
        return json.loads(result_text)
    except json.JSONDecodeError as exc:
        raise ClaudeCodeError("Claude Code result was not valid JSON.") from exc
