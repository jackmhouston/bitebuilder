#!/usr/bin/env python3
"""
BiteBuilder v1 — AI-powered soundbite selector for video editors.

Reads an interview transcript + Premiere Pro XML export, sends them to a local
LLM (Ollama) with a creative brief, and generates importable Premiere XML
sequences with the AI's selected soundbites.

Usage:
    python bitebuilder.py \
        --transcript "transcript.txt" \
        --xml "sequence.xml" \
        --brief "45 second sizzle, start relatable, end inspiring"
"""

import argparse
import logging
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

from parser.transcript import parse_transcript, get_valid_timecodes
from parser.transcript import TranscriptValidationError
from parser.premiere_xml import parse_premiere_xml_string
from generator.xmeml import generate_sequence
from generator.timecode import estimate_duration_seconds
from llm.prompts import (
    SYSTEM_PROMPT,
    EDITORIAL_DIRECTION_SYSTEM_PROMPT,
    build_editorial_direction_prompt,
    build_user_prompt,
    validate_llm_response,
    build_retry_prompt,
)
from llm.ollama_client import (
    DEFAULT_HOST,
    DEFAULT_MODEL,
    DEFAULT_THINKING_MODE,
    DEFAULT_TIMEOUT,
    resolve_host,
    generate as ollama_generate,
    generate_text,
    normalize_thinking_mode,
)


def build_validation_error(
    code: str,
    error_type: str,
    message: str,
    expected_input_format: str,
    next_action: str,
    *,
    recoverable: bool = False,
    stage: str | None = None,
    details: dict | None = None,
) -> dict:
    """Build a structured, user-facing error payload."""
    return {
        "code": code,
        "type": error_type,
        "message": message,
        "expected_input_format": expected_input_format,
        "next_action": next_action,
        "recoverable": recoverable,
        "stage": stage or "validation",
        "details": details or {},
    }


def build_transcript_timecode_error(errors: list[dict]) -> BiteBuilderError:
    """Build a deterministic transcript parsing error payload."""
    return BiteBuilderError(build_validation_error(
        code="TRANSCRIPT-TIMECODE-INVALID",
        error_type="invalid_transcript_content",
        message="Transcript timecodes are invalid or impossible.",
        expected_input_format="Timecoded transcript blocks as HH:MM:SS:FF - HH:MM:SS:FF in chronological order.",
        next_action=(
            "Fix each line-level transcript issue and retry. "
            "Use only valid frame numbers and ensure each segment has non-empty text."
        ),
        stage="transcript",
        recoverable=True,
        details={"errors": errors},
    ))


class BiteBuilderError(Exception):
    """Error with structured context that can be surfaced consistently in CLI and web."""

    def __init__(self, payload: dict) -> None:
        super().__init__(payload.get("message"))
        self.error = payload


def format_error_for_log(error: dict) -> str:
    """Return stable machine-readable log payload."""
    return json.dumps(error, sort_keys=True, separators=(",", ":"))


def validate_brief(brief: str) -> str:
    """Validate and normalize the creative brief."""
    normalized = (brief or "").strip()
    if not normalized:
        raise BiteBuilderError(build_validation_error(
            code="BRIEF-MISSING",
            error_type="missing_brief",
            message="Creative brief is required.",
            expected_input_format="A concise plain-text brief (at least 3 words).",
            next_action="Add a brief that describes duration goals and narrative style.",
            stage="brief",
        ))
    if len(normalized) < 8 or len(re.findall(r"[A-Za-z]", normalized)) < 3:
        raise BiteBuilderError(build_validation_error(
            code="BRIEF-MALFORMED",
            error_type="malformed_brief",
            message="Creative brief is too short or missing readable content.",
            expected_input_format="Natural language brief, for example: "
            "'45 second proof of concept, open with objection, end with a call to action'.",
            next_action="Rewrite the brief with at least a short sentence describing desired output.",
            stage="brief",
        ))
    return normalized


def parse_transcript_file_bytes(raw_text: str) -> str:
    """Return raw text or raise a stable structured error."""
    if not raw_text.strip():
        raise BiteBuilderError(build_validation_error(
            code="TRANSCRIPT-EMPTY",
            error_type="unsupported_file_content",
            message="Transcript content is empty.",
            expected_input_format="Timecoded transcript blocks with speaker and dialogue text.",
            next_action="Provide transcript text including HH:MM:SS:FF ranges and spoken lines.",
            stage="transcript",
        ))
    return raw_text


def read_text_file(path: str) -> str:
    """Read and validate a transcript or XML text file."""
    if not path:
        raise BiteBuilderError(build_validation_error(
            code="INPUT-MISSING",
            error_type="missing_input",
            message="Missing required input path.",
            expected_input_format="A valid path to a text file.",
            next_action="Pass a valid --transcript / --xml path.",
            stage="input",
        ))
    if not os.path.exists(path):
        raise BiteBuilderError(build_validation_error(
            code="INPUT-NOT-FOUND",
            error_type="missing_transcript_file",
            message=f"Input file not found: {path}",
            expected_input_format="Path to an existing UTF-8 file.",
            next_action="Verify the path is correct and re-run.",
            stage="input",
        ))
    if not os.path.isfile(path):
        raise BiteBuilderError(build_validation_error(
            code="INPUT-NOT-FILE",
            error_type="invalid_transcript_file",
            message=f"Input path is not a file: {path}",
            expected_input_format="A filesystem path to a UTF-8 text or XML file.",
            next_action="Point to a file, not a folder.",
            stage="input",
        ))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return parse_transcript_file_bytes(handle.read())
    except UnicodeDecodeError as exc:
        raise BiteBuilderError(build_validation_error(
            code="INPUT-ENCODING",
            error_type="unsupported_file_content",
            message=f"Could not decode file as UTF-8: {path}",
            expected_input_format="UTF-8 encoded text file.",
            next_action="Save or export as UTF-8 and retry.",
            stage="input",
            recoverable=True,
            details={"cause": str(exc)},
        ))
    except OSError as exc:
        raise BiteBuilderError(build_validation_error(
            code="INPUT-IOERROR",
            error_type="missing_transcript_file",
            message=f"Cannot open file: {path}",
            expected_input_format="Readable text/XML path.",
            next_action="Check file permissions and retry.",
            stage="input",
            details={"cause": str(exc)},
        ))


def parse_premiere_xml_safe(xml_text: str):
    """Parse Premiere XML with stable user-facing error mapping."""
    try:
        return parse_premiere_xml_string(xml_text)
    except Exception as exc:
        if isinstance(exc, ET.ParseError):
            raise BiteBuilderError(build_validation_error(
                code="XML-MALFORMED",
                error_type="invalid_xml",
                message="Invalid Premiere XML content.",
                expected_input_format="Raw Premiere XML export text that starts with <xmeml>.",
                next_action="Export XML from Premiere again and ensure it is copied in full.",
                stage="premiere_xml",
                recoverable=True,
                details={"cause": str(exc)},
            ))
        raise BiteBuilderError(build_validation_error(
            code="XML-UNSUPPORTED",
            error_type="unsupported_file_content",
            message="XML structure is unsupported or missing required Premiere metadata.",
            expected_input_format="Valid Premiere XML with <file><pathurl> plus sequence metadata.",
            next_action="Export an XMEML v4 XML sequence directly from Premiere.",
            stage="premiere_xml",
            recoverable=True,
            details={"cause": str(exc)},
        ))


DURATION_RANGE_PATTERN = re.compile(
    r'(?P<minimum>:?\d{1,2})\s*(?:to|-|–|—)\s*(?:a\s*)?(?P<maximum>:?\d{1,2})\s*(?:second|seconds|sec|secs)\b',
    re.IGNORECASE,
)
SINGLE_DURATION_PATTERN = re.compile(
    r'(?<!\d):?(?P<seconds>\d{1,2})\s*(?:second|seconds|sec|secs)\b',
    re.IGNORECASE,
)
INDEX_PATTERN = re.compile(r"-?\d+")

