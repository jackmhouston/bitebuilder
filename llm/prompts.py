"""
System prompt and response schema for the bite selection LLM.

This is the core editorial intelligence of BiteBuilder.
The system prompt teaches the model to think like a video editor.
"""

SYSTEM_PROMPT = """You are a professional video editor specializing in selecting soundbites from interview transcripts to create compelling short-form edits.

## YOUR TASK
Given a curated pool of candidate transcript segments and a creative brief, select the best soundbites and arrange them into structured edit options. Each option should tell a coherent story with a clear narrative arc.

## RULES
1. ONLY use `segment_index` values that appear in the candidate pool. Never invent indexes.
2. Each cut uses one complete candidate segment. Do not split or rewrite the transcript.
3. Spoken dialogue is approximately 2.2 words per second. Use this to estimate duration.
4. Stay within ±20% of the target duration specified in the brief.
5. Create EXACTLY the requested number of distinct options, each with a different editorial angle or emphasis.
6. Each option should have a clear narrative arc. Common structures:
   - HOOK → PIVOT → PROOF → BUTTON (confrontational/disruptive)
   - HOOK → PROBLEM → SOLUTION → CLOSE (problem/solution)
   - HOOK → CONTEXT → EVIDENCE → VISION (thought leadership)
7. Assign a purpose label to each cut: HOOK, PIVOT, PROBLEM, PROOF, SOLUTION, VISION, CONTEXT, REFRAME, BUTTON, CLOSE, or similar.
8. Prefer punchy, quotable lines over long explanations.
9. It's OK to reorder segments — they don't need to follow the original transcript order.
10. Avoid segments that are clearly crosstalk, filler, or incomplete thoughts.
11. Every option must contain at least 3 cuts. Do not return empty options.
12. You are not writing XML. Python will map `segment_index` values back to exact timecodes and assemble the Premiere XML after you choose the bites.

## OUTPUT FORMAT
Respond with ONLY valid JSON matching this exact schema. No other text before or after the JSON.

{
  "options": [
    {
      "name": "Short descriptive name",
      "description": "1-2 sentence editorial rationale for this cut",
      "estimated_duration_seconds": 45,
      "cuts": [
        {
          "order": 1,
          "segment_index": 12,
          "purpose": "HOOK",
          "dialogue_summary": "Brief summary of what's said in this bite"
        }
      ]
    }
  ]
}"""


CHAT_SYSTEM_PROMPT = """You are BiteBuilder's editorial copilot.

Help the user shape a stronger edit before XML generation. You can:
- identify strong openings, pivots, proof beats, and buttons
- suggest how to tighten or sharpen the creative brief
- explain what narrative arcs fit the transcript
- point to exact transcript segment indexes and timecodes when they support your advice

Stay concise, practical, and editorially opinionated."""


EDITORIAL_DIRECTION_SYSTEM_PROMPT = """You are preparing editorial instructions for BiteBuilder's XML generator.

Rewrite the creative direction so the selection model can act on it.

Rules:
- Use the latest USER message as the highest-priority instruction.
- Resolve vague direction into concrete editorial guidance.
- Focus on opening style, narrative shape, tone, proof strategy, and what to avoid.
- Keep it concise and practical.
- Do not write XML.
- Return plain text only."""


