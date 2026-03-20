from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from bitebuilder.models import GenerationRequest
from bitebuilder.pipeline import run_generation

WINDOWS_DRIVE_RE = re.compile(r"^(?P<drive>[A-Za-z]):[\\/](?P<rest>.*)$")
WSL_UNC_RE = re.compile(r"^\\\\wsl(?:\.localhost)?\\[^\\]+\\(?P<rest>.*)$", re.IGNORECASE)

HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BiteBuilder</title>
  <style>
    :root {
      --bg: #000;
      --panel: #050505;
      --line: #2a2a2a;
      --line-strong: #fff;
      --text: #fff;
      --muted: #b8b8b8;
      --danger: #ff6b6b;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    }

    .app {
      width: min(1100px, calc(100vw - 24px));
      margin: 12px auto 48px;
    }

    .hero {
      padding: 20px 4px 18px;
      border-bottom: 1px solid var(--line);
    }

    .kicker {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 10px;
    }

    h1 {
      margin: 0;
      font-size: clamp(28px, 5vw, 52px);
      line-height: 1;
      letter-spacing: -0.04em;
      font-family: Arial, Helvetica, sans-serif;
      font-weight: 800;
    }

    .subtitle {
      margin-top: 12px;
      color: var(--muted);
      max-width: 70ch;
      line-height: 1.6;
      font-size: 14px;
    }

    .runtime {
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
      gap: 16px;
      margin-top: 18px;
    }

    .panel {
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
    }

    .panel h2 {
      margin: 0 0 14px;
      font-size: 16px;
      font-family: Arial, Helvetica, sans-serif;
      letter-spacing: 0.01em;
    }

    .stack {
      display: grid;
      gap: 14px;
    }

    .drop-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .dropzone {
      min-height: 180px;
      border: 1px dashed #6b6b6b;
      background: #020202;
      padding: 16px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 10px;
      cursor: pointer;
      transition: border-color 0.16s ease, background 0.16s ease;
    }

    .dropzone:hover,
    .dropzone.active {
      border-color: var(--line-strong);
      background: #090909;
    }

    .drop-title {
      font-size: 14px;
      font-weight: 700;
      font-family: Arial, Helvetica, sans-serif;
    }

    .drop-copy {
      color: var(--muted);
      line-height: 1.5;
      font-size: 13px;
    }

    .drop-meta {
      color: var(--text);
      font-size: 12px;
      line-height: 1.5;
      word-break: break-word;
    }

    .field {
      display: grid;
      gap: 8px;
    }

    .two-up {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .three-up {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }

    label {
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    input,
    select,
    textarea,
    button {
      width: 100%;
      border: 1px solid var(--line);
      background: #000;
      color: var(--text);
      font: inherit;
      border-radius: 0;
    }

    input,
    select,
    textarea {
      padding: 12px 14px;
    }

    textarea {
      min-height: 180px;
      resize: vertical;
      line-height: 1.5;
    }

    input:focus,
    select:focus,
    textarea:focus {
      outline: none;
      border-color: var(--line-strong);
    }

    .hint {
      font-size: 12px;
      color: var(--muted);
      line-height: 1.5;
    }

    .actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }

    button {
      width: auto;
      padding: 12px 16px;
      cursor: pointer;
    }

    button:hover {
      border-color: var(--line-strong);
    }

    .primary {
      background: #fff;
      color: #000;
      border-color: #fff;
      font-weight: 700;
    }

    .log {
      min-height: 460px;
      max-height: 70vh;
      overflow: auto;
      white-space: pre-wrap;
      background: #000;
      border: 1px solid var(--line);
      padding: 14px;
      line-height: 1.55;
      color: #fff;
    }

    .error {
      color: var(--danger);
    }

    .result {
      margin-top: 14px;
      border-top: 1px solid var(--line);
      padding-top: 14px;
      line-height: 1.6;
      font-size: 13px;
    }

    .result code {
      word-break: break-word;
    }

    .hidden {
      display: none !important;
    }

    @media (max-width: 900px) {
      .layout,
      .drop-grid,
      .two-up,
      .three-up {
        grid-template-columns: 1fr;
      }

      .app {
        width: min(100vw, calc(100vw - 16px));
      }
    }
  </style>
</head>
<body>
  <div class="app">
    <div class="hero">
      <div class="kicker">Localhost Edit Bay</div>
      <h1>BiteBuilder</h1>
      <div class="subtitle">
        Drop in a transcript, drop in the stringout XML, tell it what story you want, and let the local pipeline do the rest.
        Ollama stays supported. Claude Code stays supported. Dry run stays supported.
      </div>
      <div class="runtime" id="runtime-status">Loading runtime status...</div>
      <div class="runtime" id="cwd-status"></div>
    </div>

    <div class="layout">
      <section class="panel">
        <h2>Inputs</h2>
        <form id="builder-form" class="stack">
          <div class="drop-grid">
            <div class="dropzone" id="transcript-drop" tabindex="0">
              <div class="drop-title">Transcript .txt</div>
              <div class="drop-copy">Drag a transcript here or click to choose a file.</div>
              <div class="drop-meta" id="transcript-meta">No transcript loaded.</div>
              <input id="transcript-input" type="file" accept=".txt,text/plain" class="hidden">
            </div>
            <div class="dropzone" id="xml-drop" tabindex="0">
              <div class="drop-title">Stringout XML</div>
              <div class="drop-copy">Drag the Premiere XML export here or click to choose it.</div>
              <div class="drop-meta" id="xml-meta">No XML loaded.</div>
              <input id="xml-input" type="file" accept=".xml,text/xml,application/xml" class="hidden">
            </div>
          </div>

          <div class="two-up">
            <div class="field">
              <label for="sequence_title">Sequence Title</label>
              <input id="sequence_title" name="sequence_title" value="BiteBuilder Selects">
            </div>
            <div class="field">
              <label for="output_path">Optional Save Path</label>
              <input id="output_path" name="output_path" placeholder="Leave blank to auto-download. Windows paths like C:\\Users\\jackm\\Downloads\\out.xml work.">
              <div class="hint">If blank, the browser downloads the generated XML automatically.</div>
            </div>
          </div>

          <div class="three-up">
            <div class="field">
              <label for="provider">Provider</label>
              <select id="provider" name="provider">
                <option value="ollama">Ollama</option>
                <option value="claude-code">Claude Code</option>
              </select>
            </div>
            <div class="field">
              <label for="model">Model</label>
              <input id="model" name="model" value="gemma3:12b">
            </div>
            <div class="field provider-ollama">
              <label for="ollama_url">Ollama URL</label>
              <input id="ollama_url" name="ollama_url" value="http://127.0.0.1:11434">
            </div>
          </div>

          <div class="two-up provider-claude hidden">
            <div class="field">
              <label for="claude_command">Claude Command</label>
              <input id="claude_command" name="claude_command" value="claude">
            </div>
            <div class="field">
              <label for="claude_auth_token">Claude Auth Token</label>
              <input id="claude_auth_token" name="claude_auth_token" type="password" placeholder="Optional ANTHROPIC_AUTH_TOKEN override">
              <div class="hint">Left blank, BiteBuilder uses your current local Claude Code login.</div>
            </div>
          </div>

          <div class="field">
            <label for="brief">Story Prompt</label>
            <textarea id="brief" name="brief" placeholder="Make a good story from this. Keep the arc tight. Avoid filler. Prefer lines that can stand alone in a short."></textarea>
            <div class="hint" id="provider-note">Ollama stays fully local and uses the Ollama HTTP endpoint.</div>
          </div>

          <div class="actions">
            <label style="display:flex;gap:10px;align-items:center;border:1px solid var(--line);padding:12px 14px;text-transform:none;letter-spacing:0;width:auto;color:var(--text);">
              <input id="dry_run" name="dry_run" type="checkbox" style="width:auto;margin:0;">
              <span>Dry run fallback only</span>
            </label>
            <button type="button" id="prefill-output">Prefill Output Name</button>
            <button type="button" id="clear-log">Clear Log</button>
            <button type="submit" class="primary" id="submit-button">Generate XML</button>
          </div>
        </form>
      </section>

      <aside class="panel">
        <h2>Run Log</h2>
        <div class="hint" style="margin-bottom: 14px;">This stays simple: load files, write the prompt, generate, and get the XML back.</div>
        <div class="log" id="log">Ready.</div>
        <div class="result hidden" id="result"></div>
      </aside>
    </div>
  </div>

  <script>
    const form = document.getElementById("builder-form");
    const logEl = document.getElementById("log");
    const resultEl = document.getElementById("result");
    const submitButton = document.getElementById("submit-button");
    const providerEl = document.getElementById("provider");
    const modelEl = document.getElementById("model");
    const providerNote = document.getElementById("provider-note");
    const runtimeStatus = document.getElementById("runtime-status");
    const cwdStatus = document.getElementById("cwd-status");
    const transcriptMeta = document.getElementById("transcript-meta");
    const xmlMeta = document.getElementById("xml-meta");

    const fileState = {
      transcript: null,
      xml: null
    };

    const providerDefaults = {
      "ollama": {
        model: "gemma3:12b",
        note: "Ollama stays fully local and uses the Ollama HTTP endpoint."
      },
      "claude-code": {
        model: "sonnet",
        note: "Claude Code runs locally through the claude CLI. Leave the token blank to use your saved login."
      }
    };

    function appendLog(text, isError = false) {
      if (logEl.textContent === "Ready.") {
        logEl.textContent = "";
      }
      const row = document.createElement("div");
      if (isError) row.className = "error";
      row.textContent = text;
      logEl.appendChild(row);
      logEl.scrollTop = logEl.scrollHeight;
    }

    function clearLog() {
      logEl.textContent = "Ready.";
      resultEl.textContent = "";
      resultEl.classList.add("hidden");
    }

    function setProviderUI() {
      const provider = providerEl.value;
      document.querySelectorAll(".provider-ollama").forEach((el) => {
        el.classList.toggle("hidden", provider !== "ollama");
      });
      document.querySelectorAll(".provider-claude").forEach((el) => {
        el.classList.toggle("hidden", provider !== "claude-code");
      });
      providerNote.textContent = providerDefaults[provider].note;
      if (!modelEl.value || modelEl.value === "gemma3:12b" || modelEl.value === "sonnet") {
        modelEl.value = providerDefaults[provider].model;
      }
      saveDraft();
    }

    function saveDraft() {
      const data = {
        sequence_title: document.getElementById("sequence_title").value,
        output_path: document.getElementById("output_path").value,
        provider: providerEl.value,
        model: modelEl.value,
        ollama_url: document.getElementById("ollama_url").value,
        claude_command: document.getElementById("claude_command").value,
        brief: document.getElementById("brief").value,
        dry_run: document.getElementById("dry_run").checked
      };
      localStorage.setItem("bitebuilder-draft", JSON.stringify(data));
    }

    function restoreDraft() {
      const raw = localStorage.getItem("bitebuilder-draft");
      if (!raw) return;
      try {
        const data = JSON.parse(raw);
        if (typeof data.sequence_title === "string") document.getElementById("sequence_title").value = data.sequence_title;
        if (typeof data.output_path === "string") document.getElementById("output_path").value = data.output_path;
        if (typeof data.provider === "string") providerEl.value = data.provider;
        if (typeof data.model === "string") modelEl.value = data.model;
        if (typeof data.ollama_url === "string") document.getElementById("ollama_url").value = data.ollama_url;
        if (typeof data.claude_command === "string") document.getElementById("claude_command").value = data.claude_command;
        if (typeof data.brief === "string") document.getElementById("brief").value = data.brief;
        document.getElementById("dry_run").checked = Boolean(data.dry_run);
      } catch (_error) {
      }
    }

    function setFile(kind, file) {
      fileState[kind] = file;
      const meta = kind === "transcript" ? transcriptMeta : xmlMeta;
      if (!file) {
        meta.textContent = kind === "transcript" ? "No transcript loaded." : "No XML loaded.";
        return;
      }
      meta.textContent = `${file.name} (${Math.round(file.size / 1024)} KB)`;
    }

    function bindDropzone(dropId, inputId, kind) {
      const drop = document.getElementById(dropId);
      const input = document.getElementById(inputId);

      drop.addEventListener("click", () => input.click());
      drop.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          input.click();
        }
      });

      input.addEventListener("change", () => {
        const [file] = input.files;
        if (file) setFile(kind, file);
      });

      ["dragenter", "dragover"].forEach((eventName) => {
        drop.addEventListener(eventName, (event) => {
          event.preventDefault();
          drop.classList.add("active");
        });
      });

      ["dragleave", "drop"].forEach((eventName) => {
        drop.addEventListener(eventName, (event) => {
          event.preventDefault();
          if (eventName === "drop") {
            const [file] = event.dataTransfer.files;
            if (file) setFile(kind, file);
          }
          drop.classList.remove("active");
        });
      });
    }

    function maybePrefillOutput(filename) {
      const output = document.getElementById("output_path");
      if (output.value.trim()) return;
      const next = filename.replace(/\\.txt$/i, "") + "_bitebuilder.xml";
      output.value = next;
      saveDraft();
    }

    function downloadXml(filename, content) {
      const blob = new Blob([content], { type: "application/xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    }

    async function parseJsonResponse(response) {
      const raw = await response.text();
      try {
        return JSON.parse(raw);
      } catch (_error) {
        throw new Error(raw || `HTTP ${response.status}`);
      }
    }

    async function loadInfo() {
      const response = await fetch("/api/info");
      const data = await response.json();
      const claude = data.providers["claude-code"];
      runtimeStatus.textContent = `Ollama: local HTTP provider. Claude Code: ${claude.available ? `found at ${claude.command}` : "not found in PATH"}`;
      cwdStatus.textContent = `Working directory: ${data.cwd}`;
    }

    providerEl.addEventListener("change", setProviderUI);
    form.addEventListener("input", (event) => {
      if (event.target.id === "claude_auth_token") return;
      saveDraft();
    });
    document.getElementById("clear-log").addEventListener("click", clearLog);
    document.getElementById("prefill-output").addEventListener("click", () => {
      if (fileState.transcript) maybePrefillOutput(fileState.transcript.name);
    });

    bindDropzone("transcript-drop", "transcript-input", "transcript");
    bindDropzone("xml-drop", "xml-input", "xml");

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearLog();

      if (!fileState.transcript) {
        appendLog("Load a transcript .txt file first.", true);
        return;
      }
      if (!fileState.xml) {
        appendLog("Load a Premiere XML file first.", true);
        return;
      }

      submitButton.disabled = true;
      submitButton.textContent = "Generating...";

      try {
        const payload = {
          transcript_name: fileState.transcript.name,
          transcript_content: await fileState.transcript.text(),
          premiere_xml_name: fileState.xml.name,
          premiere_xml_content: await fileState.xml.text(),
          sequence_title: document.getElementById("sequence_title").value,
          output_path: document.getElementById("output_path").value,
          provider: providerEl.value,
          model: modelEl.value,
          ollama_url: document.getElementById("ollama_url").value,
          claude_command: document.getElementById("claude_command").value,
          claude_auth_token: document.getElementById("claude_auth_token").value,
          brief: document.getElementById("brief").value,
          dry_run: document.getElementById("dry_run").checked
        };

        const response = await fetch("/api/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await parseJsonResponse(response);

        (data.logs || []).forEach((line) => appendLog(line));

        if (!response.ok || !data.ok) {
          appendLog(data.error || "Generation failed.", true);
          return;
        }

        if (data.result.output_xml && data.result.download_name) {
          downloadXml(data.result.download_name, data.result.output_xml);
        }

        resultEl.classList.remove("hidden");
        resultEl.innerHTML = "";
        const lines = [
          `${data.result.sequence_title}`,
          `${data.result.selected_count} selections generated.`,
          data.result.saved_output_path
            ? `Saved to: ${data.result.saved_output_path}`
            : `Downloaded as: ${data.result.download_name}`
        ];
        lines.forEach((line) => {
          const row = document.createElement("div");
          row.textContent = line;
          resultEl.appendChild(row);
        });

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


@dataclass(slots=True)
class PreparedRequest:
    request: GenerationRequest
    temporary_dir: Path | None
    download_name: str
    saved_output_path: str | None


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
        opened = open_browser(url)
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

            prepared: PreparedRequest | None = None
            logs: list[str] = []
            try:
                payload = self._read_json()
                prepared = prepare_request_from_payload(payload)
                result = run_generation(prepared.request, logger=logs.append)
                output_xml = result.output_path.read_text(encoding="utf-8")
            except ValueError as exc:
                self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc), "logs": logs})
                return
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
            finally:
                if prepared is not None and prepared.temporary_dir is not None:
                    shutil.rmtree(prepared.temporary_dir, ignore_errors=True)

            self._write_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "logs": logs,
                    "result": {
                        "sequence_title": result.sequence_title,
                        "selected_count": result.selected_count,
                        "warnings": result.warnings,
                        "saved_output_path": prepared.saved_output_path,
                        "download_name": prepared.download_name,
                        "output_xml": output_xml,
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


def prepare_request_from_payload(payload: dict) -> PreparedRequest:
    brief = _required_text(payload, "brief")
    provider = _optional_text(payload.get("provider")) or "ollama"
    if provider not in {"ollama", "claude-code"}:
        raise ValueError(f"Unsupported provider: {provider}")

    temporary_dir: Path | None = None

    transcript_content = _optional_text(payload.get("transcript_content"))
    premiere_xml_content = _optional_text(payload.get("premiere_xml_content"))
    transcript_name = _sanitize_filename(_optional_text(payload.get("transcript_name")) or "transcript.txt")
    premiere_xml_name = _sanitize_filename(_optional_text(payload.get("premiere_xml_name")) or "stringout.xml")

    if transcript_content is not None and premiere_xml_content is not None:
        temporary_dir = Path(tempfile.mkdtemp(prefix="bitebuilder-ui-"))
        transcript_path = temporary_dir / transcript_name
        premiere_xml_path = temporary_dir / premiere_xml_name
        transcript_path.write_text(transcript_content, encoding="utf-8")
        premiere_xml_path.write_text(premiere_xml_content, encoding="utf-8")
    else:
        transcript_path = _required_path(payload, "transcript_path")
        premiere_xml_path = _required_path(payload, "premiere_xml_path")
        transcript_name = transcript_path.name

    output_text = _optional_text(payload.get("output_path"))
    saved_output_path: str | None = None

    if output_text:
        output_path = normalize_user_path(output_text)
        saved_output_path = str(output_path)
    else:
        if temporary_dir is None:
            temporary_dir = Path(tempfile.mkdtemp(prefix="bitebuilder-ui-"))
        output_path = temporary_dir / _suggest_output_name(transcript_name)

    request = GenerationRequest(
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
    return PreparedRequest(
        request=request,
        temporary_dir=temporary_dir,
        download_name=output_path.name,
        saved_output_path=saved_output_path,
    )


def request_from_payload(payload: dict) -> GenerationRequest:
    return prepare_request_from_payload(payload).request


def normalize_user_path(value: str) -> Path:
    text = _strip_wrapping_quotes(value.strip())
    if not text:
        raise ValueError("Path cannot be blank.")

    windows_match = WINDOWS_DRIVE_RE.match(text)
    if windows_match:
        drive = windows_match.group("drive").lower()
        rest = windows_match.group("rest").replace("\\", "/")
        return (Path("/mnt") / drive / Path(rest)).expanduser().resolve()

    unc_match = WSL_UNC_RE.match(text)
    if unc_match:
        rest = unc_match.group("rest").replace("\\", "/")
        return (Path("/") / Path(rest)).expanduser().resolve()

    return Path(text).expanduser().resolve()


def open_browser(url: str) -> bool:
    if _is_wsl():
        if _run_browser_command(["wslview", url]):
            return True
        if _run_browser_command(
            ["powershell.exe", "-NoProfile", "-Command", f"Start-Process '{url}'"]
        ):
            return True
        if _run_browser_command(["cmd.exe", "/c", "start", "", url]):
            return True
        return False

    try:
        return webbrowser.open(url)
    except Exception:
        return False


def _is_wsl() -> bool:
    return bool(os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"))


def _run_browser_command(command: list[str]) -> bool:
    executable = command[0]
    if executable.endswith(".exe") or executable == "cmd.exe":
        pass
    elif shutil.which(executable) is None:
        return False

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


def _required_path(payload: dict, key: str) -> Path:
    text = _optional_text(payload.get(key))
    if not text:
        raise ValueError(f"Missing required field: {key}")
    return normalize_user_path(text)


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


def _sanitize_filename(name: str) -> str:
    candidate = name.replace("\\", "/").split("/")[-1].strip()
    candidate = candidate or "upload"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", candidate)


def _strip_wrapping_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _suggest_output_name(transcript_name: str) -> str:
    base = re.sub(r"\.[^.]+$", "", transcript_name)
    base = base or "bitebuilder_selects"
    return f"{base}_bitebuilder.xml"


if __name__ == "__main__":
    main()