STRIKING_PHRASE_WEIGHTS = {
    "counterintuitive": 7,
    "die or fall off a cliff": 8,
    "rickety old system": 8,
    "tip of the iceberg": 9,
    "wave of the future": 5,
    "no brainer": 5,
    "rude awakening": 6,
    "peel back the onion": 7,
    "insatiable appetite": 5,
}
HOOKY_TERMS = (
    "hook", "hooky", "opening", "open", "start", "surprising", "unexpected",
    "off-center", "off center", "weird", "whacky", "wacky", "contrarian",
)
INNOVATION_TERMS = (
    "innovation", "innovative", "future", "efficiency", "technology", "tech",
    "battery", "microgrid", "virtual power plant", "distributed", "clean energy",
)
ACCESSIBLE_TERMS = ("accessible", "smart", "intelligent", "clear", "simple", "understandable")
FINANCE_TERMS = ("roi", "finance", "financial", "bill", "utility", "rate", "rates", "save money", "savings")
TECH_WORKER_TERMS = ("technical worker", "technician", "installer", "field", "crew", "worker")
FILLER_PHRASES = (
    "back to what we were discussing earlier",
    "okay. so here",
    "oh yeah",
    "so meaning",
)


def collect_editorial_text(
    brief: str = "",
    project_context: str = "",
    editorial_direction: str = "",
    editorial_messages: list[dict] | None = None,
    accepted_plan: dict | None = None,
) -> str:
    """Combine editable user-facing direction into one searchable text block."""
    parts = [brief, project_context, editorial_direction]
    for message in editorial_messages or []:
        role = (message.get("role") or "").strip().lower()
        content = (message.get("content") or "").strip()
        if role == "user" and content:
            parts.append(content)
    accepted_plan = accepted_plan or {}
    for value in [
        accepted_plan.get("generation_directive", ""),
        accepted_plan.get("narrative_arc", ""),
        accepted_plan.get("rationale", ""),
    ]:
        if value:
            parts.append(value)
    return " ".join(part for part in parts if part).lower()


def normalize_accepted_plan(accepted_plan: dict | None) -> dict:
    """Normalize accepted copilot plan payloads into a stable shape."""
    accepted_plan = accepted_plan or {}
    return {
        "opening_segment_index": normalize_segment_index(accepted_plan.get("opening_segment_index")),
        "must_include_segment_indexes": normalize_segment_indexes(accepted_plan.get("must_include_segment_indexes")),
        "generation_directive": (accepted_plan.get("generation_directive") or "").strip(),
        "narrative_arc": (accepted_plan.get("narrative_arc") or "").strip(),
        "speaker_balance": (accepted_plan.get("speaker_balance") or "").strip(),
        "rationale": (accepted_plan.get("rationale") or "").strip(),
    }


def format_accepted_plan_text(accepted_plan: dict | None) -> str:
    """Format accepted plan decisions into a prompt-friendly block."""
    accepted_plan = normalize_accepted_plan(accepted_plan)
    lines = []
    if accepted_plan["opening_segment_index"] is not None:
        lines.append(f"- Approved opening segment_index: {accepted_plan['opening_segment_index']}")
    if accepted_plan["must_include_segment_indexes"]:
        indexes = ", ".join(str(value) for value in accepted_plan["must_include_segment_indexes"])
        lines.append(f"- Must include segment_indexes: {indexes}")
    if accepted_plan["speaker_balance"]:
        lines.append(f"- Preferred speaker balance: {accepted_plan['speaker_balance']}")
    if accepted_plan["narrative_arc"]:
        lines.append(f"- Approved narrative arc: {accepted_plan['narrative_arc']}")
    if accepted_plan["generation_directive"]:
        lines.append(f"- Generation directive: {accepted_plan['generation_directive']}")
    if accepted_plan["rationale"]:
        lines.append(f"- Rationale: {accepted_plan['rationale']}")
    return "\n".join(lines)


def infer_segment_roles(text: str, duration_seconds: float) -> list[str]:
    """Infer rough editorial roles from the segment text."""
    lower = text.lower()
    roles = []

    if (
        any(phrase in lower for phrase in STRIKING_PHRASE_WEIGHTS)
        or "?" in text
        or duration_seconds <= 8
    ):
        roles.extend(["HOOK", "REFRAME"])

    if (
        "%" in text
        or re.search(r"\b\d+(?:\.\d+)?\b", text)
        or any(term in lower for term in ("installed", "enhanced", "efficiency", "reviews", "projects", "years"))
    ):
        roles.append("PROOF")

    if any(term in lower for term in ("solution", "goal should", "energy independence", "generate their own power", "microgrid", "operate independently")):
        roles.extend(["SOLUTION", "CONTEXT"])

    if any(term in lower for term in ("future", "going away anytime soon", "no brainer", "wave of the future")):
        roles.extend(["VISION", "BUTTON", "CLOSE"])

    if any(term in lower for term in ("because", "the reason", "again", "but")):
        roles.append("PIVOT")

    if not roles:
        roles.append("CONTEXT")

    ordered = []
    for role in roles:
        if role not in ordered:
            ordered.append(role)
    return ordered


def score_segment(segment, duration_seconds: float, editorial_text: str) -> tuple[float, list[str], list[str]]:
    """Score a segment against the current brief and chat-derived direction."""
    lower = segment.text.lower()
    roles = infer_segment_roles(segment.text, duration_seconds)
    score = 0.0
    reasons = []

    if 4 <= duration_seconds <= 18:
        score += 3
        reasons.append("concise")
    elif duration_seconds <= 24:
        score += 1
    else:
        score -= 4
        reasons.append("long")

    if "HOOK" in roles:
        score += 2
    if "PROOF" in roles:
        score += 2
    if "VISION" in roles or "BUTTON" in roles:
        score += 1

    if "%" in segment.text or re.search(r"\b\d+(?:\.\d+)?\b", segment.text):
        score += 2
        reasons.append("specific numbers")

    striking_hits = [phrase for phrase in STRIKING_PHRASE_WEIGHTS if phrase in lower]
    for phrase in striking_hits:
        score += STRIKING_PHRASE_WEIGHTS[phrase]
    if striking_hits:
        reasons.append("striking phrasing")

    if any(phrase in lower for phrase in FILLER_PHRASES):
        score -= 6
        reasons.append("filler")

    wants_hook = any(term in editorial_text for term in HOOKY_TERMS)
    wants_weird = any(term in editorial_text for term in ("whacky", "wacky", "weird", "off-center", "off center", "surprising", "unexpected", "contrarian"))
    wants_innovation = any(term in editorial_text for term in INNOVATION_TERMS)
    wants_accessible = any(term in editorial_text for term in ACCESSIBLE_TERMS)
    wants_finance = any(term in editorial_text for term in FINANCE_TERMS)
    wants_technical_worker = any(term in editorial_text for term in TECH_WORKER_TERMS)

    if wants_hook and ("HOOK" in roles or "REFRAME" in roles):
        score += 4
        reasons.append("hooky opening")
    if wants_weird:
        if striking_hits or "REFRAME" in roles:
            score += 5
            reasons.append("off-center tone")
        if duration_seconds <= 12:
            score += 2
    if wants_innovation:
        innovation_hits = sum(lower.count(term) for term in INNOVATION_TERMS if term in lower)
        if innovation_hits:
            score += 2 + innovation_hits
            reasons.append("innovation angle")
    if wants_accessible:
        if 6 <= duration_seconds <= 16:
            score += 2
        if "PROOF" in roles or "SOLUTION" in roles:
            score += 2
            reasons.append("accessible explanation")
    if wants_finance and any(term in lower for term in FINANCE_TERMS):
        score += 4
        reasons.append("finance framing")
    if wants_technical_worker and segment.speaker != "Speaker 1":
        score += 4
        reasons.append("alternate speaker")

    return score, reasons, roles


