package bridge

import (
	"reflect"
	"strings"
	"testing"
)

func TestBuildFirstPassArgs(t *testing.T) {
	config := Config{
		RepoRoot:       "/repo",
		Python:         "python3",
		TranscriptPath: "interview.txt",
		XMLPath:        "source.xml",
		Brief:          "make a tight proof of concept",
		OutputDir:      "./out",
		Model:          "gemma-4-E2B-it-Q8_0.gguf",
		Host:           "http://127.0.0.1:18084",
		TimeoutSeconds: 120,
		ThinkingMode:   "off",
	}

	got, err := config.BuildFirstPassArgs()
	if err != nil {
		t.Fatalf("BuildFirstPassArgs() error = %v", err)
	}
	want := []string{
		"/repo/bitebuilder.py",
		"--transcript", "interview.txt",
		"--xml", "source.xml",
		"--brief", "make a tight proof of concept",
		"--options", "1",
		"--output", "./out",
		"--model", "gemma-4-E2B-it-Q8_0.gguf",
		"--host", "http://127.0.0.1:18084",
		"--timeout", "120",
		"--thinking-mode", "off",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("BuildFirstPassArgs() = %#v, want %#v", got, want)
	}
}

func TestBuildFirstPassArgsRequiresInputs(t *testing.T) {
	config := DefaultConfig("/repo")
	if _, err := config.BuildFirstPassArgs(); err == nil {
		t.Fatal("BuildFirstPassArgs() error = nil, want missing transcript error")
	}
}

func TestBuildReadOnlyBridgeArgsForPlan(t *testing.T) {
	config := Config{
		RepoRoot:       "/repo",
		Python:         "python3",
		TranscriptPath: "interview.txt",
		XMLPath:        "source.xml",
		SequencePlan:   "out/_sequence_plan.json",
		OutputDir:      "./out",
		Model:          "gemma-4-E2B-it-Q8_0.gguf",
		Host:           "http://127.0.0.1:18084",
		TimeoutSeconds: 120,
		ThinkingMode:   "off",
	}

	got, err := config.BuildReadOnlyBridgeArgs("plan")
	if err != nil {
		t.Fatalf("BuildReadOnlyBridgeArgs() error = %v", err)
	}
	want := []string{
		"/repo/bitebuilder.py",
		"--go-tui-bridge", "plan",
		"--output", "./out",
		"--model", "gemma-4-E2B-it-Q8_0.gguf",
		"--host", "http://127.0.0.1:18084",
		"--timeout", "120",
		"--thinking-mode", "off",
		"--transcript", "interview.txt",
		"--xml", "source.xml",
		"--sequence-plan", "out/_sequence_plan.json",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("BuildReadOnlyBridgeArgs() = %#v, want %#v", got, want)
	}
}

func TestBuildReadOnlyBridgeArgsForAssistantIncludesBrief(t *testing.T) {
	config := Config{
		RepoRoot:       "/repo",
		Python:         "python3",
		TranscriptPath: "interview.txt",
		XMLPath:        "source.xml",
		Brief:          "make a better story",
		OutputDir:      "./out",
		Model:          "gemma-4-E2B-it-Q8_0.gguf",
		Host:           "http://127.0.0.1:18084",
		TimeoutSeconds: 120,
		ThinkingMode:   "off",
	}

	got, err := config.BuildReadOnlyBridgeArgs("assistant")
	if err != nil {
		t.Fatalf("BuildReadOnlyBridgeArgs(assistant) error = %v", err)
	}
	want := []string{
		"/repo/bitebuilder.py",
		"--go-tui-bridge", "assistant",
		"--output", "./out",
		"--model", "gemma-4-E2B-it-Q8_0.gguf",
		"--host", "http://127.0.0.1:18084",
		"--timeout", "120",
		"--thinking-mode", "off",
		"--transcript", "interview.txt",
		"--xml", "source.xml",
		"--brief", "make a better story",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("BuildReadOnlyBridgeArgs(assistant) = %#v, want %#v", got, want)
	}
}