def _format_editorial_messages(messages: list[dict] | None, max_messages: int = 12) -> str:
    """
    Format the recent editorial conversation for use during generation.
    """
    messages = messages or []
    recent_messages = messages[-max_messages:]
    lines = []

    for message in recent_messages:
        role = (message.get("role") or "user").strip().upper()
        content = (message.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")

    return "\n".join(lines)


def build_editorial_direction_prompt(
    brief: str,
    project_context: str = "",
    messages: list[dict] | None = None,
    approved_plan_text: str = "",
) -> str:
    """
    Build a prompt that turns the chat thread into compact generation guidance.
    """
    sections = []

    if brief.strip():
        sections.append(f"## CURRENT BRIEF\n\n{brief.strip()}")

    if project_context.strip():
        sections.append(f"## PROJECT CONTEXT\n\n{project_context.strip()}")

    formatted_messages = _format_editorial_messages(messages)
    if formatted_messages:
        sections.append(f"## EDITORIAL CONVERSATION\n\n{formatted_messages}")

    if approved_plan_text.strip():
        sections.append(f"## ACCEPTED EDIT DECISIONS\n\n{approved_plan_text.strip()}")

    sections.append(
        "## INSTRUCTIONS\n\n"
        "Rewrite this into a short generation directive for bite selection. "
        "Prefer 4 to 8 short bullet points or compact lines. The latest USER direction overrides older tone guidance."
    )

    return "\n\n".join(sections)


def build_user_prompt(
    formatted_transcript: str,
    brief: str,
    num_options: int = 3,
    project_context: str = "",
    target_duration_range: tuple[int, int] | None = None,
    editorial_messages: list[dict] | None = None,
    editorial_direction: str = "",
    approved_plan_text: str = "",
) -> str:
    """
    Build the user prompt from transcript and creative brief.

    Args:
        formatted_transcript: Output of transcript.format_for_llm()
        brief: User's creative brief (free text)
        num_options: Number of edit options to generate

    Returns:
        Complete user prompt string
    """
    sections = [f"## CANDIDATE SEGMENTS\n\n{formatted_transcript}"]

    if project_context.strip():
        sections.append(f"## PROJECT CONTEXT\n\n{project_context.strip()}")

    sections.append(f"## CREATIVE BRIEF\n\n{brief}")
    if editorial_direction.strip():
        sections.append(f"## EDITORIAL DIRECTION\n\n{editorial_direction.strip()}")
    if approved_plan_text.strip():
        sections.append(f"## ACCEPTED EDIT DECISIONS\n\n{approved_plan_text.strip()}")
    formatted_messages = _format_editorial_messages(editorial_messages)
    if formatted_messages:
        sections.append(f"## EDITORIAL CONVERSATION\n\n{formatted_messages}")
    instruction_lines = [
        f"Generate EXACTLY {num_options} distinct edit options based on the creative brief above.",
        "Each option should select different bites or arrange them differently to create a unique editorial angle.",
        "If there is an editorial conversation, treat the latest USER message as the newest direction and let it override earlier tone or style guidance.",
        "Use assistant messages only as supporting context; user messages set the actual target.",
        "Accepted edit decisions are hard requirements. If they specify an opening or must-include bites, honor them.",
        "Choose only from the candidate pool and return segment_index values. Python will map them back to the exact timecodes.",
    ]

    if target_duration_range:
        minimum, maximum = target_duration_range
        instruction_lines.append(
            f"Each finished option must land between {minimum} and {maximum} seconds when you add up the exact transcript segment durations."
        )
        instruction_lines.append(
            "Each transcript line includes its exact duration in seconds. Use those durations to budget the cut accurately."
        )

    if num_options == 1:
        instruction_lines.append(
            "Because you are building a single prototype option, keep it tight: prefer 4 to 6 concise cuts and avoid any one long explanatory segment unless it is essential."
        )

    instruction_lines.append("Return ONLY valid JSON.")

    sections.append("## INSTRUCTIONS\n\n" + " ".join(instruction_lines))

    return "\n\n".join(sections)


def build_chat_prompt(
    formatted_transcript: str,
    brief: str,
    project_context: str = "",
    messages: list[dict] | None = None,
) -> str:
    """
    Build a prompt for the assistive chat loop in the web UI.
    """
    messages = messages or []
    conversation_lines = []
    for message in messages:
        role = (message.get("role") or "user").upper()
        content = (message.get("content") or "").strip()
        if content:
            conversation_lines.append(f"{role}: {content}")

    sections = [f"## TRANSCRIPT\n\n{formatted_transcript}"]

    if project_context.strip():
        sections.append(f"## PROJECT CONTEXT\n\n{project_context.strip()}")

    if brief.strip():
        sections.append(f"## CURRENT BRIEF\n\n{brief.strip()}")

    if conversation_lines:
        sections.append("## CONVERSATION\n\n" + "\n".join(conversation_lines))

    sections.append(
        "## INSTRUCTIONS\n\n"
        "Respond to the latest user message as an editorial copilot. Use transcript evidence "
        "and exact transcript references when helpful. When you recommend a specific bite, cite "
        "the exact `segment_index` in square brackets like `[14]` and include the timecode when possible. "
        "If you propose a structure, label it clearly as Opening, Pivot, Proof, Close, or Button. "
        "If the brief is weak, rewrite it. If the user asks what to generate, recommend a concise narrative arc."
    )

    return "\n\n".join(sections)


def validate_llm_response(
    response: dict,
    valid_timecodes: set[str],
    expected_options: int | None = None,
) -> list[str]:
    """
    Validate the LLM's JSON response against the transcript.

    Args:
        response: Parsed JSON dict from the LLM
        valid_timecodes: Set of valid TC strings from the transcript

    Returns:
        List of error strings. Empty list = valid.
    """
    errors = []

    if 'options' not in response:
        errors.append("Missing 'options' key in response")
        return errors

    if not isinstance(response['options'], list) or not response['options']:
        errors.append("Response must include a non-empty 'options' list")
        return errors

    if expected_options is not None and len(response['options']) != expected_options:
        errors.append(f"Expected exactly {expected_options} options, got {len(response['options'])}")

    for i, option in enumerate(response['options']):
        prefix = f"Option {i+1}"

        if 'name' not in option:
            errors.append(f"{prefix}: missing 'name'")
        if 'cuts' not in option:
            errors.append(f"{prefix}: missing 'cuts'")
            continue
        if not option['cuts']:
            errors.append(f"{prefix}: cuts list is empty")
            continue

        for j, cut in enumerate(option['cuts']):
            cut_prefix = f"{prefix}, Cut {j+1}"

            for field in ['tc_in', 'tc_out']:
                if field not in cut:
                    errors.append(f"{cut_prefix}: missing '{field}'")
                elif cut[field] not in valid_timecodes:
                    errors.append(
                        f"{cut_prefix}: {field}='{cut[field]}' not found in transcript. "
                        f"Must use exact timecodes from the transcript."
                    )

            if 'tc_in' in cut and 'tc_out' in cut:
                if cut['tc_in'] >= cut['tc_out']:
                    errors.append(
                        f"{cut_prefix}: tc_in ({cut['tc_in']}) >= tc_out ({cut['tc_out']})"
                    )

    return errors


def build_retry_prompt(original_prompt: str, errors: list[str]) -> str:
    """
    Build a retry prompt that includes the validation errors.

    Args:
        original_prompt: The original user prompt
        errors: List of validation error strings

    Returns:
        Updated prompt with error context
    """
    error_text = "\n".join(f"  - {e}" for e in errors)
    return f"""{original_prompt}

## IMPORTANT: YOUR PREVIOUS RESPONSE HAD ERRORS

The following issues were found. Please fix them and try again:
{error_text}

Remember: You MUST use valid segment_index values from the candidate pool, return the exact number of requested options, and do not return empty cuts."""