def build_candidate_shortlist(
    segments,
    source,
    brief: str,
    project_context: str = "",
    editorial_messages: list[dict] | None = None,
    editorial_direction: str = "",
    pinned_segment_indexes: list[int] | None = None,
    banned_segment_indexes: list[int] | None = None,
    required_segment_indexes: list[int] | None = None,
    locked_segment_indexes: list[int] | None = None,
    forced_open_segment_index: int | None = None,
    speaker_balance: str = "balanced",
    accepted_plan: dict | None = None,
    limit: int = 28,
) -> list[dict]:
    """Build a diverse, style-aware candidate pool before asking the model to assemble an edit."""
    pinned_segment_indexes = set(normalize_segment_indexes(pinned_segment_indexes))
    banned_segment_indexes = set(normalize_segment_indexes(banned_segment_indexes))
    required_segment_indexes = set(normalize_segment_indexes(required_segment_indexes))
    locked_segment_indexes = set(normalize_segment_indexes(locked_segment_indexes))
    forced_open_segment_index = normalize_segment_index(forced_open_segment_index)
    editorial_text = collect_editorial_text(
        brief=brief,
        project_context=project_context,
        editorial_direction=editorial_direction,
        editorial_messages=editorial_messages,
        accepted_plan=accepted_plan,
    )
    candidates = []
    for index, segment in enumerate(segments):
        if index in banned_segment_indexes:
            continue
        duration_seconds = estimate_duration_seconds(segment.tc_in, segment.tc_out, source.timebase, source.ntsc)
        score, reasons, roles = score_segment(segment, duration_seconds, editorial_text)
        if index in pinned_segment_indexes:
            score += 12
            reasons.append("pinned")
        if index in required_segment_indexes:
            score += 14
            reasons.append("must include")
        if index in locked_segment_indexes:
            score += 16
            reasons.append("locked")
        if forced_open_segment_index is not None and index == forced_open_segment_index:
            score += 24
            if "HOOK" not in roles:
                roles = ["HOOK", *roles]
            reasons.append("forced opening")

        if speaker_balance == "ceo":
            if segment.speaker == "Speaker 1":
                score += 4
                reasons.append("speaker bias: ceo")
            else:
                score -= 2
        elif speaker_balance == "worker":
            if segment.speaker != "Speaker 1":
                score += 5
                reasons.append("speaker bias: worker")
            else:
                score -= 2
        elif speaker_balance == "balanced" and segment.speaker != "Speaker 1":
            score += 1

        candidates.append({
            "segment_index": index,
            "tc_in": segment.tc_in,
            "tc_out": segment.tc_out,
            "speaker": segment.speaker,
            "text": segment.text,
            "duration_seconds": duration_seconds,
            "score": round(score, 2),
            "roles": roles,
            "reasons": reasons,
        })

    ranked = sorted(
        candidates,
        key=lambda item: (item["score"], -min(item["duration_seconds"], 18)),
        reverse=True,
    )

    shortlist = []
    seen_indexes = set()

    def add_bucket(role_names: tuple[str, ...], bucket_limit: int):
        added = 0
        for candidate in ranked:
            if candidate["segment_index"] in seen_indexes:
                continue
            if not any(role in candidate["roles"] for role in role_names):
                continue
            shortlist.append(candidate)
            seen_indexes.add(candidate["segment_index"])
            added += 1
            if len(shortlist) >= limit or added >= bucket_limit:
                return

    add_bucket(("HOOK", "REFRAME"), 8)
    add_bucket(("PROOF",), 10)
    add_bucket(("SOLUTION", "CONTEXT", "PIVOT"), 8)
    add_bucket(("VISION", "BUTTON", "CLOSE"), 6)

    for candidate in ranked:
        if len(shortlist) >= limit:
            break
        if candidate["segment_index"] in seen_indexes:
            continue
        shortlist.append(candidate)
        seen_indexes.add(candidate["segment_index"])

    return shortlist


def format_candidate_pool(candidates: list[dict]) -> str:
    """Format shortlisted candidates for the model prompt."""
    lines = []
    for candidate in candidates:
        roles = ",".join(candidate["roles"])
        reason_text = ", ".join(candidate["reasons"][:3]) if candidate["reasons"] else "general fit"
        lines.append(
            f"[{candidate['segment_index']}] {candidate['tc_in']} - {candidate['tc_out']} | "
            f"{candidate['speaker']} | {candidate['duration_seconds']:.1f}s | roles={roles} | "
            f"score={candidate['score']:.1f} | {reason_text}\n"
            f"    \"{candidate['text']}\""
        )
    return "\n\n".join(lines)


def collect_candidate_validation_errors(
    response: dict,
    valid_candidate_indexes: set[int],
    expected_options: int,
) -> list[str]:
    """Validate that the model picked real candidate indexes."""
    errors = []

    if "options" not in response:
        return ["Missing 'options' key in response"]
    if not isinstance(response["options"], list) or not response["options"]:
        return ["Response must include a non-empty 'options' list"]
    if len(response["options"]) != expected_options:
        errors.append(f"Expected exactly {expected_options} options, got {len(response['options'])}")

    for opt_index, option in enumerate(response["options"], start=1):
        cuts = option.get("cuts")
        alt_indexes = option.get("segment_indexes") or option.get("segment_indices")
        if not cuts and not alt_indexes:
            errors.append(f"Option {opt_index}: missing cuts")
            continue

        if cuts:
            for cut_index, cut in enumerate(cuts, start=1):
                if "tc_in" in cut and "tc_out" in cut:
                    continue
                segment_index = normalize_segment_index(cut.get("segment_index"))
                if segment_index not in valid_candidate_indexes:
                    errors.append(
                        f"Option {opt_index}, Cut {cut_index}: segment_index '{segment_index}' is not in the candidate pool"
                    )
        else:
            for item in alt_indexes:
                normalized = normalize_segment_index(item)
                if normalized not in valid_candidate_indexes:
                    errors.append(
                        f"Option {opt_index}: segment_index '{item}' is not in the candidate pool"
                    )

    return errors


def normalize_segment_index(value) -> int | None:
    """Parse a segment index from a few common model-output shapes."""
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        match = INDEX_PATTERN.search(value)
        if match:
            return int(match.group(0))
    return None


def normalize_segment_indexes(values) -> list[int]:
    """Normalize a collection of model or UI segment indexes."""
    normalized = []
    for value in values or []:
        item = normalize_segment_index(value)
        if item is not None and item not in normalized:
            normalized.append(item)
    return normalized


def hydrate_model_response(response: dict, candidates: list[dict], segments, source) -> dict:
    """Map model-selected candidate indexes back to exact timecodes and speakers."""
    candidate_map = {item["segment_index"]: item for item in candidates}
    hydrated_options = []

    for option_index, option in enumerate(response.get("options", []), start=1):
        hydrated_cuts = []
        raw_cuts = option.get("cuts")
        if raw_cuts:
            iterable = raw_cuts
        else:
            iterable = [
                {"segment_index": item, "order": idx + 1}
                for idx, item in enumerate(option.get("segment_indexes") or option.get("segment_indices") or [])
            ]

        for cut_index, cut in enumerate(iterable, start=1):
            if "tc_in" in cut and "tc_out" in cut:
                hydrated_cuts.append({
                    "order": cut.get("order", cut_index),
                    "tc_in": cut["tc_in"],
                    "tc_out": cut["tc_out"],
                    "speaker": cut.get("speaker", ""),
                    "purpose": cut.get("purpose", "CUT"),
                    "dialogue_summary": cut.get("dialogue_summary", ""),
                })
                continue

            segment_index = normalize_segment_index(cut.get("segment_index"))
            candidate = candidate_map.get(segment_index)
            if not candidate:
                continue
            segment = segments[segment_index]
            hydrated_cuts.append({
                "order": cut.get("order", cut_index),
                "tc_in": candidate["tc_in"],
                "tc_out": candidate["tc_out"],
                "speaker": candidate["speaker"],
                "purpose": cut.get("purpose") or candidate["roles"][0],
                "dialogue_summary": cut.get("dialogue_summary") or segment.text[:160],
            })

        if not hydrated_cuts:
            continue

        estimated_duration = option.get("estimated_duration_seconds")
        if estimated_duration in (None, ""):
            estimated_duration = round(
                sum(
                    estimate_duration_seconds(cut["tc_in"], cut["tc_out"], source.timebase, source.ntsc)
                    for cut in hydrated_cuts
                ),
                1,
            )

        hydrated_options.append({
            "name": option.get("name", f"Option {option_index}"),
            "description": option.get("description", ""),
            "estimated_duration_seconds": estimated_duration,
            "cuts": hydrated_cuts,
        })

    return {"options": hydrated_options}


def candidate_matches_purpose(candidate: dict, purpose: str) -> bool:
    """Allow replacement candidates that serve a similar editorial job."""
    purpose = (purpose or "CONTEXT").upper()
    related_roles = {
        "HOOK": {"HOOK", "REFRAME", "PIVOT"},
        "PIVOT": {"PIVOT", "REFRAME", "CONTEXT", "SOLUTION"},
        "PROOF": {"PROOF", "SOLUTION", "CONTEXT"},
        "SOLUTION": {"SOLUTION", "CONTEXT", "PROOF"},
        "VISION": {"VISION", "BUTTON", "CLOSE", "CONTEXT"},
        "BUTTON": {"BUTTON", "CLOSE", "VISION"},
        "CLOSE": {"CLOSE", "BUTTON", "VISION"},
        "CONTEXT": {"CONTEXT", "PIVOT", "SOLUTION", "PROOF"},
    }
    return any(role in candidate["roles"] for role in related_roles.get(purpose, {purpose}))


