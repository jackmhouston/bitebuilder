package bridge

import (
	"reflect"
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
