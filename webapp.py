#!/usr/bin/env python3
"""
Local BiteBuilder web UI.
"""

import json
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Flask, current_app, jsonify, render_template, request, send_from_directory

from bitebuilder import (
    build_candidate_shortlist,
    BiteBuilderError,
    build_validation_error,
    parse_premiere_xml_safe,
    validate_brief,
    format_error_for_log,
    normalize_segment_index,
    normalize_segment_indexes,
    run_pipeline,
)
from generator.xmeml import generate_sequence
from generator.timecode import estimate_duration_seconds
from llm.ollama_client import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_THINKING_MODE,
    DEFAULT_TIMEOUT,
    generate_text,
    normalize_thinking_mode,
    resolve_host,
)
from llm.prompts import CHAT_SYSTEM_PROMPT, build_chat_prompt
from parser.transcript import format_for_llm, parse_transcript
from parser.transcript import TranscriptValidationError


ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "output" / "web"
PRESETS_ROOT = ROOT / "testing"
CHAT_TRANSCRIPT_LIMIT = 12000
JOB_STORE = {}
JOB_LOCK = threading.Lock()
SEGMENT_INDEX_PATTERN = re.compile(r"\[(\d+)\]")
TIMECODE_RANGE_PATTERN = re.compile(
    r"(\d{2}:\d{2}:\d{2}:\d{2})\s*-\s*(\d{2}:\d{2}:\d{2}:\d{2})"
)
TIMECODE_PATTERN = re.compile(r"\b\d{2}:\d{2}:\d{2}:\d{2}\b")
NARRATIVE_ARC_PATTERN = re.compile(r"narrative\s+arc[^:\n]*:\s*(.+)", re.IGNORECASE)
PROJECT_FILE_EXTENSIONS = (".bitebuilder-project.json", ".json")
APP_STEPS = (
    {
        "key": "intake",
        "label": "Upload",
        "path": "/",
    },
    {
        "key": "brief",
        "label": "Validate",
        "path": "/project/brief",
    },
    {
        "key": "chat",
        "label": "Preview/Confirm",
        "path": "/project/chat",
    },
    {
        "key": "generate",
        "label": "Generate",
        "path": "/project/generate",
    },
    {
        "key": "export",
        "label": "Download",
        "path": "/project/export",
    },
)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def validation_error_payload(
    code: str,
    error_type: str,
    message: str,
    expected_input_format: str,
    next_action: str,
    *,
    recoverable: bool = False,
    stage: str | None = None,
) -> dict:
    return build_validation_error(
        code=code,
        error_type=error_type,
        message=message,
        expected_input_format=expected_input_format,
        next_action=next_action,
        recoverable=recoverable,
        stage=stage,
    )


def transcript_timecode_error_payload(errors: list[dict], stage: str = "transcript") -> dict:
    return build_validation_error(
        code="TRANSCRIPT-TIMECODE-INVALID",
        error_type="invalid_transcript_content",
        message="Transcript timecodes are invalid or impossible.",
        expected_input_format="Timecoded transcript blocks as HH:MM:SS:FF - HH:MM:SS:FF in chronological order.",
        next_action=(
            "Fix transcript formatting issues at the listed lines and retry "
            "generation or chat."
        ),
        recoverable=True,
        stage=stage,
        details={"errors": errors},
    )


def validation_error_response(payload: dict, status: int = 400):
    current_app.logger.error("api_error=%s", format_error_for_log(payload))
    return jsonify({"status": "error", "error": payload}), status


def _source_value(source, key: str, default):
    if hasattr(source, key):
        return getattr(source, key)
    if hasattr(source, "to_dict"):
        try:
            source_dict = source.to_dict()
            if isinstance(source_dict, dict) and key in source_dict:
                return source_dict[key]
        except Exception:
            pass
    if isinstance(source, dict):
        return source.get(key, default)
    return default


def recoverable_generation_response(payload: dict, result: dict | None = None):
    response = {
        "status": payload.get("partial", {}).get("status") if isinstance(payload, dict) else "partial",
        "error": payload,
        "result": result,
    }
    return jsonify(response), 200


def preferred_model(models: list[str]) -> str:
    if DEFAULT_MODEL in models:
        return DEFAULT_MODEL
    return models[0] if models else DEFAULT_MODEL


def trim_transcript_for_chat(formatted_transcript: str) -> str:
    if len(formatted_transcript) <= CHAT_TRANSCRIPT_LIMIT:
        return formatted_transcript
    return (
        formatted_transcript[:CHAT_TRANSCRIPT_LIMIT]
        + "\n\n[Transcript preview truncated for chat. Generation still uses the full transcript.]"
    )


def load_preset_manifest(preset_id: str) -> dict:
    preset_path = PRESETS_ROOT / preset_id / "preset.json"
    if not preset_path.exists():
        raise FileNotFoundError(f"Preset '{preset_id}' was not found.")
    return json.loads(preset_path.read_text(encoding="utf-8"))


def resolve_repo_path(relative_path: str) -> Path:
    return (ROOT / relative_path).resolve()