def optimize_option_duration(
    option: dict,
    candidates: list[dict],
    source,
    target_duration_range: tuple[int, int] | None,
) -> tuple[dict, list[str]]:
    """Adjust an option with shorter or longer candidate swaps when it misses the target window."""
    if not target_duration_range or not option.get("cuts"):
        return option, []

    minimum, maximum = target_duration_range
    target_midpoint = (minimum + maximum) / 2
    candidate_by_tc = {(item["tc_in"], item["tc_out"]): item for item in candidates}

    working = []
    for cut in option["cuts"]:
        candidate = candidate_by_tc.get((cut["tc_in"], cut["tc_out"]))
        working.append({
            "order": cut.get("order", len(working) + 1),
            "tc_in": cut["tc_in"],
            "tc_out": cut["tc_out"],
            "speaker": cut.get("speaker", ""),
            "purpose": cut.get("purpose", "CONTEXT"),
            "dialogue_summary": cut.get("dialogue_summary", ""),
            "candidate": candidate,
            "duration_seconds": estimate_duration_seconds(cut["tc_in"], cut["tc_out"], source.timebase, source.ntsc),
        })

    notes = []

    def total_duration() -> float:
        return sum(item["duration_seconds"] for item in working)

    def used_indexes() -> set[int]:
        return {
            item["candidate"]["segment_index"]
            for item in working
            if item.get("candidate") and item["candidate"].get("segment_index") is not None
        }

    def apply_candidate(cut_idx: int, replacement: dict):
        working[cut_idx].update({
            "tc_in": replacement["tc_in"],
            "tc_out": replacement["tc_out"],
            "speaker": replacement["speaker"],
            "dialogue_summary": replacement["text"][:160],
            "candidate": replacement,
            "duration_seconds": replacement["duration_seconds"],
        })

    guard = 0
    while total_duration() > maximum and guard < 8:
        guard += 1
        current_total = total_duration()
        used = used_indexes()
        best_move = None

        for cut_idx, cut in enumerate(working):
            current_candidate = cut.get("candidate")
            current_duration = cut["duration_seconds"]
            for replacement in candidates:
                replacement_index = replacement["segment_index"]
                if current_candidate and replacement_index == current_candidate.get("segment_index"):
                    continue
                if replacement_index in used:
                    continue
                if replacement["duration_seconds"] >= current_duration:
                    continue
                if not candidate_matches_purpose(replacement, cut.get("purpose", "CONTEXT")):
                    continue

                new_total = current_total - current_duration + replacement["duration_seconds"]
                new_distance = abs(new_total - target_midpoint)
                current_distance = abs(current_total - target_midpoint)
                improvement = current_distance - new_distance
                if improvement <= 0:
                    continue
                candidate_score = (improvement, replacement["score"])
                if not best_move or candidate_score > best_move["score"]:
                    best_move = {
                        "cut_idx": cut_idx,
                        "replacement": replacement,
                        "new_total": new_total,
                        "score": candidate_score,
                    }

        if best_move:
            old_tc = working[best_move["cut_idx"]]["tc_in"]
            replacement = best_move["replacement"]
            apply_candidate(best_move["cut_idx"], replacement)
            notes.append(
                f"Replaced cut starting at {old_tc} with {replacement['tc_in']} to tighten the option."
            )
            continue

        droppable = []
        for cut_idx, cut in enumerate(working):
            purpose = (cut.get("purpose") or "").upper()
            if purpose in {"HOOK", "BUTTON", "CLOSE", "VISION"}:
                continue
            if len(working) <= 3:
                break
            new_total = current_total - cut["duration_seconds"]
            if new_total < minimum - 3:
                continue
            improvement = abs(current_total - target_midpoint) - abs(new_total - target_midpoint)
            droppable.append((improvement, cut["duration_seconds"], cut_idx))

        if droppable:
            _, _, cut_idx = max(droppable)
            removed_tc = working[cut_idx]["tc_in"]
            del working[cut_idx]
            notes.append(f"Removed cut starting at {removed_tc} to tighten the option.")
            continue

        break

    guard = 0
    while total_duration() < minimum and guard < 4:
        guard += 1
        current_total = total_duration()
        used = used_indexes()
        best_addition = None
        for candidate in candidates:
            if candidate["segment_index"] in used:
                continue
            new_total = current_total + candidate["duration_seconds"]
            improvement = abs(current_total - target_midpoint) - abs(new_total - target_midpoint)
            if improvement <= 0:
                continue
            if not any(role in candidate["roles"] for role in ("PROOF", "CONTEXT", "SOLUTION", "VISION", "BUTTON", "CLOSE")):
                continue
            score = (improvement, candidate["score"])
            if not best_addition or score > best_addition["score"]:
                best_addition = {"candidate": candidate, "score": score}

        if not best_addition:
            break

        candidate = best_addition["candidate"]
        insert_at = max(1, len(working) - 1)
        working.insert(insert_at, {
            "order": insert_at + 1,
            "tc_in": candidate["tc_in"],
            "tc_out": candidate["tc_out"],
            "speaker": candidate["speaker"],
            "purpose": candidate["roles"][0],
            "dialogue_summary": candidate["text"][:160],
            "candidate": candidate,
            "duration_seconds": candidate["duration_seconds"],
        })
        notes.append(f"Added candidate {candidate['tc_in']} to strengthen the duration and coverage.")

    optimized_cuts = []
    for order, cut in enumerate(working, start=1):
        optimized_cuts.append({
            "order": order,
            "tc_in": cut["tc_in"],
            "tc_out": cut["tc_out"],
            "speaker": cut["speaker"],
            "purpose": cut["purpose"],
            "dialogue_summary": cut["dialogue_summary"],
        })

    optimized_option = {
        **option,
        "estimated_duration_seconds": round(total_duration(), 1),
        "cuts": optimized_cuts,
    }
    return optimized_option, notes


def optimize_response_durations(
    response: dict,
    candidates: list[dict],
    source,
    target_duration_range: tuple[int, int] | None,
) -> tuple[dict, list[str]]:
    """Optimize all options against the requested duration window."""
    if not target_duration_range:
        return response, []

    optimized_options = []
    notes = []
    for option_index, option in enumerate(response.get("options", []), start=1):
        optimized_option, option_notes = optimize_option_duration(
            option=option,
            candidates=candidates,
            source=source,
            target_duration_range=target_duration_range,
        )
        optimized_options.append(optimized_option)
        for note in option_notes:
            notes.append(f"Option {option_index}: {note}")

    return {"options": optimized_options}, notes


