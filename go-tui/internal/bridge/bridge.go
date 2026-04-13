package bridge

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const (
	defaultPython         = "python3"
	defaultModel          = "gemma-4-E2B-it-Q8_0.gguf"
	defaultHost           = "http://127.0.0.1:18084"
	defaultTimeoutSeconds = 300
	defaultThinkingMode   = "off"
)

// Config is the Go TUI's side-effect boundary for invoking the existing Python CLI.
type Config struct {
	RepoRoot       string
	Python         string
	TranscriptPath string
	XMLPath        string
	SequencePlan   string
	Brief          string
	OutputDir      string
	Model          string
	Host           string
	TimeoutSeconds int
	ThinkingMode   string
}

// RunResult captures the completed Python process output for display in the TUI.
type RunResult struct {
	Command string
	Stdout  string
	Stderr  string
}

// Runner executes BiteBuilder through the Python CLI. Keeping it small makes the UI easy to test later.
type Runner struct{}

// DefaultConfig returns conservative defaults that mirror the Python CLI defaults closely enough for scaffold use.
func DefaultConfig(startDir string) Config {
	root := startDir
	if found, err := FindRepoRoot(startDir); err == nil {
		root = found
	}
	return Config{
		RepoRoot:       root,
		Python:         defaultPython,
		OutputDir:      "./output",
		Model:          defaultModel,
		Host:           defaultHost,
		TimeoutSeconds: defaultTimeoutSeconds,
		ThinkingMode:   defaultThinkingMode,
	}
}

// FindRepoRoot walks upward from startDir until it finds bitebuilder.py.
func FindRepoRoot(startDir string) (string, error) {
	current, err := filepath.Abs(startDir)
	if err != nil {
		return "", fmt.Errorf("resolve start directory: %w", err)
	}
	info, err := os.Stat(current)
	if err != nil {
		return "", fmt.Errorf("stat start directory: %w", err)
	}
	if !info.IsDir() {
		current = filepath.Dir(current)
	}

	for {
		candidate := filepath.Join(current, "bitebuilder.py")
		if stat, err := os.Stat(candidate); err == nil && !stat.IsDir() {
			return current, nil
		}
		parent := filepath.Dir(current)
		if parent == current {
			return "", fmt.Errorf("could not find bitebuilder.py from %q", startDir)
		}
		current = parent
	}
}

// BuildFirstPassArgs validates Config and returns arguments for the current Python CLI first-pass path.
func (c Config) BuildFirstPassArgs() ([]string, error) {
	if strings.TrimSpace(c.TranscriptPath) == "" {
		return nil, errors.New("transcript path is required")
	}
	if strings.TrimSpace(c.XMLPath) == "" {
		return nil, errors.New("XML path is required")
	}
	if strings.TrimSpace(c.Brief) == "" {
		return nil, errors.New("creative brief is required")
	}
	if strings.TrimSpace(c.RepoRoot) == "" {
		return nil, errors.New("repo root is required")
	}
	if strings.TrimSpace(c.Python) == "" {
		return nil, errors.New("python executable is required")
	}
	if c.TimeoutSeconds <= 0 {
		return nil, errors.New("timeout must be greater than zero")
	}

	args := []string{
		filepath.Join(c.RepoRoot, "bitebuilder.py"),
		"--transcript", c.TranscriptPath,
		"--xml", c.XMLPath,
		"--brief", c.Brief,
		"--options", "1",
		"--output", defaultIfBlank(c.OutputDir, "./output"),
		"--model", defaultIfBlank(c.Model, defaultModel),
		"--host", defaultIfBlank(c.Host, defaultHost),
		"--timeout", fmt.Sprintf("%d", c.TimeoutSeconds),
		"--thinking-mode", defaultIfBlank(c.ThinkingMode, defaultThinkingMode),
	}
	return args, nil
}

