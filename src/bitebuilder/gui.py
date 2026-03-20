from __future__ import annotations

import argparse
import json
import shutil
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from bitebuilder.models import GenerationRequest
from bitebuilder.pipeline import run_generation

HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BiteBuilder</title>
  <style>
    :root {
      --bg: #07111d;
      --panel: rgba(14, 24, 43, 0.88);
      --panel-2: rgba(10, 17, 31, 0.92);
      --line: rgba(125, 189, 255, 0.2);
      --text: #ecf6ff;
      --muted: #8fa5bf;
      --accent: #5df0cf;
      --accent-2: #ffbe5c;
      --danger: #ff8c8c;
      --shadow: 0 30px 80px rgba(0, 0, 0, 0.45);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: "JetBrains Mono", "Fira Code", "SFMono-Regular", monospace;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(93, 240, 207, 0.16), transparent 28%),
        radial-gradient(circle at top right, rgba(255, 190, 92, 0.15), transparent 32%),
        linear-gradient(160deg, #050b14 0%, #091526 45%, #08101b 100%);
    }

    .shell {
      width: min(1380px, calc(100vw - 32px));
      margin: 20px auto;
      padding: 24px;
      border: 1px solid var(--line);
      border-radius: 28px;
      background: rgba(6, 11, 20, 0.7);
      backdrop-filter: blur(14px);
      box-shadow: var(--shadow);
    }

    .topbar {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      margin-bottom: 22px;
    }

    .kicker {
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.18em;
      font-size: 12px;
      margin-bottom: 10px;
    }

    h1 {
      margin: 0;
      font-family: "Space Grotesk", "Avenir Next", "Segoe UI", sans-serif;
      font-size: clamp(32px, 5vw, 64px);
      line-height: 0.95;
      letter-spacing: -0.04em;
    }

    .subhead {
      margin-top: 12px;
      max-width: 78ch;
      color: var(--muted);
      line-height: 1.6;
      font-size: 14px;
    }

    .status {
      min-width: 300px;
      padding: 16px 18px;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: linear-gradient(180deg, rgba(18, 30, 52, 0.9), rgba(10, 18, 33, 0.95));
    }

    .status h2,
    .panel h2 {
      margin: 0 0 10px;
      font-family: "Space Grotesk", "Segoe UI", sans-serif;
      font-size: 18px;
      letter-spacing: -0.02em;
    }

    .status-line {
      font-size: 13px;
      color: var(--muted);
      margin: 6px 0;
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(360px, 0.9fr);
      gap: 18px;
    }

    .panel {
      border: 1px solid var(--line);
      border-radius: 24px;
      background: var(--panel);
      padding: 20px;
    }

    .form-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 14px;
    }

    .field {
      grid-column: span 12;
    }

    .field.half {
      grid-column: span 6;
    }

    .field.third {
      grid-column: span 4;
    }

    label {
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }

    input,
    select,
    textarea,
    button {
      width: 100%;
      border: 1px solid rgba(125, 189, 255, 0.18);
      border-radius: 16px;
      background: var(--panel-2);
      color: var(--text);
      font: inherit;
    }

    input,
    select,
    textarea {
      padding: 14px 16px;
    }

    textarea {
      min-height: 220px;
      resize: vertical;
      line-height: 1.5;
    }

    input:focus,
    select:focus,
    textarea:focus {
      outline: none;
      border-color: rgba(93, 240, 207, 0.65);
      box-shadow: 0 0 0 3px rgba(93, 240, 207, 0.12);
    }

    .provider-note,
    .mini-note {
      margin-top: 8px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }

    .toggle-row {
      display: flex;
      gap: 16px;
      align-items: center;
      flex-wrap: wrap;
      margin-top: 6px;
    }

    .toggle {
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid rgba(125, 189, 255, 0.12);
      background: rgba(8, 15, 28, 0.72);
      color: var(--text);
      width: auto;
    }

    .toggle input {
      width: 16px;
      height: 16px;
      margin: 0;
    }

    .actions {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      margin-top: 18px;
      flex-wrap: wrap;
      align-items: center;
    }

    .actions-left,
    .actions-right {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }

    button {
      width: auto;
      cursor: pointer;
      transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
      padding: 14px 18px;
    }

    button:hover {
      transform: translateY(-1px);
      border-color: rgba(93, 240, 207, 0.48);
    }

    .primary {
      background: linear-gradient(135deg, rgba(93, 240, 207, 0.9), rgba(123, 255, 224, 0.78));
      color: #051016;
      font-weight: 700;
    }

    .ghost {
      background: rgba(8, 15, 28, 0.72);
      color: var(--text);
    }

    .pill {
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(125, 189, 255, 0.14);
      color: var(--muted);
      background: rgba(8, 15, 28, 0.6);
      font-size: 12px;
    }

    .log {
      min-height: 420px;
      max-height: 65vh;
      overflow: auto;
      padding: 16px;
      border-radius: 18px;
      background: #050b14;
      border: 1px solid rgba(93, 240, 207, 0.12);
      white-space: pre-wrap;
      line-height: 1.55;
      color: #bafbe9;
    }

    .result-card {
      margin-top: 14px;
      padding: 14px 16px;
      border-radius: 18px;
      border: 1px solid rgba(255, 190, 92, 0.16);
      background: rgba(255, 190, 92, 0.07);
      color: var(--text);
    }

    .error {
      color: var(--danger);
    }

    .hidden {
      display: none;
    }

    @media (max-width: 1100px) {
      .grid {
        grid-template-columns: 1fr;
      }

      .status {
        min-width: 0;
      }
    }

    @media (max-width: 760px) {
      .shell {
        width: min(100vw, calc(100vw - 16px));
        margin: 8px auto;
        padding: 14px;
        border-radius: 20px;
      }

      .topbar {
        flex-direction: column;
        align-items: stretch;
      }

      .field.half,
      .field.third {
        grid-column: span 12;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="topbar">
      <div>
        <div class="kicker">Localhost Edit Bay</div>
        <h1>BiteBuilder</h1>
        <div class="subhead">
          Transcript, Premiere XML, and a creative brief in. Selectable Ollama, Claude Code, or dry-run logic out.
          This browser UI stays thin and drives the same Python pipeline as the CLI.
        </div>
      </div>
      <div class="status">
        <h2>Runtime</h2>
        <div class="status-line" id="runtime-status">Loading local provider status...</div>
        <div class="status-line" id="cwd-status"></div>
      </div>
    </div>

    <div class="grid">
      <section class="panel">
        <h2>Build A Select Sequence</h2>
        <form id="builder-form">
          <div class="form-grid">
            <div class="field half">
              <label for="transcript_path">Transcript Path</label>
              <input id="transcript_path" name="transcript_path" placeholder="/absolute/path/to/transcript.txt" required>
            </div>
            <div class="field half">
              <label for="premiere_xml_path">Premiere XML Path</label>
              <input id="premiere_xml_path" name="premiere_xml_path" placeholder="/absolute/path/to/source.xml" required>
            </div>

            <div class="field half">
              <label for="output_path">Output XML Path</label>
              <input id="output_path" name="output_path" placeholder="/absolute/path/to/output.xml" required>
              <div class="mini-note">Use the prefill button if you want the output next to the transcript.</div>
            </div>
            <div class="field half">
              <label for="sequence_title">Sequence Title</label>
              <input id="sequence_title" name="sequence_title" value="BiteBuilder Selects">
            </div>

            <div class="field third">
              <label for="provider">Provider</label>
              <select id="provider" name="provider">
                <option value="ollama">Ollama</option>
                <option value="claude-code">Claude Code</option>
              </select>
            </div>
            <div class="field third">
              <label for="model">Model</label>
              <input id="model" name="model" value="gemma3:12b">
            </div>
            <div class="field third provider-ollama">
              <label for="ollama_url">Ollama URL</label>
              <input id="ollama_url" name="ollama_url" value="http://127.0.0.1:11434">
            </div>

            <div class="field half provider-claude hidden">
              <label for="claude_command">Claude Command</label>
              <input id="claude_command" name="claude_command" value="claude">
              <div class="mini-note">Used for local headless calls like <code>claude -p</code>.</div>
            </div>
            <div class="field half provider-claude hidden">
              <label for="claude_auth_token">Claude Auth Token</label>
              <input id="claude_auth_token" name="claude_auth_token" type="password" placeholder="Optional ANTHROPIC_AUTH_TOKEN override">
              <div class="mini-note">Leave blank to use the current <code>claude auth login</code> session.</div>
            </div>

            <div class="field">
              <label for="brief">Creative Brief</label>
              <textarea id="brief" name="brief" placeholder="Find the cleanest emotional arc, avoid throat-clearing, keep the rhythm tight, and bias toward lines that can stand alone in a short."></textarea>
              <div class="provider-note" id="provider-note">
                Ollama stays fully local. Claude Code uses your local Claude login or an optional auth token override through the local CLI.
              </div>
            </div>
          </div>

          <div class="actions">
            <div class="actions-left">
              <label class="toggle">
                <input id="dry_run" name="dry_run" type="checkbox">
                <span>Dry run fallback only</span>
              </label>
              <div class="pill" id="provider-pill">Provider: Ollama</div>
            </div>
            <div class="actions-right">
              <button class="ghost" type="button" id="prefill-output">Prefill Output</button>
              <button class="ghost" type="button" id="clear-log">Clear Log</button>
              <button class="primary" type="submit" id="submit-button">Generate XML</button>
            </div>
          </div>
        </form>
      </section>

      <aside class="panel">
        <h2>Run Log</h2>
        <div class="subhead" style="margin-top: 0; margin-bottom: 14px;">
          Use this while iterating on prompts, XML structure, provider behavior, and Premiere import edge cases.
        </div>
        <div class="log" id="log">Ready.</div>
        <div class="result-card hidden" id="result-card"></div>
      </aside>
    </div>
  </div>

  <script>
    const form = document.getElementById("builder-form");
    const providerEl = document.getElementById("provider");
    const modelEl = document.getElementById("model");
    const logEl = document.getElementById("log");
    const resultCard = document.getElementById("result-card");
    const runtimeStatus = document.getElementById("runtime-status");
    const cwdStatus = document.getElementById("cwd-status");
    const providerPill = document.getElementById("provider-pill");
    const providerNote = document.getElementById("provider-note");
    const submitButton = document.getElementById("submit-button");

    const providerDefaults = {
      "ollama": {
        model: "gemma3:12b",
        note: "Ollama stays fully local. Point the URL at your local Ollama daemon and keep inference on-box."
      },
      "claude-code": {
        model: "sonnet",
        note: "Claude Code runs locally through the CLI. Leave the token blank to use your saved Claude login, or paste an ANTHROPIC_AUTH_TOKEN override."
      }
    };

    function setProviderUI() {
      const provider = providerEl.value;
      document.querySelectorAll(".provider-ollama").forEach((el) => {
        el.classList.toggle("hidden", provider !== "ollama");
      });
      document.querySelectorAll(".provider-claude").forEach((el) => {
        el.classList.toggle("hidden", provider !== "claude-code");
      });
      providerPill.textContent = provider === "ollama" ? "Provider: Ollama" : "Provider: Claude Code";
      providerNote.textContent = providerDefaults[provider].note;
      if (!modelEl.value || modelEl.value === providerDefaults["ollama"].model || modelEl.value === providerDefaults["claude-code"].model) {
        modelEl.value = providerDefaults[provider].model;
      }
      saveDraft();
    }

    function appendLog(text, isError = false) {
      if (logEl.textContent === "Ready.") {
        logEl.textContent = "";
      }
      const block = document.createElement("div");
      if (isError) block.className = "error";
      block.textContent = text;
      logEl.appendChild(block);
      logEl.scrollTop = logEl.scrollHeight;
    }

    function clearLog() {
      logEl.textContent = "Ready.";
      resultCard.classList.add("hidden");
      resultCard.textContent = "";
    }

    function prefillOutput() {
      const transcript = document.getElementById("transcript_path").value.trim();
      const output = document.getElementById("output_path");
      if (!transcript) return;
      if (transcript.endsWith(".txt")) {
        output.value = transcript.slice(0, -4) + "_bitebuilder.xml";
        saveDraft();
      }
    }

    function saveDraft() {
      const data = Object.fromEntries(new FormData(form).entries());
      data.dry_run = document.getElementById("dry_run").checked;
      localStorage.setItem("bitebuilder-draft", JSON.stringify(data));
    }

    function restoreDraft() {
      const raw = localStorage.getItem("bitebuilder-draft");
      if (!raw) return;
      try {
        const data = JSON.parse(raw);
        for (const [key, value] of Object.entries(data)) {
          const field = form.elements.namedItem(key);
          if (!field) continue;
          if (field.type === "checkbox") {
            field.checked = Boolean(value);
          } else if (typeof value === "string") {
            field.value = value;
          }
        }
      } catch (_error) {
      }
    }

    async function loadInfo() {
      const response = await fetch("/api/info");
      const data = await response.json();
      const claude = data.providers["claude-code"];
      runtimeStatus.textContent =
        "Ollama: local HTTP provider. Claude Code: " +
        (claude.available ? `found at ${claude.command}` : "not found in PATH");
      cwdStatus.textContent = `Working directory: ${data.cwd}`;
    }

    form.addEventListener("input", saveDraft);
    providerEl.addEventListener("change", setProviderUI);
    document.getElementById("prefill-output").addEventListener("click", prefillOutput);
    document.getElementById("clear-log").addEventListener("click", clearLog);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearLog();
      saveDraft();
      submitButton.disabled = true;
      submitButton.textContent = "Generating...";

      const payload = Object.fromEntries(new FormData(form).entries());
      payload.dry_run = document.getElementById("dry_run").checked;

      try {
        const response = await fetch("/api/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await response.json();
        (data.logs || []).forEach((line) => appendLog(line));
        if (!response.ok || !data.ok) {
          appendLog(data.error || "Generation failed.", true);
          return;
        }
        resultCard.classList.remove("hidden");
        resultCard.innerHTML =
          `<strong>${data.result.sequence_title}</strong><br>` +
          `${data.result.selected_count} selections written to:<br><code>${data.result.output_path}</code>`;
        if (data.result.warnings && data.result.warnings.length) {
          appendLog("Warnings:");
          data.result.warnings.forEach((warning) => appendLog(`- ${warning}`, true));
        }
      } catch (error) {
        appendLog(String(error), true);
      } finally {
        submitButton.disabled = false;
        submitButton.textContent = "Generate XML";
      }
    });

    restoreDraft();
    setProviderUI();
    loadInfo().catch((error) => {
      runtimeStatus.textContent = "Could not load runtime info.";
      cwdStatus.textContent = String(error);
    });
  </script>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bitebuilder-gui",
        description="Launch the BiteBuilder localhost UI.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind. Use 0 for an ephemeral port.")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open a browser.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), _build_handler())
    url = f"http://{args.host}:{server.server_port}"
    print(f"BiteBuilder web UI listening at {url}")
    print("Press Ctrl+C to stop the server.")

    if not args.no_browser:
        opened = webbrowser.open(url)
        if not opened:
            print(f"Open this URL in your browser: {url}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down BiteBuilder web UI...")
    finally:
        server.server_close()


