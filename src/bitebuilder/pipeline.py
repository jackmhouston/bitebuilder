from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable

from bitebuilder.models import (
    GenerationRequest,
    GenerationResult,
    SelectionCandidate,
)
from bitebuilder.ollama_client import OllamaClient, OllamaError
from bitebuilder.premiere_xml_parser import parse_premiere_xml
from bitebuilder.prompts import build_selection_prompt
from bitebuilder.transcript_parser import parse_transcript
from bitebuilder.xmeml_generator import render_xmeml_sequence

Logger = Callable[[str], None]


def run_generation(
    request: GenerationRequest,
    logger: Logger | None = None,
) -> GenerationResult:
    log = logger or (lambda _: None)
    log("Parsing transcript...")
    transcript = parse_transcript(request.transcript_path)
    log(f"Loaded {len(transcript.segments)} transcript segments.")

    log("Parsing Premiere XML...")
    project = parse_premiere_xml(request.premiere_xml_path)
    log(f"Loaded {len(project.clips)} source clips at {project.fps} fps.")

    warnings: list[str] = []
    if request.dry_run:
        log("Dry-run mode enabled. Using deterministic local selection.")
        selections = _fallback_selection(request.brief, transcript.segments)
    else:
        prompt = build_selection_prompt(request, transcript, project)
        log(f"Asking local Ollama model {request.model} for an edit pass...")
        try:
            llm_payload = OllamaClient(request.ollama_url).generate_json(
                model=request.model,
                prompt=prompt,
            )
            selections = _normalize_llm_selection(llm_payload, transcript.segments)
            log(f"Model returned {len(selections)} selected bites.")
        except OllamaError as exc:
            warnings.append(str(exc))
            log(f"Ollama unavailable, falling back to deterministic selection: {exc}")
            selections = _fallback_selection(request.brief, transcript.segments)

    if not selections:
        raise ValueError("No selections were produced from transcript or model output.")

    log("Rendering XMEML sequence...")
    xml_text = render_xmeml_sequence(
        sequence_title=request.sequence_title,
        project=project,
        selections=selections,
    )

    output_path = Path(request.output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(xml_text, encoding="utf-8")
    log(f"Wrote {output_path}")

    return GenerationResult(
        output_path=output_path,
        sequence_title=request.sequence_title,
        selected_count=len(selections),
        warnings=warnings,
    )


def _normalize_llm_selection(payload: dict, segments) -> list[SelectionCandidate]:
    selected_segments = payload.get("selected_segments") or []
    normalized: list[SelectionCandidate] = []
    for raw in selected_segments:
        transcript_index = int(raw.get("transcript_index", 0))
        segment = _segment_by_index(segments, transcript_index)
        if segment is None:
            continue
        normalized.append(
            SelectionCandidate(
                transcript_index=segment.index,
                quote=(raw.get("quote") or segment.text).strip(),
                reason=(raw.get("reason") or "Selected by local model.").strip(),
                source_clip_id=_none_if_blank(raw.get("source_clip_id")),
                source_clip_name=_none_if_blank(raw.get("source_clip_name")),
                duration_seconds=_coerce_duration(
                    raw.get("duration_seconds"),
                    segment.start_seconds,
                    segment.end_seconds,
                ),
            )
        )
    return normalized


def _fallback_selection(brief: str, segments) -> list[SelectionCandidate]:
    keywords = [word.casefold() for word in brief.split() if len(word) > 3]
    weights = Counter(keywords)
    ranked = sorted(
        segments,
        key=lambda segment: (_segment_score(segment.text, weights), -segment.index),
        reverse=True,
    )
    chosen = ranked[: min(5, len(ranked))]
    if not chosen:
        return []
    ordered = sorted(chosen, key=lambda segment: segment.index)
    return [
        SelectionCandidate(
            transcript_index=segment.index,
            quote=segment.text,
            reason="Fallback heuristic selection based on brief keyword overlap.",
            duration_seconds=_coerce_duration(
                None,
                segment.start_seconds,
                segment.end_seconds,
            ),
        )
        for segment in ordered
    ]


def _segment_score(text: str, weights: Counter[str]) -> int:
    words = [word.casefold().strip(".,!?\"'()[]") for word in text.split()]
    if not weights:
        return len(words)
    return sum(weights[word] for word in words if word in weights) + len(words) // 6


def _segment_by_index(segments, transcript_index: int):
    for segment in segments:
        if segment.index == transcript_index:
            return segment
    return None


def _coerce_duration(
    explicit_duration,
    start_seconds: float | None,
    end_seconds: float | None,
) -> float:
    if explicit_duration is not None:
        try:
            return max(float(explicit_duration), 1.0)
        except (TypeError, ValueError):
            pass
    if start_seconds is not None and end_seconds is not None and end_seconds > start_seconds:
        return end_seconds - start_seconds
    return 4.0


def _none_if_blank(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None