// BuildReadOnlyBridgeArgs validates Config and returns arguments for the Python JSON bridge.
func (c Config) BuildReadOnlyBridgeArgs(operation string) ([]string, error) {
	operation = strings.TrimSpace(operation)
	if operation == "" {
		return nil, errors.New("bridge operation is required")
	}
	if strings.TrimSpace(c.RepoRoot) == "" {
		return nil, errors.New("repo root is required")
	}
	if strings.TrimSpace(c.Python) == "" {
		return nil, errors.New("python executable is required")
	}
	if c.TimeoutSeconds <= 0 {
		return nil, errors.New("timeout must be greater than zero")
	}

	switch operation {
	case "setup":
	case "media", "transcript", "assistant":
		if strings.TrimSpace(c.TranscriptPath) == "" {
			return nil, errors.New("transcript path is required")
		}
		if strings.TrimSpace(c.XMLPath) == "" {
			return nil, errors.New("XML path is required")
		}
	case "plan", "bite":
		if strings.TrimSpace(c.TranscriptPath) == "" {
			return nil, errors.New("transcript path is required")
		}
		if strings.TrimSpace(c.XMLPath) == "" {
			return nil, errors.New("XML path is required")
		}
		if strings.TrimSpace(c.SequencePlan) == "" {
			return nil, errors.New("sequence plan path is required")
		}
	default:
		return nil, fmt.Errorf("unsupported bridge operation %q", operation)
	}

	args := []string{
		filepath.Join(c.RepoRoot, "bitebuilder.py"),
		"--go-tui-bridge", operation,
		"--output", defaultIfBlank(c.OutputDir, "./output"),
		"--model", defaultIfBlank(c.Model, defaultModel),
		"--host", defaultIfBlank(c.Host, defaultHost),
		"--timeout", fmt.Sprintf("%d", c.TimeoutSeconds),
		"--thinking-mode", defaultIfBlank(c.ThinkingMode, defaultThinkingMode),
	}
	if strings.TrimSpace(c.TranscriptPath) != "" {
		args = append(args, "--transcript", c.TranscriptPath)
	}
	if strings.TrimSpace(c.XMLPath) != "" {
		args = append(args, "--xml", c.XMLPath)
	}
	if strings.TrimSpace(c.SequencePlan) != "" {
		args = append(args, "--sequence-plan", c.SequencePlan)
	}
	if strings.TrimSpace(c.Brief) != "" {
		args = append(args, "--brief", c.Brief)
	}
	return args, nil
}

// RunBridgeOperation invokes the Python JSON bridge and returns captured output.
func (Runner) RunBridgeOperation(ctx context.Context, config Config, operation string) (RunResult, error) {
	args, err := config.BuildReadOnlyBridgeArgs(operation)
	if err != nil {
		return RunResult{}, err
	}

	cmd := exec.CommandContext(ctx, config.Python, args...)
	cmd.Dir = config.RepoRoot

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err = cmd.Run()
	result := RunResult{
		Command: strings.Join(append([]string{config.Python}, args...), " "),
		Stdout:  stdout.String(),
		Stderr:  stderr.String(),
	}
	if err != nil {
		return result, fmt.Errorf("run BiteBuilder bridge operation %s: %w", operation, err)
	}
	return result, nil
}

// RunFirstPass invokes bitebuilder.py and returns captured output.
func (Runner) RunFirstPass(ctx context.Context, config Config) (RunResult, error) {
	args, err := config.BuildFirstPassArgs()
	if err != nil {
		return RunResult{}, err
	}

	cmd := exec.CommandContext(ctx, config.Python, args...)
	cmd.Dir = config.RepoRoot

	var stdout bytes.Buffer
	var stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	err = cmd.Run()
	result := RunResult{
		Command: strings.Join(append([]string{config.Python}, args...), " "),
		Stdout:  stdout.String(),
		Stderr:  stderr.String(),
	}
	if err != nil {
		return result, fmt.Errorf("run bitebuilder first pass: %w", err)
	}
	return result, nil
}

func defaultIfBlank(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}