def available_presets() -> list[dict]:
    presets = []
    if not PRESETS_ROOT.exists():
        return presets

    for preset_path in sorted(PRESETS_ROOT.glob("*/preset.json")):
        manifest = json.loads(preset_path.read_text(encoding="utf-8"))
        presets.append({
            "id": manifest["id"],
            "name": manifest["name"],
            "brief": manifest["brief"],
            "prd_path": manifest.get("prd_path", ""),
        })
    return presets


def build_page_context(
    page_key: str,
    page_title: str,
) -> dict:
    current_index = next(
        (index for index, step in enumerate(APP_STEPS) if step["key"] == page_key),
        0,
    )
    steps = []
    for index, step in enumerate(APP_STEPS):
        steps.append({
            **step,
            "active": step["key"] == page_key,
            "complete": index < current_index,
        })

    return {
        "steps": steps,
        "page_key": page_key,
        "page_title": page_title,
        "asset_version": max(
            int((ROOT / "static" / "app.css").stat().st_mtime_ns),
            int((ROOT / "static" / "app.js").stat().st_mtime_ns),
        ),
    }


def build_segment_lookup(segments) -> dict[tuple[str, str], dict]:
    lookup = {}
    for index, segment in enumerate(segments):
        lookup[(segment.tc_in, segment.tc_out)] = {
            "segment_index": index,
            "tc_in": segment.tc_in,
            "tc_out": segment.tc_out,
            "speaker": segment.speaker,
            "text": segment.text,
        }
    return lookup


def compact_text(text: str, limit: int = 180) -> str:
    cleaned = " ".join((text or "").strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def extract_reply_segment_indexes(reply: str, segments) -> list[int]:
    indexes = []
    seen = set()

    for match in SEGMENT_INDEX_PATTERN.finditer(reply or ""):
        index = normalize_segment_index(match.group(1))
        if index is not None and 0 <= index < len(segments) and index not in seen:
            seen.add(index)
            indexes.append(index)

    tc_lookup = {
        segment.tc_in: index
        for index, segment in enumerate(segments)
    }
    range_lookup = {
        (segment.tc_in, segment.tc_out): index
        for index, segment in enumerate(segments)
    }

    for match in TIMECODE_RANGE_PATTERN.finditer(reply or ""):
        index = range_lookup.get((match.group(1), match.group(2)))
        if index is not None and index not in seen:
            seen.add(index)
            indexes.append(index)

    for match in TIMECODE_PATTERN.finditer(reply or ""):
        index = tc_lookup.get(match.group(0))
        if index is not None and index not in seen:
            seen.add(index)
            indexes.append(index)

    return indexes


def infer_plan_speaker_balance(segment_indexes: list[int], segments) -> str:
    if not segment_indexes:
        return "balanced"
    speaker_ones = 0
    speaker_others = 0
    for index in segment_indexes:
        if not (0 <= index < len(segments)):
            continue
        if segments[index].speaker == "Speaker 1":
            speaker_ones += 1
        else:
            speaker_others += 1
    if speaker_others > speaker_ones:
        return "worker"
    if speaker_ones > 0 and speaker_others == 0:
        return "ceo"
    return "balanced"


def infer_narrative_arc(reply: str, segment_indexes: list[int]) -> str:
    match = NARRATIVE_ARC_PATTERN.search(reply or "")
    if match:
        return compact_text(match.group(1), limit=120)
    if len(segment_indexes) >= 4:
        return "Hook -> Pivot -> Proof -> Vision"
    if len(segment_indexes) == 3:
        return "Hook -> Proof -> Close"
    if len(segment_indexes) == 2:
        return "Hook -> Pivot"
    return ""


def build_copilot_plan(reply: str, segments, messages: list[dict] | None = None) -> dict:
    indexes = extract_reply_segment_indexes(reply, segments)
    opening_index = indexes[0] if indexes else None
    must_include = indexes[:4]
    latest_user_message = ""
    for message in reversed(messages or []):
        if (message.get("role") or "").strip().lower() == "user":
            latest_user_message = (message.get("content") or "").strip()
            if latest_user_message:
                break

    directive_parts = []
    if opening_index is not None and 0 <= opening_index < len(segments):
        segment = segments[opening_index]
        directive_parts.append(
            f"Open on [{opening_index}] {segment.tc_in} - {segment.tc_out}: {compact_text(segment.text, 140)}"
        )
    if len(must_include) > 1:
        other_indexes = must_include[1:]
        directive_parts.append(
            "Keep these beats in the cut: " + ", ".join(f"[{value}]" for value in other_indexes)
        )
    narrative_arc = infer_narrative_arc(reply, must_include)
    if narrative_arc:
        directive_parts.append(f"Narrative arc: {narrative_arc}")
    if latest_user_message:
        directive_parts.append(f"Honor latest user direction: {compact_text(latest_user_message, 160)}")

    return {
        "opening_segment_index": opening_index,
        "must_include_segment_indexes": must_include,
        "generation_directive": " ".join(part for part in directive_parts if part),
        "narrative_arc": narrative_arc,
        "speaker_balance": infer_plan_speaker_balance(must_include, segments),
        "rationale": compact_text(reply, 320),
        "source_segment_indexes": indexes,
    }


def enrich_option(option: dict, segments, candidate_shortlist: list[dict] | None = None) -> dict:
    segment_lookup = build_segment_lookup(segments)
    candidate_lookup = {
        item["segment_index"]: item
        for item in (candidate_shortlist or [])
    }
    selected_cuts = []
    for cut in option.get("cuts", []):
        base = segment_lookup.get((cut["tc_in"], cut["tc_out"]), {})
        segment_index = base.get("segment_index")
        candidate = candidate_lookup.get(segment_index, {})
        selected_cuts.append({
            "segment_index": segment_index,
            "tc_in": cut["tc_in"],
            "tc_out": cut["tc_out"],
            "speaker": cut.get("speaker") or base.get("speaker", ""),
            "purpose": cut.get("purpose", ""),
            "dialogue_summary": cut.get("dialogue_summary", ""),
            "text": base.get("text", ""),
            "reasons": candidate.get("reasons", []),
            "roles": candidate.get("roles", []),
            "score": candidate.get("score"),
        })
    return {
        "name": option.get("name", ""),
        "description": option.get("description", ""),
        "estimated_duration_seconds": option.get("estimated_duration_seconds"),
        "selected_cuts": selected_cuts,
    }


def serialize_generation_result(run_id: str, run_dir: Path, result: dict) -> dict:
    response_options = result.get("response", {}).get("options", [])
    candidate_shortlist = result.get("debug_artifacts", {}).get("candidate_shortlist", [])
    enriched_options = [
        enrich_option(option, result.get("segments", []), candidate_shortlist)
        for option in response_options
    ]

    files = []
    for index, item in enumerate(result["output_files"]):
        option_payload = enriched_options[index] if index < len(enriched_options) else {
            "selected_cuts": [],
            "name": item["name"],
            "description": item["description"],
            "estimated_duration_seconds": item["estimated_duration_seconds"],
        }
        files.append({
            "name": item["name"],
            "description": item["description"],
            "filename": item["filename"],
            "cut_count": item["cut_count"],
            "actual_duration_seconds": item["actual_duration_seconds"],
            "estimated_duration_seconds": item["estimated_duration_seconds"],
            "download_url": f"/api/output/{run_id}/{item['filename']}",
            "selected_cuts": option_payload["selected_cuts"],
        })

    debug_urls = {
        key: f"/api/output/{run_id}/{Path(path).name}"
        for key, path in (result.get("debug_files") or {}).items()
    }

    return {
        "run_id": run_id,
        "saved_dir": str(run_dir),
        "segment_count": result["segment_count"],
        "source": result["source"].to_dict(),
        "thinking_mode": result["thinking_mode"],
        "target_duration_range": result["target_duration_range"],
        "validation_errors": result["validation_errors"],
        "used_retry": result.get("used_retry", False),
        "selection_retry": result.get("selection_retry", {}),
        "debug_download_url": f"/api/output/{run_id}/_llm_response.json",
        "debug_files": debug_urls,
        "candidate_shortlist": candidate_shortlist,
        "options_detail": enriched_options,
        "files": files,
    }


def open_output_path(path: Path) -> str:
    candidates = [
        ["xdg-open", str(path)],
        ["open", str(path)],
        ["explorer.exe", str(path)],
    ]
    errors = []
    for command in candidates:
        try:
            subprocess.Popen(command)
            return f"Opened {path}"
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors) or f"Could not open {path}")