func TestBuildReadOnlyBridgeArgsForAssistantIncludesSelectionContext(t *testing.T) {
	config := Config{
		RepoRoot:          "/repo",
		Python:            "python3",
		TranscriptPath:    "interview.txt",
		XMLPath:           "source.xml",
		SequencePlan:      "out/_sequence_plan.json",
		Brief:             "make a better story",
		RefineInstruction: "why this bite?",
		SelectedBoardJSON: `{"selected_bites":[{"bite_id":"bite-002"}]}`,
		OutputDir:         "./out",
		Model:             "gemma-4-E2B-it-Q8_0.gguf",
		Host:              "http://127.0.0.1:18084",
		TimeoutSeconds:    120,
		ThinkingMode:      "off",
	}

	got, err := config.BuildReadOnlyBridgeArgs("assistant")
	if err != nil {
		t.Fatalf("BuildReadOnlyBridgeArgs(assistant) error = %v", err)
	}
	want := []string{
		"/repo/bitebuilder.py",
		"--go-tui-bridge", "assistant",
		"--output", "./out",
		"--model", "gemma-4-E2B-it-Q8_0.gguf",
		"--host", "http://127.0.0.1:18084",
		"--timeout", "120",
		"--thinking-mode", "off",
		"--transcript", "interview.txt",
		"--xml", "source.xml",
		"--sequence-plan", "out/_sequence_plan.json",
		"--brief", "make a better story",
		"--refine-instruction", "why this bite?",
		"--selected-bites-json", `{"selected_bites":[{"bite_id":"bite-002"}]}`,
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("BuildReadOnlyBridgeArgs(assistant selection) = %#v, want %#v", got, want)
	}
}

func TestBuildReadOnlyBridgeArgsForSummary(t *testing.T) {
	config := Config{
		RepoRoot:                "/repo",
		Python:                  "python3",
		TranscriptPath:          "interview.txt",
		XMLPath:                 "source.xml",
		SecondaryTranscriptPath: "interview-b.txt",
		SecondaryXMLPath:        "source-b.xml",
		OutputDir:               "./out",
		Model:                   "gemma-4-E2B-it-Q8_0.gguf",
		Host:                    "http://127.0.0.1:18084",
		TimeoutSeconds:          120,
		ThinkingMode:            "off",
	}

	got, err := config.BuildReadOnlyBridgeArgs("summary")
	if err != nil {
		t.Fatalf("BuildReadOnlyBridgeArgs(summary) error = %v", err)
	}
	want := []string{
		"/repo/bitebuilder.py",
		"--go-tui-bridge", "summary",
		"--output", "./out",
		"--model", "gemma-4-E2B-it-Q8_0.gguf",
		"--host", "http://127.0.0.1:18084",
		"--timeout", "120",
		"--thinking-mode", "off",
		"--transcript", "interview.txt",
		"--xml", "source.xml",
		"--transcript-b", "interview-b.txt",
		"--xml-b", "source-b.xml",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("BuildReadOnlyBridgeArgs(summary) = %#v, want %#v", got, want)
	}
}

func TestBuildRefinementArgs(t *testing.T) {
	config := Config{
		RepoRoot:                   "/repo",
		Python:                     "python3",
		TranscriptPath:             "interview.txt",
		XMLPath:                    "source.xml",
		SequencePlan:               "out/_sequence_plan.json",
		RefineInstruction:          "make the opening sharper",
		OutputDir:                  "./out",
		Model:                      "gemma-4-E2B-it-Q8_0.gguf",
		Host:                       "http://127.0.0.1:18084",
		TimeoutSeconds:             120,
		ThinkingMode:               "off",
		OptionID:                   "option-2",
		MaxBiteDurationSeconds:     8.5,
		MaxTotalDurationSeconds:    45,
		RequireChangedSelectedCuts: true,
		RefinementRetries:          2,
	}

	got, err := config.BuildRefinementArgs()
	if err != nil {
		t.Fatalf("BuildRefinementArgs() error = %v", err)
	}
	want := []string{
		"/repo/bitebuilder.py",
		"--go-tui-refine",
		"--transcript", "interview.txt",
		"--xml", "source.xml",
		"--sequence-plan", "out/_sequence_plan.json",
		"--refine-instruction", "make the opening sharper",
		"--output", "./out",
		"--model", "gemma-4-E2B-it-Q8_0.gguf",
		"--host", "http://127.0.0.1:18084",
		"--timeout", "120",
		"--thinking-mode", "off",
		"--refinement-retries", "2",
		"--option-id", "option-2",
		"--max-bite-duration", "8.5",
		"--max-total-duration", "45",
		"--require-changed-cuts",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("BuildRefinementArgs() = %#v, want %#v", got, want)
	}
}