def _build_handler():
    class BiteBuilderHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._write_response(HTTPStatus.OK, HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
                return

            if parsed.path == "/api/info":
                payload = {
                    "cwd": str(Path.cwd()),
                    "providers": {
                        "ollama": {
                            "available": True,
                            "url": "http://127.0.0.1:11434",
                        },
                        "claude-code": {
                            "available": shutil.which("claude") is not None,
                            "command": shutil.which("claude") or "claude",
                        },
                    },
                }
                self._write_json(HTTPStatus.OK, payload)
                return

            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/generate":
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
                return

            try:
                payload = self._read_json()
                request = request_from_payload(payload)
            except ValueError as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc), "logs": []})
                return

            logs: list[str] = []
            try:
                result = run_generation(request, logger=logs.append)
            except Exception as exc:
                logs.append(f"Generation failed: {exc}")
                self._write_json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "ok": False,
                        "error": str(exc),
                        "logs": logs,
                    },
                )
                return

            self._write_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "logs": logs,
                    "result": {
                        "output_path": str(result.output_path),
                        "sequence_title": result.sequence_title,
                        "selected_count": result.selected_count,
                        "warnings": result.warnings,
                    },
                },
            )

        def log_message(self, format: str, *args) -> None:
            return

        def _read_json(self) -> dict:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("Request body must be valid JSON.") from exc
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object.")
            return payload

        def _write_json(self, status: HTTPStatus, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self._write_response(status, body, "application/json; charset=utf-8")

        def _write_response(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return BiteBuilderHandler


def request_from_payload(payload: dict) -> GenerationRequest:
    transcript_path = _required_path(payload, "transcript_path")
    premiere_xml_path = _required_path(payload, "premiere_xml_path")
    output_path = _required_path(payload, "output_path")
    brief = _required_text(payload, "brief")

    provider = _optional_text(payload.get("provider")) or "ollama"
    if provider not in {"ollama", "claude-code"}:
        raise ValueError(f"Unsupported provider: {provider}")

    return GenerationRequest(
        transcript_path=transcript_path,
        premiere_xml_path=premiere_xml_path,
        output_path=output_path,
        brief=brief,
        provider=provider,
        sequence_title=_optional_text(payload.get("sequence_title")) or "BiteBuilder Selects",
        model=_optional_text(payload.get("model")),
        ollama_url=_optional_text(payload.get("ollama_url")) or "http://127.0.0.1:11434",
        claude_command=_optional_text(payload.get("claude_command")) or "claude",
        claude_auth_token=_optional_text(payload.get("claude_auth_token")),
        dry_run=bool(payload.get("dry_run")),
    )


def _required_path(payload: dict, key: str) -> Path:
    text = _optional_text(payload.get(key))
    if not text:
        raise ValueError(f"Missing required field: {key}")
    return Path(text).expanduser().resolve()


def _required_text(payload: dict, key: str) -> str:
    text = _optional_text(payload.get(key))
    if not text:
        raise ValueError(f"Missing required field: {key}")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    main()