def read_text_if_exists(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def apply_variant_name(result: dict, run_dir: Path, variant_name: str) -> None:
    variant = (variant_name or "").strip()
    if not variant:
        return
    safe_variant = variant.replace(" ", "_").replace("/", "-")
    for item in result.get("output_files", []):
        original = run_dir / item["filename"]
        new_filename = f"{safe_variant}__{item['filename']}"
        updated = run_dir / new_filename
        if original.exists() and original != updated:
            original.rename(updated)
        item["filename"] = new_filename
        item["path"] = str(updated)
        item["name"] = f"{variant} | {item['name']}"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["OUTPUT_ROOT"] = OUTPUT_ROOT

    @app.get("/")
    def index():
        return render_template(
            "intake.html",
            **build_page_context(
                page_key="intake",
                page_title="Upload",
            ),
        )

    @app.get("/project/intake")
    def project_intake():
        return index()

    @app.get("/project/brief")
    def project_brief():
        return render_template(
            "context.html",
            **build_page_context(
                page_key="brief",
                page_title="Validate",
            ),
        )

    @app.get("/project/context")
    def project_context():
        return project_brief()

    @app.get("/project/chat")
    def project_chat():
        return render_template(
            "copilot.html",
            **build_page_context(
                page_key="chat",
                page_title="Preview/Confirm",
            ),
        )

    @app.get("/project/copilot")
    def project_copilot():
        return project_chat()

    @app.get("/project/generate")
    def project_generate():
        return render_template(
            "generate.html",
            **build_page_context(
                page_key="generate",
                page_title="Generate",
            ),
        )

    @app.get("/project/output")
    def project_output():
        return project_generate()

    @app.get("/project/export")
    def project_export():
        return render_template(
            "export.html",
            **build_page_context(
                page_key="export",
                page_title="Export",
            ),
        )

    @app.get("/project/logs")
    def project_logs():
        return render_template(
            "logs.html",
            **build_page_context(
                page_key="logs",
                page_title="Logs",
            ),
        )

    @app.get("/api/models")
    def get_models():
        try:
            active_host, models = resolve_host(model=DEFAULT_MODEL, preferred_host=DEFAULT_HOST)
        except Exception:
            active_host, models = DEFAULT_HOST, []
        return jsonify({
            "connected": bool(models),
            "models": models,
            "default_model": preferred_model(models),
            "default_thinking_mode": normalize_thinking_mode(DEFAULT_THINKING_MODE),
            "host": active_host,
        })

    @app.get("/api/presets")
    def get_presets():
        return jsonify({"presets": available_presets()})

    @app.get("/api/presets/<preset_id>")
    def get_preset(preset_id: str):
        try:
            manifest = load_preset_manifest(preset_id)
            transcript_path = resolve_repo_path(manifest["transcript_path"])
            xml_path = resolve_repo_path(manifest["xml_path"])
        except Exception as exc:
            return validation_error_response(build_validation_error(
                code="PRESET-UNAVAILABLE",
                error_type="missing_inputs",
                message="Preset could not be loaded.",
                expected_input_format="Preset id that exists and resolves to readable manifest files.",
                next_action="Choose a valid preset id and retry.",
                stage="preset",
                details={"cause": str(exc)},
            ), 404)

        return jsonify({
            "id": manifest["id"],
            "name": manifest["name"],
            "brief": manifest["brief"],
            "project_context": manifest["project_context"],
            "options": manifest["options"],
            "timeout": manifest["timeout"],
            "model": manifest.get("model", DEFAULT_MODEL),
            "thinking_mode": manifest.get("thinking_mode", DEFAULT_THINKING_MODE),
            "transcript_name": transcript_path.name,
            "xml_name": xml_path.name,
            "transcript_text": transcript_path.read_text(encoding="utf-8"),
            "xml_text": xml_path.read_text(encoding="utf-8"),
            "prd_path": manifest.get("prd_path", ""),
        })

    @app.get("/repo-file/<path:repo_path>")
    def repo_file(repo_path: str):
        file_path = resolve_repo_path(repo_path)
        if ROOT not in file_path.parents or not file_path.is_file():
            return validation_error_response(validation_error_payload(
                code="REPO-FILE-MISSING",
                error_type="missing_file",
                message="Requested repo file was not found.",
                expected_input_format="A repo_path that maps to a file under project root.",
                next_action="Use a valid file path from the repository list.",
                stage="file",
            ), 404)
        return send_from_directory(file_path.parent, file_path.name, as_attachment=False)

    @app.post("/api/chat")
    def chat():
        data = request.get_json(silent=True) or {}
        transcript_text = (data.get("transcript_text") or "").strip()
        if not transcript_text:
            return validation_error_response(validation_error_payload(
                code="CHAT-TRANSCRIPT-MISSING",
                error_type="missing_transcript_content",
                message="Transcript text is required for chat.",
                expected_input_format="Request JSON must include transcript_text.",
                next_action="Upload transcript text before sending chat request.",
                stage="transcript",
            ))

        try:
            segments = parse_transcript(transcript_text, strict=True)
        except TranscriptValidationError as exc:
            return validation_error_response(transcript_timecode_error_payload(exc.errors, "transcript"), 400)
        if not segments:
            return validation_error_response(validation_error_payload(
                code="CHAT-TRANSCRIPT-NO-SEGMENTS",
                error_type="unsupported_file_content",
                message="No transcript segments were found in the transcript.",
                expected_input_format="At least one HH:MM:SS:FF - HH:MM:SS:FF segment with text.",
                next_action="Use a transcript export with timecoded segments.",
                stage="transcript",
            ))

        model = (data.get("model") or DEFAULT_MODEL).strip()
        brief = (data.get("brief") or "").strip()
        project_context = (data.get("project_context") or "").strip()
        timeout = int(data.get("timeout") or DEFAULT_TIMEOUT)
        thinking_mode = normalize_thinking_mode(data.get("thinking_mode"))
        messages = data.get("messages") or []
        try:
            active_host, _ = resolve_host(model=model, preferred_host=DEFAULT_HOST)
        except Exception as exc:
            return validation_error_response(build_validation_error(
                code="CHAT-HOST-UNAVAILABLE",
                error_type="runtime_dependency",
                message="Could not connect to Ollama host.",
                expected_input_format="Reachable Ollama host/port with model access.",
                next_action="Start Ollama and check host port in /api/models.",
                stage="model",
                details={"cause": str(exc)},
            ))

        formatted_transcript = trim_transcript_for_chat(format_for_llm(segments))
        prompt = build_chat_prompt(
            formatted_transcript=formatted_transcript,
            brief=brief,
            project_context=project_context,
            messages=messages,
        )

        try:
            reply = generate_text(
                system_prompt=CHAT_SYSTEM_PROMPT,
                user_prompt=prompt,
                model=model,
                host=active_host,
                timeout=timeout,
                thinking_mode=thinking_mode,
            )
        except Exception as exc:
            return validation_error_response(build_validation_error(
                code="CHAT-LLM-FAILED",
                error_type="runtime_llm_error",
                message="Failed to generate chat guidance.",
                expected_input_format="Valid chat prompt and active model.",
                next_action="Verify model availability and retry.",
                stage="llm_generation",
                details={"cause": str(exc)},
            ))

        suggested_plan = build_copilot_plan(reply, segments, messages=messages)

        return jsonify({
            "reply": reply,
            "suggested_plan": suggested_plan,
            "segment_count": len(segments),
            "host": active_host,
        })

    @app.post("/api/parse-transcript")
    def parse_transcript_api():
        data = request.get_json(silent=True) or {}
        transcript_text = (data.get("transcript_text") or "").strip()
        xml_text = (data.get("xml_text") or "").strip()
        if not transcript_text:
            return validation_error_response(validation_error_payload(
                code="PARSE-TRANSCRIPT-MISSING",
                error_type="missing_transcript_content",
                message="Transcript text is required.",
                expected_input_format="Request JSON with transcript_text key.",
                next_action="Provide transcript text.",
                stage="transcript",
            ))

        timebase = 30
        ntsc = False
        if xml_text:
            try:
                source = parse_premiere_xml_safe(xml_text)
                timebase = _source_value(source, "timebase", timebase)
                ntsc = _source_value(source, "ntsc", ntsc)
            except Exception as exc:
                if isinstance(exc, BiteBuilderError):
                    return validation_error_response(exc.error, 400)
                return validation_error_response(validation_error_payload(
                    code="PARSE-XML-INVALID",
                    error_type="invalid_xml",
                    message="Could not parse Premiere XML.",
                    expected_input_format="Raw Premiere XML export text.",
                    next_action="Upload a full XML export from Premiere.",
                    stage="premiere_xml",
                    details={"cause": str(exc)},
                ))
        try:
            segments = parse_transcript(
                transcript_text,
                strict=True,
                timebase=timebase,
                ntsc=ntsc,
            )
        except TranscriptValidationError as exc:
            return validation_error_response(transcript_timecode_error_payload(exc.errors, "transcript"), 400)
        return jsonify({
            "segment_count": len(segments),
            "segments": [
                {
                    "segment_index": index,
                    "tc_in": segment.tc_in,
                    "tc_out": segment.tc_out,
                    "speaker": segment.speaker,
                    "text": segment.text,
                    "duration_seconds": estimate_duration_seconds(
                        segment.tc_in,
                        segment.tc_out,
                        timebase,
                        ntsc,
                    ),
                }
                for index, segment in enumerate(segments)
            ],
        })

    @app.post("/api/preview-shortlist")
    def preview_shortlist():
        data = request.get_json(silent=True) or {}
        transcript_text = (data.get("transcript_text") or "").strip()
        xml_text = (data.get("xml_text") or "").strip()
        brief = (data.get("brief") or "").strip()
        project_context = (data.get("project_context") or "").strip()
        messages = data.get("messages") or []
        accepted_plan = data.get("accepted_plan") or {}
        speaker_balance = (data.get("speaker_balance") or "balanced").strip()
        if not transcript_text or not xml_text:
            return validation_error_response(validation_error_payload(
                code="PREVIEW-INPUT-MISSING",
                error_type="missing_inputs",
                message="Transcript text and Premiere XML text are required.",
                expected_input_format="Both transcript_text and xml_text.",
                next_action="Fill both required fields before previewing candidates.",
                stage="input",
            ))
        try:
            validated_brief = validate_brief(brief)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)
        try:
            source = parse_premiere_xml_safe(xml_text)
        except Exception as exc:
            if isinstance(exc, BiteBuilderError):
                return validation_error_response(exc.error, 400)
            return validation_error_response(validation_error_payload(
                code="PREVIEW-XML-INVALID",
                error_type="invalid_xml",
                message="Could not parse Premiere XML.",
                expected_input_format="Valid Premiere XML export text.",
                next_action="Upload a fresh Premiere XML export.",
                stage="premiere_xml",
                details={"cause": str(exc)},
            ))
        try:
            timebase = _source_value(source, "timebase", 30)
            ntsc = _source_value(source, "ntsc", False)
            segments = parse_transcript(
                transcript_text,
                strict=True,
                timebase=timebase,
                ntsc=ntsc,
            )
        except TranscriptValidationError as exc:
            return validation_error_response(transcript_timecode_error_payload(exc.errors, "transcript"), 400)
        if not segments:
            return validation_error_response(validation_error_payload(
                code="PREVIEW-TRANSCRIPT-NO-SEGMENTS",
                error_type="unsupported_file_content",
                message="No transcript segments were found.",
                expected_input_format="At least one timecoded block with text.",
                next_action="Use a transcript export with timecoded blocks.",
                stage="transcript",
            ))
        shortlist = build_candidate_shortlist(
            segments=segments,
            source=source,
            brief=validated_brief,
            project_context=project_context,
            editorial_messages=messages,
            accepted_plan=accepted_plan,
            pinned_segment_indexes=data.get("pinned_segment_indexes"),
            banned_segment_indexes=data.get("banned_segment_indexes"),
            required_segment_indexes=data.get("required_segment_indexes"),
            locked_segment_indexes=data.get("locked_segment_indexes"),
            forced_open_segment_index=data.get("forced_open_segment_index"),
            speaker_balance=speaker_balance,
        )
        return jsonify({"candidates": shortlist, "count": len(shortlist)})

    @app.post("/api/render-xml")
    def render_xml():
        data = request.get_json(silent=True) or {}
        xml_text = (data.get("xml_text") or "").strip()
        transcript_text = (data.get("transcript_text") or "").strip()
        option_name = (data.get("name") or "Manual Edit").strip()
        cuts = data.get("cuts") or []
        if not xml_text or not cuts:
            return validation_error_response(validation_error_payload(
                code="MANUAL-INPUT-MISSING",
                error_type="missing_inputs",
                message="Premiere XML and at least one cut are required.",
                expected_input_format="xml_text + cuts array.",
                next_action="Provide both values and retry.",
                stage="input",
            ))

        try:
            segments = parse_transcript(transcript_text, strict=True) if transcript_text else []
        except TranscriptValidationError as exc:
            return validation_error_response(transcript_timecode_error_payload(exc.errors, "transcript"), 400)
        segment_lookup = build_segment_lookup(segments)
        try:
            source = parse_premiere_xml_safe(xml_text)
        except Exception as exc:
            if isinstance(exc, BiteBuilderError):
                return validation_error_response(exc.error, 400)
            return validation_error_response(build_validation_error(
                code="MANUAL-XML-INVALID",
                error_type="invalid_xml",
                message="Could not parse Premiere XML for manual render.",
                expected_input_format="Valid raw Premiere XML export.",
                next_action="Upload valid XML and retry.",
                stage="premiere_xml",
                details={"cause": str(exc)},
            ))

        normalized_cuts = []
        for item in cuts:
            if "tc_in" in item and "tc_out" in item:
                normalized_cuts.append({"tc_in": item["tc_in"], "tc_out": item["tc_out"]})
                continue
            segment_index = normalize_segment_index(item.get("segment_index"))
            if segment_index is None or segment_index >= len(segments):
                continue
            segment = segments[segment_index]
            normalized_cuts.append({"tc_in": segment.tc_in, "tc_out": segment.tc_out})

        if not normalized_cuts:
            return validation_error_response(validation_error_payload(
                code="MANUAL-NO-VALID-CUTS",
                error_type="invalid_cuts",
                message="No valid cuts were provided.",
                expected_input_format="At least one cut as tc_in/tc_out or valid segment_index.",
                next_action="Send corrected cut entries referencing parsed transcript segments.",
                stage="cuts",
            ))

        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        xml_str = generate_sequence(name=option_name, cuts=normalized_cuts, source=source)
        filename = f"{option_name.replace(' ', '_').replace('/', '-')}.xml"
        filepath = run_dir / filename
        filepath.write_text(xml_str, encoding="utf-8")
        cuts_detail = []
        for cut in normalized_cuts:
            base = segment_lookup.get((cut["tc_in"], cut["tc_out"]), {})
            cuts_detail.append({
                "tc_in": cut["tc_in"],
                "tc_out": cut["tc_out"],
                "speaker": base.get("speaker", ""),
                "text": base.get("text", ""),
            })

        payload = {
            "run_id": run_id,
            "saved_dir": str(run_dir),
            "files": [{
                "name": option_name,
                "filename": filename,
                "download_url": f"/api/output/{run_id}/{filename}",
                "selected_cuts": cuts_detail,
            }],
            "debug_files": {},
            "validation_errors": [],
        }
        (run_dir / "_manual_selection.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return jsonify(payload)

    @app.post("/api/open-output-folder")
    def open_output_folder():
        data = request.get_json(silent=True) or {}
        run_id = (data.get("run_id") or "").strip()
        saved_dir = (data.get("saved_dir") or "").strip()
        target = None
        if run_id:
            target = app.config["OUTPUT_ROOT"] / run_id
        elif saved_dir:
            target = Path(saved_dir)
        if not target:
            return validation_error_response(validation_error_payload(
                code="OPEN-OUTPUT-MISSING",
                error_type="missing_inputs",
                message="run_id or saved_dir is required.",
                expected_input_format="Either run_id (queued response) or saved_dir path.",
                next_action="Pass run_id or absolute saved_dir from generation responses.",
                stage="output",
            ))
        try:
            message = open_output_path(target.resolve())
        except Exception as exc:
            return validation_error_response(build_validation_error(
                code="OPEN-OUTPUT-FAILED",
                error_type="runtime_output_error",
                message="Could not open output folder.",
                expected_input_format="Writable output directory path.",
                next_action="Confirm folder exists and OS permissions allow opening.",
                stage="output",
                details={"cause": str(exc)},
            ))
        return jsonify({"message": message})

    @app.get("/api/session-log/<run_id>")
    def session_log(run_id: str):
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        log_path = run_dir / "_generation_log.json"
        payload = {
            "run_id": run_id,
            "saved_dir": str(run_dir),
            "generation_log": json.loads(read_text_if_exists(log_path) or "{}"),
            "llm_response": json.loads(read_text_if_exists(run_dir / "_llm_response.json") or "{}"),
            "prompt_text": read_text_if_exists(run_dir / "_generation_prompt.txt"),
            "editorial_direction": read_text_if_exists(run_dir / "_editorial_direction.txt"),
            "candidate_shortlist": json.loads(read_text_if_exists(run_dir / "_candidate_shortlist.json") or "[]"),
        }
        return jsonify(payload)

    @app.post("/api/generate")
    def generate():
        data = request.get_json(silent=True) or {}
        transcript_text = (data.get("transcript_text") or "").strip()
        xml_text = (data.get("xml_text") or "").strip()
        brief = (data.get("brief") or "").strip()
        project_context = (data.get("project_context") or "").strip()
        model = (data.get("model") or DEFAULT_MODEL).strip()
        options = int(data.get("options") or 3)
        timeout = int(data.get("timeout") or DEFAULT_TIMEOUT)
        thinking_mode = normalize_thinking_mode(data.get("thinking_mode"))
        messages = data.get("messages") or []
        accepted_plan = data.get("accepted_plan") or {}
        variant_name = (data.get("variant_name") or "").strip()
        pinned_segment_indexes = normalize_segment_indexes(data.get("pinned_segment_indexes"))
        banned_segment_indexes = normalize_segment_indexes(data.get("banned_segment_indexes"))
        required_segment_indexes = normalize_segment_indexes(data.get("required_segment_indexes"))
        locked_segment_indexes = normalize_segment_indexes(data.get("locked_segment_indexes"))
        forced_open_segment_index = normalize_segment_index(data.get("forced_open_segment_index"))
        speaker_balance = (data.get("speaker_balance") or "balanced").strip()

        if not transcript_text:
            return validation_error_response(validation_error_payload(
                code="GENERATE-TRANSCRIPT-MISSING",
                error_type="missing_transcript_content",
                message="Transcript text is required.",
                expected_input_format="Transcript key in request JSON.",
                next_action="Provide transcript content before generation.",
                stage="transcript",
            ))
        if not xml_text:
            return validation_error_response(validation_error_payload(
                code="GENERATE-XML-MISSING",
                error_type="invalid_xml",
                message="Premiere XML text is required.",
                expected_input_format="xml_text key in request JSON.",
                next_action="Provide Premiere XML content before generation.",
                stage="premiere_xml",
            ))
        try:
            validated_brief = validate_brief(brief)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)

        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = run_pipeline(
                transcript_text=transcript_text,
                xml_text=xml_text,
                brief=validated_brief,
                options=options,
                model=model,
                output_dir=str(run_dir),
                host=DEFAULT_HOST,
                timeout=timeout,
                project_context=project_context,
                editorial_messages=messages,
                accepted_plan=accepted_plan,
                pinned_segment_indexes=pinned_segment_indexes,
                banned_segment_indexes=banned_segment_indexes,
                required_segment_indexes=required_segment_indexes,
                locked_segment_indexes=locked_segment_indexes,
                forced_open_segment_index=forced_open_segment_index,
                speaker_balance=speaker_balance,
                thinking_mode=thinking_mode,
            )
        except Exception as exc:
            if isinstance(exc, BiteBuilderError) and exc.error.get("partial"):
                return recoverable_generation_response(exc.error)
            if isinstance(exc, BiteBuilderError):
                app.logger.error("generation_failed=%s", format_error_for_log(exc.error))
                return validation_error_response(exc.error)
            return validation_error_response(validation_error_payload(
                code="GENERATE-FAILED",
                error_type="runtime_failure",
                message="Generation failed.",
                expected_input_format="Valid transcript, XML, brief, and model connection.",
                next_action="Retry after fixing input errors shown above.",
                stage="generation",
                details={"cause": str(exc)},
            ))

        apply_variant_name(result, run_dir, variant_name)
        return jsonify(serialize_generation_result(run_id, run_dir, result))

    @app.post("/api/generate-jobs")
    def generate_jobs():
        data = request.get_json(silent=True) or {}
        transcript_text = (data.get("transcript_text") or "").strip()
        xml_text = (data.get("xml_text") or "").strip()
        brief = (data.get("brief") or "").strip()
        project_context = (data.get("project_context") or "").strip()
        model = (data.get("model") or DEFAULT_MODEL).strip()
        options = int(data.get("options") or 3)
        timeout = int(data.get("timeout") or DEFAULT_TIMEOUT)
        thinking_mode = normalize_thinking_mode(data.get("thinking_mode"))
        messages = data.get("messages") or []
        accepted_plan = data.get("accepted_plan") or {}
        variant_name = (data.get("variant_name") or "").strip()
        pinned_segment_indexes = normalize_segment_indexes(data.get("pinned_segment_indexes"))
        banned_segment_indexes = normalize_segment_indexes(data.get("banned_segment_indexes"))
        required_segment_indexes = normalize_segment_indexes(data.get("required_segment_indexes"))
        locked_segment_indexes = normalize_segment_indexes(data.get("locked_segment_indexes"))
        forced_open_segment_index = normalize_segment_index(data.get("forced_open_segment_index"))
        speaker_balance = (data.get("speaker_balance") or "balanced").strip()

        if not transcript_text or not xml_text or not brief:
            return validation_error_response(validation_error_payload(
                code="GENERATE-JOB-INPUT-MISSING",
                error_type="missing_inputs",
                message="Transcript text, Premiere XML, and a brief are required.",
                expected_input_format="transcript_text, xml_text, brief in JSON request.",
                next_action="Supply all required values before starting job.",
                stage="input",
            ))
        try:
            validated_brief = validate_brief(brief)
        except BiteBuilderError as exc:
            return validation_error_response(exc.error)

        job_id = uuid4().hex
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        def update_job(message: str, status: str | None = None, payload: dict | None = None):
            with JOB_LOCK:
                job = JOB_STORE[job_id]
                job["logs"].append({"timestamp": now_iso(), "message": message})
                if status:
                    job["status"] = status
                if payload is not None:
                    job["result"] = payload

        with JOB_LOCK:
            JOB_STORE[job_id] = {
                "job_id": job_id,
                "run_id": run_id,
                "status": "queued",
                "logs": [{"timestamp": now_iso(), "message": "Queued generation job."}],
                "result": None,
                "error": None,
            }

        def worker():
            try:
                update_job("Starting generation.", status="running")
                result = run_pipeline(
                    transcript_text=transcript_text,
                    xml_text=xml_text,
                    brief=validated_brief,
                    options=options,
                    model=model,
                    output_dir=str(run_dir),
                    host=DEFAULT_HOST,
                    timeout=timeout,
                    project_context=project_context,
                    editorial_messages=messages,
                    accepted_plan=accepted_plan,
                    pinned_segment_indexes=pinned_segment_indexes,
                    banned_segment_indexes=banned_segment_indexes,
                    required_segment_indexes=required_segment_indexes,
                    locked_segment_indexes=locked_segment_indexes,
                    forced_open_segment_index=forced_open_segment_index,
                    speaker_balance=speaker_balance,
                    thinking_mode=thinking_mode,
                    progress_callback=lambda message: update_job(message),
                )
                apply_variant_name(result, run_dir, variant_name)
                payload = serialize_generation_result(run_id, run_dir, result)
                update_job("Generation complete.", status="completed", payload=payload)
            except Exception as exc:
                with JOB_LOCK:
                    if isinstance(exc, BiteBuilderError) and exc.error.get("partial"):
                        JOB_STORE[job_id]["status"] = "partial"
                        JOB_STORE[job_id]["error"] = exc.error
                        JOB_STORE[job_id]["logs"].append({
                            "timestamp": now_iso(),
                            "message": exc.error.get("message"),
                        })
                        return
                with JOB_LOCK:
                    JOB_STORE[job_id]["status"] = "error"
                    if isinstance(exc, BiteBuilderError):
                        error = exc.error
                        app.logger.error("job_error=%s", format_error_for_log(error))
                        JOB_STORE[job_id]["error"] = error
                        JOB_STORE[job_id]["logs"].append({"timestamp": now_iso(), "message": error.get("message", str(exc))})
                    else:
                        JOB_STORE[job_id]["error"] = str(exc)
                        JOB_STORE[job_id]["logs"].append({"timestamp": now_iso(), "message": str(exc)})

        threading.Thread(target=worker, daemon=True).start()
        return jsonify({"job_id": job_id, "run_id": run_id, "status": "queued"})

    @app.get("/api/jobs/<job_id>")
    def job_status(job_id: str):
        with JOB_LOCK:
            job = JOB_STORE.get(job_id)
        if not job:
            return validation_error_response(validation_error_payload(
                code="JOB-NOT-FOUND",
                error_type="missing_resource",
                message="Job not found.",
                expected_input_format="A valid job_id returned by /api/generate-jobs.",
                next_action="Request status for an existing job_id.",
                stage="job_status",
            ), 404)
        payload = {
            "job_id": job["job_id"],
            "run_id": job["run_id"],
            "status": job["status"],
            "logs": job["logs"],
            "error": job["error"],
        }
        if job["status"] == "completed":
            payload["result"] = job["result"]
        return jsonify(payload)

    @app.get("/api/output/<run_id>/<path:filename>")
    def download_output(run_id: str, filename: str):
        run_dir = app.config["OUTPUT_ROOT"] / run_id
        return send_from_directory(run_dir, filename, as_attachment=True)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