def enforce_requested_speaker_mix(
    response: dict,
    candidates: list[dict],
    source,
    editorial_text: str,
    target_duration_range: tuple[int, int] | None,
) -> tuple[dict, list[str]]:
    """Try to preserve multi-speaker coverage when the brief explicitly asks for it."""
    if not any(term in editorial_text for term in TECH_WORKER_TERMS):
        return response, []

    candidate_by_tc = {(item["tc_in"], item["tc_out"]): item for item in candidates}
    target_midpoint = (sum(target_duration_range) / 2) if target_duration_range else None
    notes = []
    updated_options = []

    for option_index, option in enumerate(response.get("options", []), start=1):
        speakers = {cut.get("speaker") for cut in option.get("cuts", []) if cut.get("speaker")}
        if len(speakers) > 1:
            updated_options.append(option)
            continue

        current_duration = option_actual_duration_seconds(option, source.timebase, source.ntsc)
        used_indexes = {
            candidate_by_tc[(cut["tc_in"], cut["tc_out"])]["segment_index"]
            for cut in option.get("cuts", [])
            if (cut["tc_in"], cut["tc_out"]) in candidate_by_tc
        }
        alternate_candidates = [
            candidate
            for candidate in candidates
            if candidate["segment_index"] not in used_indexes and candidate["speaker"] != next(iter(speakers or {""}))
        ]
        if not alternate_candidates:
            updated_options.append(option)
            continue

        best_move = None
        replaceable_indexes = [
            idx
            for idx, cut in enumerate(option.get("cuts", []))
            if (cut.get("purpose") or "").upper() not in {"HOOK", "BUTTON", "CLOSE"}
        ]
        if not replaceable_indexes and len(option.get("cuts", [])) > 2:
            replaceable_indexes = list(range(1, len(option["cuts"]) - 1))

        for replacement in alternate_candidates:
            for cut_idx in replaceable_indexes:
                cut = option["cuts"][cut_idx]
                purpose = cut.get("purpose", "CONTEXT")
                if not candidate_matches_purpose(replacement, purpose):
                    continue
                cut_duration = estimate_duration_seconds(cut["tc_in"], cut["tc_out"], source.timebase, source.ntsc)
                new_duration = current_duration - cut_duration + replacement["duration_seconds"]
                distance = abs(new_duration - target_midpoint) if target_midpoint else 0
                move_score = (-distance, replacement["score"])
                if not best_move or move_score > best_move["score"]:
                    best_move = {
                        "cut_idx": cut_idx,
                        "replacement": replacement,
                        "new_duration": new_duration,
                        "score": move_score,
                    }

        if not best_move:
            updated_options.append(option)
            continue

        replacement = best_move["replacement"]
        new_cuts = []
        for cut_idx, cut in enumerate(option["cuts"]):
            if cut_idx == best_move["cut_idx"]:
                new_cuts.append({
                    "order": cut.get("order", cut_idx + 1),
                    "tc_in": replacement["tc_in"],
                    "tc_out": replacement["tc_out"],
                    "speaker": replacement["speaker"],
                    "purpose": cut.get("purpose", replacement["roles"][0]),
                    "dialogue_summary": replacement["text"][:160],
                })
            else:
                new_cuts.append(cut)

        updated_options.append({
            **option,
            "estimated_duration_seconds": round(best_move["new_duration"], 1),
            "cuts": new_cuts,
        })
        notes.append(
            f"Option {option_index}: replaced one cut with {replacement['speaker']} at {replacement['tc_in']} to preserve multi-speaker coverage."
        )

    return {"options": updated_options}, notes


def enforce_selection_constraints(
    response: dict,
    candidates: list[dict],
    source,
    required_segment_indexes: list[int] | None = None,
    locked_segment_indexes: list[int] | None = None,
    forced_open_segment_index: int | None = None,
    target_duration_range: tuple[int, int] | None = None,
) -> tuple[dict, list[str]]:
    """Force required and locked bites into the cut and optionally force the opening bite."""
    required_indexes = normalize_segment_indexes(required_segment_indexes)
    locked_indexes = normalize_segment_indexes(locked_segment_indexes)
    forced_open_segment_index = normalize_segment_index(forced_open_segment_index)
    must_include = []
    for value in [forced_open_segment_index, *required_indexes, *locked_indexes]:
        if value is not None and value not in must_include:
            must_include.append(value)

    if not must_include or not response.get("options"):
        return response, []

    candidate_map = {item["segment_index"]: item for item in candidates}
    notes = []
    updated_options = []

    for option_index, option in enumerate(response.get("options", []), start=1):
        cuts = [dict(cut) for cut in option.get("cuts", [])]
        used_indexes = []
        for cut in cuts:
            for idx, candidate in candidate_map.items():
                if candidate["tc_in"] == cut["tc_in"] and candidate["tc_out"] == cut["tc_out"]:
                    used_indexes.append(idx)
                    break

        if forced_open_segment_index is not None and forced_open_segment_index in candidate_map:
            opening_candidate = candidate_map[forced_open_segment_index]
            if cuts:
                if used_indexes and forced_open_segment_index in used_indexes:
                    existing_idx = used_indexes.index(forced_open_segment_index)
                    if existing_idx != 0:
                        cuts.insert(0, cuts.pop(existing_idx))
                        used_indexes.insert(0, used_indexes.pop(existing_idx))
                        notes.append(f"Option {option_index}: moved forced opening bite {opening_candidate['tc_in']} to the front.")
                else:
                    cuts.insert(0, {
                        "order": 1,
                        "tc_in": opening_candidate["tc_in"],
                        "tc_out": opening_candidate["tc_out"],
                        "speaker": opening_candidate["speaker"],
                        "purpose": "HOOK",
                        "dialogue_summary": opening_candidate["text"][:160],
                    })
                    used_indexes.insert(0, forced_open_segment_index)
                    notes.append(f"Option {option_index}: inserted forced opening bite {opening_candidate['tc_in']}.")

        for segment_index in must_include:
            if segment_index in used_indexes or segment_index not in candidate_map:
                continue

            replacement = candidate_map[segment_index]
            insert_at = max(1, len(cuts) - 1) if cuts else 0
            cuts.insert(insert_at, {
                "order": insert_at + 1,
                "tc_in": replacement["tc_in"],
                "tc_out": replacement["tc_out"],
                "speaker": replacement["speaker"],
                "purpose": replacement["roles"][0],
                "dialogue_summary": replacement["text"][:160],
            })
            used_indexes.insert(insert_at, segment_index)
            notes.append(f"Option {option_index}: inserted required bite {replacement['tc_in']}.")

        if target_duration_range and len(cuts) > 6:
            minimum, maximum = target_duration_range
            while len(cuts) > 3 and option_actual_duration_seconds({"cuts": cuts}, source.timebase, source.ntsc) > maximum:
                removable_idx = None
                for idx in range(len(cuts) - 2, 0, -1):
                    cut = cuts[idx]
                    matching_index = None
                    for candidate_index, candidate in candidate_map.items():
                        if candidate["tc_in"] == cut["tc_in"] and candidate["tc_out"] == cut["tc_out"]:
                            matching_index = candidate_index
                            break
                    if matching_index not in must_include:
                        removable_idx = idx
                        break
                if removable_idx is None:
                    break
                removed = cuts.pop(removable_idx)
                notes.append(f"Option {option_index}: removed {removed['tc_in']} after constraint insertion to stay tighter.")

        for cut_idx, cut in enumerate(cuts, start=1):
            cut["order"] = cut_idx

        updated_options.append({
            **option,
            "estimated_duration_seconds": round(
                option_actual_duration_seconds({"cuts": cuts}, source.timebase, source.ntsc),
                1,
            ),
            "cuts": cuts,
        })

    return {"options": updated_options}, notes


def build_fallback_response(
    candidates: list[dict],
    source,
    num_options: int,
    target_duration_range: tuple[int, int] | None,
    editorial_text: str,
) -> dict:
    """Build a deterministic response when the model output is unusable."""
    target_seconds = (sum(target_duration_range) / 2) if target_duration_range else 50
    ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)

    def find_first(required_roles: tuple[str, ...], used: set[int], speaker: str | None = None):
        for candidate in ranked:
            if candidate["segment_index"] in used:
                continue
            if speaker and candidate["speaker"] != speaker:
                continue
            if any(role in candidate["roles"] for role in required_roles):
                return candidate
        return None

    options = []
    for option_number in range(1, num_options + 1):
        used = set()
        selected = []
        wants_alt_speaker = any(term in editorial_text for term in TECH_WORKER_TERMS)

        for role_group in (("HOOK", "REFRAME"), ("CONTEXT", "PIVOT", "SOLUTION"), ("PROOF",), ("PROOF", "SOLUTION"), ("VISION", "BUTTON", "CLOSE")):
            candidate = find_first(role_group, used)
            if candidate:
                selected.append(candidate)
                used.add(candidate["segment_index"])

        if wants_alt_speaker:
            alt_speaker_candidate = find_first(("PROOF", "SOLUTION", "CONTEXT"), used, speaker="Speaker 2") or find_first(("PROOF", "SOLUTION", "CONTEXT"), used, speaker="Speaker 3")
            if alt_speaker_candidate:
                selected.insert(min(3, len(selected)), alt_speaker_candidate)
                used.add(alt_speaker_candidate["segment_index"])

        current_duration = sum(item["duration_seconds"] for item in selected)
        for candidate in ranked:
            if candidate["segment_index"] in used:
                continue
            if current_duration >= target_seconds and len(selected) >= 4:
                break
            selected.append(candidate)
            used.add(candidate["segment_index"])
            current_duration += candidate["duration_seconds"]
            if len(selected) >= 6:
                break

        if option_number > 1 and selected:
            rotated = selected[option_number - 1:] + selected[:option_number - 1]
            selected = rotated

        hydrated_cuts = []
        for cut_number, candidate in enumerate(selected, start=1):
            hydrated_cuts.append({
                "order": cut_number,
                "tc_in": candidate["tc_in"],
                "tc_out": candidate["tc_out"],
                "speaker": candidate["speaker"],
                "purpose": candidate["roles"][0],
                "dialogue_summary": candidate["text"][:160],
            })

        if hydrated_cuts:
            options.append({
                "name": f"Fallback Option {option_number}",
                "description": "Deterministic assembly built from the highest-scoring candidate bites.",
                "estimated_duration_seconds": 0,
                "cuts": hydrated_cuts,
            })

    for option in options:
        option["estimated_duration_seconds"] = round(
            sum(
                estimate_duration_seconds(cut["tc_in"], cut["tc_out"], source.timebase, source.ntsc)
                for cut in option["cuts"]
            ),
            1,
        )

    return {"options": options}