func TestBuildRefinementArgsRequiresSequencePlanAndInstruction(t *testing.T) {
	config := DefaultConfig("/repo")
	config.TranscriptPath = "interview.txt"
	config.XMLPath = "source.xml"
	if _, err := config.BuildRefinementArgs(); err == nil {
		t.Fatal("BuildRefinementArgs() error = nil, want missing sequence plan error")
	}
	config.SequencePlan = "out/_sequence_plan.json"
	if _, err := config.BuildRefinementArgs(); err == nil {
		t.Fatal("BuildRefinementArgs() error = nil, want missing refine instruction error")
	}
	config.RefineInstruction = "make it shorter"
	config.RefinementRetries = -1
	if _, err := config.BuildRefinementArgs(); err == nil {
		t.Fatal("BuildRefinementArgs() error = nil, want invalid retries error")
	}
}

func TestBuildExportArgs(t *testing.T) {
	config := Config{
		RepoRoot:          "/repo",
		Python:            "python3",
		TranscriptPath:    "interview.txt",
		XMLPath:           "source.xml",
		SequencePlan:      "out/_sequence_plan.json",
		OutputDir:         "./out",
		Model:             "gemma-4-E2B-it-Q8_0.gguf",
		Host:              "http://127.0.0.1:18084",
		TimeoutSeconds:    120,
		ThinkingMode:      "off",
		OptionID:          "option-2",
		SelectedBoardJSON: `{"selected_bites":[{"bite_id":"bite-001"}]}`,
	}

	got, err := config.BuildExportArgs()
	if err != nil {
		t.Fatalf("BuildExportArgs() error = %v", err)
	}
	want := []string{
		"/repo/bitebuilder.py",
		"--go-tui-export",
		"--transcript", "interview.txt",
		"--xml", "source.xml",
		"--sequence-plan", "out/_sequence_plan.json",
		"--output", "./out",
		"--model", "gemma-4-E2B-it-Q8_0.gguf",
		"--host", "http://127.0.0.1:18084",
		"--timeout", "120",
		"--thinking-mode", "off",
		"--option-id", "option-2",
		"--selected-bites-json", `{"selected_bites":[{"bite_id":"bite-001"}]}`,
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("BuildExportArgs() = %#v, want %#v", got, want)
	}
}

func TestBuildExportArgsRequiresInputs(t *testing.T) {
	config := DefaultConfig("/repo")
	if _, err := config.BuildExportArgs(); err == nil {
		t.Fatal("BuildExportArgs() error = nil, want missing transcript error")
	}
	config.TranscriptPath = "interview.txt"
	config.XMLPath = "source.xml"
	if _, err := config.BuildExportArgs(); err == nil {
		t.Fatal("BuildExportArgs() error = nil, want missing sequence plan error")
	}
}

func TestBuildReadOnlyBridgeArgsRequiresScreenSpecificInputs(t *testing.T) {
	config := DefaultConfig("/repo")
	if _, err := config.BuildReadOnlyBridgeArgs("setup"); err != nil {
		t.Fatalf("setup bridge args error = %v", err)
	}
	if _, err := config.BuildReadOnlyBridgeArgs("media"); err == nil {
		t.Fatal("media bridge args error = nil, want missing transcript error")
	}
	config.TranscriptPath = "interview.txt"
	config.XMLPath = "source.xml"
	if _, err := config.BuildReadOnlyBridgeArgs("plan"); err == nil {
		t.Fatal("plan bridge args error = nil, want missing sequence plan error")
	}
}

func TestBuildGenerationArgs(t *testing.T) {
	config := Config{
		RepoRoot:       "/repo",
		Python:         "python3",
		TranscriptPath: "interview.txt",
		XMLPath:        "source.xml",
		Brief:          "make a tight proof of concept",
		OutputDir:      "./out",
		Model:          "gemma-4-E2B-it-Q8_0.gguf",
		Host:           "http://127.0.0.1:18084",
		TimeoutSeconds: 120,
		ThinkingMode:   "off",
	}

	got, err := config.BuildGenerationArgs()
	if err != nil {
		t.Fatalf("BuildGenerationArgs() error = %v", err)
	}
	want := []string{
		"/repo/bitebuilder.py",
		"--go-tui-generate",
		"--transcript", "interview.txt",
		"--xml", "source.xml",
		"--brief", "make a tight proof of concept",
		"--options", "1",
		"--output", "./out",
		"--model", "gemma-4-E2B-it-Q8_0.gguf",
		"--host", "http://127.0.0.1:18084",
		"--timeout", "120",
		"--thinking-mode", "off",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("BuildGenerationArgs() = %#v, want %#v", got, want)
	}
}

