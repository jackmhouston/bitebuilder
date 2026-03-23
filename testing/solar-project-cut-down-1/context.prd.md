# PRD: Solar Project Cut Down 1 Test Context

## Overview

Create a reusable test context for the BiteBuilder GUI so the Solar Project transcript and Premiere XML can be loaded without manual re-entry. The goal is to let the user run a first-pass edit generation immediately, then use the assistive chat window to refine the direction after the copilot has seen the transcript.

## Test Goals

- Preload the Solar transcript and Premiere XML from a stable repo-side testing directory.
- Preload the current creative brief and project context into the GUI.
- Default the run to three options and a standard timeout.
- Support a first-pass generation before any chat.
- Preserve the ability to use chat loops after the transcript has been read.

## Creative Brief

solar panel company innovation, interview with the CEO and one of his technical workers, innovation amidst unpopularity

## Project Context

Need a few options for a :45 to a :60 second cut for bites that start with something hooky, "solar is the future" and similar opening beats, then move into accessible but intelligent information. Some of these bites can be spliced together to create a more optimal outcome.

The intended loop is:

1. Run a first pass automatically from the preloaded files and context.
2. Let the user use the assistive chat after the copilot has read the transcript.
3. Regenerate once the brief has been sharpened.

## Default Run Settings

- Model: `qwen3:8b`
- Options: `3`
- Timeout: `300`

## Test Assets

- Transcript: `testing/solar-project-cut-down-1/Solar Project Cut Down 1.txt`
- Premiere XML: `testing/solar-project-cut-down-1/Solar Project Cut Down 1.xml`