def ensure_ollama_ready(model: str, host: str = DEFAULT_HOST) -> tuple[str, list[str]]:
    """Ensure Ollama is reachable and the requested model exists locally."""
    resolved_host, available = resolve_host(model=model, preferred_host=host)
    if available:
        model_names = [item.split(":")[0] for item in available]
        target_name = model.split(":")[0]
        if target_name not in model_names and model not in available:
            raise ValueError(
                f"Model '{model}' not found locally. Available models: {', '.join(available)}"
            )
    return resolved_host, available


def infer_target_duration_range(*texts: str) -> tuple[int, int] | None:
    """Infer a target duration range in seconds from the brief or project context."""
    combined = " ".join(text for text in texts if text).strip()
    if not combined:
        return None

    match = DURATION_RANGE_PATTERN.search(combined)
    if match:
        minimum = int(match.group("minimum").lstrip(":"))
        maximum = int(match.group("maximum").lstrip(":"))
        if 0 < minimum <= maximum <= 600:
            return minimum, maximum

    match = SINGLE_DURATION_PATTERN.search(combined)
    if match:
        seconds = int(match.group("seconds"))
        if 0 < seconds <= 600:
            padding = max(5, round(seconds * 0.2))
            return max(5, seconds - padding), seconds + padding

    return None


def option_actual_duration_seconds(option: dict, timebase: int, ntsc: bool) -> float:
    """Calculate the real duration of a generated option from its cut timecodes."""
    return sum(
        estimate_duration_seconds(cut["tc_in"], cut["tc_out"], timebase, ntsc)
        for cut in option.get("cuts", [])
        if "tc_in" in cut and "tc_out" in cut
    )


def format_for_generation(segments, timebase: int, ntsc: bool) -> str:
    """Format transcript segments with exact durations so the model can budget time."""
    lines = []
    for index, segment in enumerate(segments):
        duration_seconds = estimate_duration_seconds(segment.tc_in, segment.tc_out, timebase, ntsc)
        lines.append(
            f"[{index}] {segment.tc_in} - {segment.tc_out} | {segment.speaker} | {duration_seconds:.1f}s\n"
            f"    \"{segment.text}\""
        )
    return "\n\n".join(lines)


def collect_duration_warnings(
    response: dict,
    timebase: int,
    ntsc: bool,
    target_duration_range: tuple[int, int] | None,
) -> list[str]:
    """Warn when assembled options miss the requested target duration window."""
    warnings = []
    if not target_duration_range:
        return warnings

    minimum, maximum = target_duration_range
    for index, option in enumerate(response.get("options", []), start=1):
        if not option.get("cuts"):
            continue

        actual_duration = option_actual_duration_seconds(option, timebase, ntsc)
        if actual_duration < minimum or actual_duration > maximum:
            warnings.append(
                f"Option {index}: actual duration {actual_duration:.1f}s is outside target range {minimum}-{maximum}s"
            )

    return warnings


def generate_edit_options(
    segments,
    source,
    brief: str,
    num_options: int,
    model: str,
    host: str,
    timeout: int,
    project_context: str = "",
    editorial_messages: list[dict] | None = None,
    pinned_segment_indexes: list[int] | None = None,
    banned_segment_indexes: list[int] | None = None,
    required_segment_indexes: list[int] | None = None,
    locked_segment_indexes: list[int] | None = None,
    forced_open_segment_index: int | None = None,
    speaker_balance: str = "balanced",
    accepted_plan: dict | None = None,
    thinking_mode: str = DEFAULT_THINKING_MODE,
    max_attempts: int = 3,
    progress_callback=None,
):
    """Call the LLM and validate the returned edit options."""
    valid_tcs = get_valid_timecodes(segments)
    target_duration_range = infer_target_duration_range(brief, project_context)
    accepted_plan = normalize_accepted_plan(accepted_plan)
    accepted_plan_text = format_accepted_plan_text(accepted_plan)
    required_segment_indexes = normalize_segment_indexes(required_segment_indexes)
    locked_segment_indexes = normalize_segment_indexes(locked_segment_indexes)
    effective_required_segment_indexes = normalize_segment_indexes([
        *required_segment_indexes,
        *locked_segment_indexes,
        *accepted_plan["must_include_segment_indexes"],
    ])
    effective_forced_open_segment_index = forced_open_segment_index
    if effective_forced_open_segment_index is None:
        effective_forced_open_segment_index = accepted_plan["opening_segment_index"]
    effective_speaker_balance = speaker_balance
    if (
        accepted_plan["speaker_balance"]
        and effective_speaker_balance == "balanced"
    ):
        effective_speaker_balance = accepted_plan["speaker_balance"]
    editorial_direction = ""
    editorial_direction_prompt = ""
    editorial_direction_debug = {}
    attempt_logs = []
    used_fallback = False

    if editorial_messages:
        try:
            if progress_callback:
                progress_callback("Summarizing editorial direction.")
            editorial_direction_prompt = build_editorial_direction_prompt(
                brief=brief,
                project_context=project_context,
                messages=editorial_messages,
                approved_plan_text=accepted_plan_text,
            )
            editorial_direction = generate_text(
                system_prompt=EDITORIAL_DIRECTION_SYSTEM_PROMPT,
                user_prompt=editorial_direction_prompt,
                model=model,
                host=host,
                timeout=timeout,
                thinking_mode=thinking_mode,
                max_tokens=384,
                debug=editorial_direction_debug,
            )
        except Exception:
            editorial_direction = ""

    editorial_text = collect_editorial_text(
        brief=brief,
        project_context=project_context,
        editorial_direction=editorial_direction,
        editorial_messages=editorial_messages,
        accepted_plan=accepted_plan,
    )
    candidate_shortlist = build_candidate_shortlist(
        segments=segments,
        source=source,
        brief=brief,
        project_context=project_context,
        editorial_messages=editorial_messages,
        editorial_direction=editorial_direction,
        pinned_segment_indexes=pinned_segment_indexes,
        banned_segment_indexes=banned_segment_indexes,
        required_segment_indexes=effective_required_segment_indexes,
        locked_segment_indexes=locked_segment_indexes,
        forced_open_segment_index=effective_forced_open_segment_index,
        speaker_balance=effective_speaker_balance,
        accepted_plan=accepted_plan,
    )
    formatted_transcript = format_candidate_pool(candidate_shortlist)
    valid_candidate_indexes = {item["segment_index"] for item in candidate_shortlist}

    user_prompt = build_user_prompt(
        formatted_transcript,
        brief,
        num_options,
        project_context=project_context,
        target_duration_range=target_duration_range,
        editorial_messages=editorial_messages,
        editorial_direction=editorial_direction,
        approved_plan_text=accepted_plan_text,
    )

    response = {}
    used_retry = False
    errors = []
    warnings = []
    prompt = user_prompt

    for attempt in range(max_attempts):
        if progress_callback:
            progress_callback(f"Running generation attempt {attempt + 1}.")
        llm_debug = {}
        raw_response = {}
        candidate_errors = []
        structural_errors = []
        duration_warnings = []
        try:
            raw_response = ollama_generate(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                model=model,
                host=host,
                timeout=timeout,
                thinking_mode=thinking_mode,
                debug=llm_debug,
            )
            candidate_errors = collect_candidate_validation_errors(
                response=raw_response,
                valid_candidate_indexes=valid_candidate_indexes,
                expected_options=num_options,
            )
            response = hydrate_model_response(raw_response, candidate_shortlist, segments, source)
            optimization_notes = []
            if not candidate_errors:
                response, optimization_notes = optimize_response_durations(
                    response=response,
                    candidates=candidate_shortlist,
                    source=source,
                    target_duration_range=target_duration_range,
                )
                response, constraint_notes = enforce_selection_constraints(
                    response=response,
                    candidates=candidate_shortlist,
                    source=source,
                    required_segment_indexes=effective_required_segment_indexes,
                    locked_segment_indexes=locked_segment_indexes,
                    forced_open_segment_index=effective_forced_open_segment_index,
                    target_duration_range=target_duration_range,
                )
                optimization_notes.extend(constraint_notes)
                response, speaker_mix_notes = enforce_requested_speaker_mix(
                    response=response,
                    candidates=candidate_shortlist,
                    source=source,
                    editorial_text=editorial_text,
                    target_duration_range=target_duration_range,
                )
                optimization_notes.extend(speaker_mix_notes)
            structural_errors = validate_llm_response(
                response=response,
                valid_timecodes=valid_tcs,
                expected_options=num_options,
            )
            duration_warnings = collect_duration_warnings(
                response=response,
                timebase=source.timebase,
                ntsc=source.ntsc,
                target_duration_range=target_duration_range,
            )
            errors = candidate_errors + structural_errors
            warnings = optimization_notes + duration_warnings
        except Exception as exc:
            errors = [str(exc)]
            warnings = []
            response = {}

        attempt_logs.append({
            "attempt": attempt + 1,
            "prompt": prompt,
            "raw_text": llm_debug.get("raw_text", ""),
            "repaired_text": llm_debug.get("repaired_text", ""),
            "raw_response": raw_response,
            "hydrated_response": response,
            "errors": errors,
            "warnings": warnings,
        })

        if not errors:
            break

        if attempt < max_attempts - 1:
            used_retry = True
            prompt = build_retry_prompt(user_prompt, errors)

    if errors:
        if progress_callback:
            progress_callback("Model output failed validation. Building deterministic fallback.")
        used_fallback = True
        response = build_fallback_response(
            candidates=candidate_shortlist,
            source=source,
            num_options=num_options,
            target_duration_range=target_duration_range,
            editorial_text=editorial_text,
        )
        warnings = warnings + errors + [
            "Used deterministic fallback assembly because the model response was invalid or incomplete."
        ]
    else:
        errors = warnings

    if progress_callback:
        progress_callback("Selection complete.")

    debug_artifacts = {
        "editorial_direction_prompt": editorial_direction_prompt,
        "editorial_direction": editorial_direction,
        "editorial_direction_raw": editorial_direction_debug.get("raw_text", ""),
        "accepted_plan": accepted_plan,
        "accepted_plan_text": accepted_plan_text,
        "candidate_shortlist": candidate_shortlist,
        "generation_prompt": user_prompt,
        "attempts": attempt_logs,
        "used_fallback": used_fallback,
    }

    return response, errors, used_retry, valid_tcs, target_duration_range, debug_artifacts