func TestDecodeEnvelopeDataForSetup(t *testing.T) {
	stdout := `{"ok":true,"schema_version":"go_tui_bridge.v1","operation":"setup","data":{"version":"0.1.0","capabilities":{"transport":"request_response_json","mutates_output":false,"operations":["setup","media"],"runtime_boundary":{"python_authoritative_for":["model_calls","sequence_plan_refinement","sequence_plan_validation","xmeml_generation"],"go_tui_role":"bubble_tea_ui_and_subprocess_event_client","generation_transport":"subprocess_ndjson"}},"defaults":{"model":"gemma","host":"http://127.0.0.1:18084","timeout":300,"thinking_mode":"off","output_dir":"./output"},"paths":{"transcript":"interview.txt","xml":"source.xml","sequence_plan":"_sequence_plan.json"}}}`

	envelope, err := DecodeEnvelope(stdout)
	if err != nil {
		t.Fatalf("DecodeEnvelope() error = %v", err)
	}
	data, err := DecodeEnvelopeData[SetupData](envelope)
	if err != nil {
		t.Fatalf("DecodeEnvelopeData[SetupData]() error = %v", err)
	}
	if data.Capabilities.MutatesOutput {
		t.Fatal("setup capability mutates_output = true, want false")
	}
	if data.Defaults.ThinkingMode != "off" {
		t.Fatalf("thinking mode = %q, want off", data.Defaults.ThinkingMode)
	}
	if got := data.Capabilities.Operations[1]; got != OperationMedia {
		t.Fatalf("operation[1] = %q, want %q", got, OperationMedia)
	}
	wantAuthority := []string{"model_calls", "sequence_plan_refinement", "sequence_plan_validation", "xmeml_generation"}
	if !reflect.DeepEqual(data.Capabilities.RuntimeBoundary.PythonAuthoritativeFor, wantAuthority) {
		t.Fatalf("python authority = %#v, want %#v", data.Capabilities.RuntimeBoundary.PythonAuthoritativeFor, wantAuthority)
	}
	if got := data.Capabilities.RuntimeBoundary.GoTUIRole; got != "bubble_tea_ui_and_subprocess_event_client" {
		t.Fatalf("go_tui_role = %q, want subprocess UI role", got)
	}
}

func TestDecodeEnvelopeRejectsErrorWithoutPayload(t *testing.T) {
	_, err := DecodeEnvelope(`{"ok":false,"schema_version":"go_tui_bridge.v1","operation":"media"}`)
	if err == nil {
		t.Fatal("DecodeEnvelope() error = nil, want missing error payload failure")
	}
}

func TestParseGenerationEvents(t *testing.T) {
	stdout := strings.Join([]string{
		`{"event":"started","request_id":"req-1","schema_version":"go_tui_generation_events.v1","stage":"start"}`,
		`{"event":"progress","message":"Running generation attempt 1.","request_id":"req-1","schema_version":"go_tui_generation_events.v1","stage":"model_request"}`,
		`{"event":"artifact","kind":"sequence_plan","path":"out/_sequence_plan.json","request_id":"req-1","schema_version":"go_tui_generation_events.v1"}`,
		`{"event":"completed","ok":true,"request_id":"req-1","schema_version":"go_tui_generation_events.v1","stage":"complete"}`,
	}, "\n")

	events, err := ParseGenerationEvents(stdout)
	if err != nil {
		t.Fatalf("ParseGenerationEvents() error = %v", err)
	}
	if got := events[0].Event; got != GenerationEventStarted {
		t.Fatalf("event[0] = %q, want %q", got, GenerationEventStarted)
	}
	if got := events[1].Stage; got != "model_request" {
		t.Fatalf("event[1].Stage = %q, want model_request", got)
	}
	if got := events[2].Path; got != "out/_sequence_plan.json" {
		t.Fatalf("event[2].Path = %q, want sequence plan path", got)
	}
	if events[3].OK == nil || !*events[3].OK {
		t.Fatalf("completed ok = %v, want true", events[3].OK)
	}
}

func TestParseGenerationEventsRejectsMalformedStdout(t *testing.T) {
	_, err := ParseGenerationEvents("not-json\n")
	if err == nil {
		t.Fatal("ParseGenerationEvents() error = nil, want malformed line failure")
	}
}