def write_debug_artifacts(output_dir: str, debug_artifacts: dict | None) -> dict:
    """Write prompt, shortlist, and raw-model traces for a generation run."""
    paths = {}
    if not debug_artifacts:
        return paths

    if debug_artifacts.get("editorial_direction_prompt"):
        path = os.path.join(output_dir, "_editorial_direction_prompt.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(debug_artifacts["editorial_direction_prompt"])
        paths["editorial_direction_prompt"] = path

    if debug_artifacts.get("editorial_direction"):
        path = os.path.join(output_dir, "_editorial_direction.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(debug_artifacts["editorial_direction"])
        paths["editorial_direction"] = path

    if debug_artifacts.get("accepted_plan_text"):
        path = os.path.join(output_dir, "_accepted_plan.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(debug_artifacts["accepted_plan_text"])
        paths["accepted_plan"] = path

    if debug_artifacts.get("generation_prompt"):
        path = os.path.join(output_dir, "_generation_prompt.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(debug_artifacts["generation_prompt"])
        paths["generation_prompt"] = path

    if debug_artifacts.get("candidate_shortlist") is not None:
        path = os.path.join(output_dir, "_candidate_shortlist.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(debug_artifacts["candidate_shortlist"], handle, indent=2)
        paths["candidate_shortlist"] = path

    for attempt in debug_artifacts.get("attempts", []):
        attempt_id = attempt.get("attempt", 0)
        if attempt.get("raw_text"):
            path = os.path.join(output_dir, f"_generation_attempt_{attempt_id}_raw.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(attempt["raw_text"])
            paths[f"attempt_{attempt_id}_raw"] = path
        if attempt.get("repaired_text"):
            path = os.path.join(output_dir, f"_generation_attempt_{attempt_id}_repaired.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(attempt["repaired_text"])
            paths[f"attempt_{attempt_id}_repaired"] = path

    log_path = os.path.join(output_dir, "_generation_log.json")
    with open(log_path, "w", encoding="utf-8") as handle:
        json.dump(debug_artifacts, handle, indent=2)
    paths["generation_log"] = log_path
    return paths


def write_output_files(response: dict, source, output_dir: str, debug_artifacts: dict | None = None) -> tuple[list[dict], str, dict]:
    """Write XML sequences and the raw LLM response to disk."""
    os.makedirs(output_dir, exist_ok=True)
    generated_files = []
    debug_path = os.path.join(output_dir, "_llm_response.json")
    with open(debug_path, "w", encoding="utf-8") as handle:
        json.dump(response, handle, indent=2)
    debug_files = write_debug_artifacts(output_dir, debug_artifacts)

    for index, option in enumerate(response.get("options", [])):
        opt_name = option.get("name", f"Option {index + 1}")
        opt_cuts = option.get("cuts", [])
        opt_desc = option.get("description", "")

        if not opt_cuts:
            continue

        gen_cuts = [{"tc_in": cut["tc_in"], "tc_out": cut["tc_out"]} for cut in opt_cuts]
        xml_str = generate_sequence(name=opt_name, cuts=gen_cuts, source=source)
        ET.fromstring(xml_str)

        actual_dur = 0.0
        for cut in gen_cuts:
            actual_dur += estimate_duration_seconds(
                cut["tc_in"],
                cut["tc_out"],
                source.timebase,
                source.ntsc,
            )

        safe_name = opt_name.replace(" ", "_").replace("/", "-")
        filename = f"{safe_name}.xml"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as handle:
            handle.write(xml_str)

        generated_files.append({
            "name": opt_name,
            "description": opt_desc,
            "filename": filename,
            "path": filepath,
            "cut_count": len(gen_cuts),
            "actual_duration_seconds": actual_dur,
            "estimated_duration_seconds": option.get("estimated_duration_seconds", 0),
        })

    if not generated_files:
        raise RuntimeError(
            "No sequences were generated. Check the LLM response at "
            f"{os.path.abspath(debug_path)}"
        )

    return generated_files, debug_path, debug_files


def run_pipeline(
    transcript_text: str,
    xml_text: str,
    brief: str,
    options: int = 3,
    model: str = DEFAULT_MODEL,
    output_dir: str = "./output",
    host: str = DEFAULT_HOST,
    timeout: int = DEFAULT_TIMEOUT,
    project_context: str = "",
    editorial_messages: list[dict] | None = None,
    pinned_segment_indexes: list[int] | None = None,
    banned_segment_indexes: list[int] | None = None,
    required_segment_indexes: list[int] | None = None,
    locked_segment_indexes: list[int] | None = None,
    forced_open_segment_index: int | None = None,
    speaker_balance: str = "balanced",
    accepted_plan: dict | None = None,
    thinking_mode: str = DEFAULT_THINKING_MODE,
    progress_callback=None,
) -> dict:
    """Run the full BiteBuilder pipeline from raw transcript and XML strings."""
    progress = {
        "transcript_parsed": False,
        "xml_parsed": False,
        "selection_started": False,
        "output_started": False,
    }

    validated_brief = validate_brief(brief)
    if progress_callback:
        progress_callback("Parsing transcript.")
    try:
        segments = parse_transcript(
            transcript_text,
            strict=True,
        )
    except TranscriptValidationError as exc:
        raise build_transcript_timecode_error(exc.errors)

    if not segments:
        raise BiteBuilderError(build_validation_error(
            code="TRANSCRIPT-NO-SEGMENTS",
            error_type="unsupported_file_content",
            message="No valid transcript segments were found.",
            expected_input_format="Timecoded blocks following README format.",
            next_action="Ensure the transcript includes valid timecode ranges and text.",
            stage="transcript",
            recoverable=True,
        ))

    progress["transcript_parsed"] = True
    progress["segment_count"] = len(segments)

    if progress_callback:
        progress_callback("Parsing Premiere XML.")
    source = parse_premiere_xml_safe(xml_text)
    progress["xml_parsed"] = True
    progress["source"] = source.to_dict()

    # Additional validation pass with source frame rate to enforce frame-range policies.
    try:
        parse_transcript(
            transcript_text,
            strict=True,
            timebase=source.timebase,
            ntsc=source.ntsc,
        )
    except TranscriptValidationError as exc:
        raise build_transcript_timecode_error(exc.errors)

    if progress_callback:
        progress_callback("Resolving local model.")
    try:
        resolved_host, available_models = ensure_ollama_ready(model, host)
    except Exception as exc:
        raise BiteBuilderError(build_validation_error(
            code="MODEL-UNAVAILABLE",
            error_type="runtime_dependency",
            message="Failed to resolve Ollama model.",
            expected_input_format="Available Ollama model and local host.",
            next_action="Start Ollama and install the selected model.",
            stage="model",
            details={"cause": str(exc)},
        ))

    try:
        progress["selection_started"] = True
        response, validation_errors, used_retry, valid_tcs, target_duration_range, debug_artifacts = generate_edit_options(
            segments=segments,
            source=source,
            brief=validated_brief,
            num_options=options,
            model=model,
            host=resolved_host,
            timeout=timeout,
            project_context=project_context,
            editorial_messages=editorial_messages,
            pinned_segment_indexes=pinned_segment_indexes,
            banned_segment_indexes=banned_segment_indexes,
            required_segment_indexes=required_segment_indexes,
            locked_segment_indexes=locked_segment_indexes,
            forced_open_segment_index=forced_open_segment_index,
            speaker_balance=speaker_balance,
            accepted_plan=accepted_plan,
            thinking_mode=thinking_mode,
            progress_callback=progress_callback,
        )
    except Exception as exc:
        error = build_validation_error(
            code="SELECTION-FAILED",
            error_type="runtime_selection_failed",
            message="Selection failed after transcript and XML were loaded.",
            expected_input_format="Valid transcript, valid Premiere XML, and a working Ollama response.",
            next_action="Retry generation; if this repeats, verify the LLM host and captured logs.",
            stage="selection",
            recoverable=True,
            details={"cause": str(exc)},
        )
        partial = {
            "status": "partial",
            "stage": "selection",
            "progress": {**progress, "selection_started": False},
            "segment_count": len(segments),
            "source": source.to_dict(),
            "brief": validated_brief,
        }
        raise BiteBuilderError({**error, "partial": partial})

    if progress_callback:
        progress_callback("Writing output files.")
    try:
        progress["output_started"] = True
        output_files, debug_path, debug_files = write_output_files(
            response,
            source,
            output_dir,
            debug_artifacts=debug_artifacts,
        )
    except Exception as exc:
        error = build_validation_error(
            code="OUTPUT-WRITE-FAILED",
            error_type="runtime_output_error",
            message="Failed while writing generated XML files.",
            expected_input_format="Writable output directory and a complete generated response.",
            next_action="Check output permissions and retry with --output pointing to a writable folder.",
            stage="output",
            recoverable=True,
            details={"cause": str(exc)},
        )
        partial = {
            "status": "partial",
            "stage": "output",
            "progress": progress,
            "segment_count": len(segments),
            "source": source.to_dict(),
            "brief": validated_brief,
        }
        raise BiteBuilderError({**error, "partial": partial})

    return {
        "segments": segments,
        "segment_count": len(segments),
        "valid_timecode_count": len(valid_tcs),
        "source": source,
        "available_models": available_models,
        "host": resolved_host,
        "thinking_mode": normalize_thinking_mode(thinking_mode),
        "target_duration_range": target_duration_range,
        "response": response,
        "validation_errors": validation_errors,
        "used_retry": used_retry,
        "output_files": output_files,
        "debug_path": debug_path,
        "debug_files": debug_files,
        "debug_artifacts": debug_artifacts,
        "progress": progress,
        "brief": validated_brief,
        "output_dir": os.path.abspath(output_dir),
    }


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger = logging.getLogger("bitebuilder.cli")

    args = parse_args()

    print("=" * 60)
    print("  BiteBuilder v1")
    print("  AI-Powered Soundbite Selector for Premiere Pro")
    print("=" * 60)
    print()

    try:
        result = run_pipeline(
            transcript_text=read_text_file(args.transcript),
            xml_text=read_text_file(args.xml),
            brief=args.brief,
            options=args.options,
            model=args.model,
            output_dir=args.output,
            host=args.host,
            timeout=args.timeout,
            thinking_mode=args.thinking_mode,
        )
    except BiteBuilderError as exc:
        logger.error("bitebuilder_error=%s", format_error_for_log(exc.error))
        print(f"ERROR [{exc.error.get('code')}]: {exc.error.get('message')}", file=sys.stderr)
        print(f"Expected format: {exc.error.get('expected_input_format')}", file=sys.stderr)
        print(f"Fix this: {exc.error.get('next_action')}", file=sys.stderr)
        if exc.error.get("partial"):
            print(
                f"Recoverable status: {exc.error['partial'].get('status')} "
                f"at stage={exc.error['partial'].get('stage')}"
            )
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected bitebuilder error.")
        print("ERROR [RUNTIME-UNKNOWN]: Unexpected runtime failure.", file=sys.stderr)
        print("Fix this: Re-run with valid inputs and check the error details.", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        sys.exit(1)

    source = result["source"]
    print(f"Transcript segments: {result['segment_count']}")
    print(f"Timecode boundaries: {result['valid_timecode_count']}")
    print(f"Source: {source.source_name}")
    print(f"Rate: {source.actual_fps:.3f}fps | Duration: {source.duration_seconds:.1f}s")
    print(f"Resolution: {source.width}x{source.height}")
    print(f"Model: {args.model}")
    print(f"Thinking mode: {result['thinking_mode']}")
    if result["target_duration_range"]:
        print(
            "Target duration: "
            f"{result['target_duration_range'][0]}-{result['target_duration_range'][1]}s"
        )
    print()

    if result["used_retry"]:
        print("Validation required a retry before output generation.")
        if result["validation_errors"]:
            print("Remaining validation issues:")
            for error in result["validation_errors"]:
                print(f"  - {error}")
        print()

    print(f"Generated {len(result['output_files'])} sequence(s) in: {result['output_dir']}")
    for item in result["output_files"]:
        print(
            f"  {item['filename']} | {item['cut_count']} cuts | "
            f"~{item['actual_duration_seconds']:.1f}s"
        )
        if item["description"]:
            print(f"    {item['description']}")

    print()
    print("Import into Premiere Pro: File > Import > select the .xml file(s)")
    print(f"LLM response saved to: {result['debug_path']}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="BiteBuilder v1 — AI-powered soundbite selector for Premiere Pro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bitebuilder.py \\
    --transcript interview.txt \\
    --xml "Solar Project Cut Down 1.xml" \\
    --brief "45 second sizzle, start relatable, get technical, end inspiring"

  python bitebuilder.py \\
    --transcript interview.txt \\
    --xml export.xml \\
    --brief "30 second social media clip focusing on ROI" \\
    --options 5 --model llama3.1:8b
        """,
    )

    parser.add_argument(
        '--transcript', required=True,
        help='Path to timecoded transcript .txt file'
    )
    parser.add_argument(
        '--xml', required=True,
        help='Path to Premiere Pro XML export (provides source media metadata)'
    )
    parser.add_argument(
        '--brief', required=True,
        help='Creative brief describing the desired edit (quoted string)'
    )
    parser.add_argument(
        '--options', type=int, default=3,
        help='Number of edit options to generate (default: 3)'
    )
    parser.add_argument(
        '--model', default=DEFAULT_MODEL,
        help=f'Ollama model name (default: {DEFAULT_MODEL})'
    )
    parser.add_argument(
        '--output', default='./output',
        help='Output directory for generated XMLs (default: ./output)'
    )
    parser.add_argument(
        '--host', default=DEFAULT_HOST,
        help=f'Ollama API host URL (default: {DEFAULT_HOST})'
    )
    parser.add_argument(
        '--timeout', type=int, default=DEFAULT_TIMEOUT,
        help=f'LLM request timeout in seconds (default: {DEFAULT_TIMEOUT})'
    )
    parser.add_argument(
        '--thinking-mode',
        choices=['auto', 'on', 'off'],
        default=DEFAULT_THINKING_MODE,
        help=f'Qwen thinking mode control (default: {DEFAULT_THINKING_MODE})'
    )

    return parser.parse_args()


if __name__ == '__main__':
    main()
