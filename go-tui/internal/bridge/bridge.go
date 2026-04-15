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
	RepoRoot                   string
	Python                     string
	TranscriptPath             string
	XMLPath                    string
	SecondaryTranscriptPath    string
	SecondaryXMLPath           string
	SequencePlan               string
	Brief                      string
	RefineInstruction          string
	SelectedBoardJSON          string
	OutputDir                  string
	Model                      string
	Host                       string
	TimeoutSeconds             int
	ThinkingMode               string
	OptionID                   string
	MaxBiteDurationSeconds     float64
	MaxTotalDurationSeconds    float64
	RequireChangedSelectedCuts bool
	RefinementRetries          int
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
		RepoRoot:          root,
		Python:            defaultPython,
		OutputDir:         "./output",
		Model:             defaultModel,
		Host:              defaultHost,
		TimeoutSeconds:    defaultTimeoutSeconds,
		ThinkingMode:      defaultThinkingMode,
		RefinementRetries: 1,
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

func appendOptionalSecondarySourceArgs(args []string, c Config) []string {
	if strings.TrimSpace(c.SecondaryTranscriptPath) != "" {
		args = append(args, "--transcript-b", c.SecondaryTranscriptPath)
	}
	if strings.TrimSpace(c.SecondaryXMLPath) != "" {
		args = append(args, "--xml-b", c.SecondaryXMLPath)
	}
	return args
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
		return nil, errors.New("creative ask is required")
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
	args = appendOptionalSecondarySourceArgs(args, c)
	return args, nil
}

// BuildGenerationArgs validates Config and returns arguments for the Python NDJSON generation bridge.
func (c Config) BuildGenerationArgs() ([]string, error) {
	if strings.TrimSpace(c.TranscriptPath) == "" {
		return nil, errors.New("transcript path is required")
	}
	if strings.TrimSpace(c.XMLPath) == "" {
		return nil, errors.New("XML path is required")
	}
	if strings.TrimSpace(c.Brief) == "" {
		return nil, errors.New("creative ask is required")
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
		"--go-tui-generate",
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
	args = appendOptionalSecondarySourceArgs(args, c)
	return args, nil
}

// BuildRefinementArgs validates Config and returns arguments for the Python NDJSON refinement bridge.
func (c Config) BuildRefinementArgs() ([]string, error) {
	if strings.TrimSpace(c.TranscriptPath) == "" {
		return nil, errors.New("transcript path is required")
	}
	if strings.TrimSpace(c.XMLPath) == "" {
		return nil, errors.New("XML path is required")
	}
	if strings.TrimSpace(c.SequencePlan) == "" {
		return nil, errors.New("sequence plan path is required")
	}
	if strings.TrimSpace(c.RefineInstruction) == "" {
		return nil, errors.New("refine instruction is required")
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
	if c.RefinementRetries < 0 {
		return nil, errors.New("refinement retries must be zero or greater")
	}

	args := []string{
		filepath.Join(c.RepoRoot, "bitebuilder.py"),
		"--go-tui-refine",
		"--transcript", c.TranscriptPath,
		"--xml", c.XMLPath,
		"--sequence-plan", c.SequencePlan,
		"--refine-instruction", c.RefineInstruction,
		"--output", defaultIfBlank(c.OutputDir, "./output"),
		"--model", defaultIfBlank(c.Model, defaultModel),
		"--host", defaultIfBlank(c.Host, defaultHost),
		"--timeout", fmt.Sprintf("%d", c.TimeoutSeconds),
		"--thinking-mode", defaultIfBlank(c.ThinkingMode, defaultThinkingMode),
		"--refinement-retries", fmt.Sprintf("%d", c.RefinementRetries),
	}
	args = appendOptionalSecondarySourceArgs(args, c)
	if strings.TrimSpace(c.OptionID) != "" {
		args = append(args, "--option-id", c.OptionID)
	}
	if c.MaxBiteDurationSeconds > 0 {
		args = append(args, "--max-bite-duration", fmt.Sprintf("%g", c.MaxBiteDurationSeconds))
	}
	if c.MaxTotalDurationSeconds > 0 {
		args = append(args, "--max-total-duration", fmt.Sprintf("%g", c.MaxTotalDurationSeconds))
	}
	if c.RequireChangedSelectedCuts {
		args = append(args, "--require-changed-cuts")
	}
	return args, nil
}

// BuildExportArgs validates Config and returns arguments for the Python NDJSON final-export bridge.
func (c Config) BuildExportArgs() ([]string, error) {
	if strings.TrimSpace(c.TranscriptPath) == "" {
		return nil, errors.New("transcript path is required")
	}
	if strings.TrimSpace(c.XMLPath) == "" {
		return nil, errors.New("XML path is required")
	}
	if strings.TrimSpace(c.SequencePlan) == "" {
		return nil, errors.New("sequence plan path is required")
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
		"--go-tui-export",
		"--transcript", c.TranscriptPath,
		"--xml", c.XMLPath,
		"--sequence-plan", c.SequencePlan,
		"--output", defaultIfBlank(c.OutputDir, "./output"),
		"--model", defaultIfBlank(c.Model, defaultModel),
		"--host", defaultIfBlank(c.Host, defaultHost),
		"--timeout", fmt.Sprintf("%d", c.TimeoutSeconds),
		"--thinking-mode", defaultIfBlank(c.ThinkingMode, defaultThinkingMode),
	}
	args = appendOptionalSecondarySourceArgs(args, c)
	if strings.TrimSpace(c.OptionID) != "" {
		args = append(args, "--option-id", c.OptionID)
	}
	if strings.TrimSpace(c.SelectedBoardJSON) != "" {
		args = append(args, "--selected-bites-json", c.SelectedBoardJSON)
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
	case "media", "transcript", "summary", "assistant":
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
	if strings.TrimSpace(c.SecondaryTranscriptPath) != "" {
		args = append(args, "--transcript-b", c.SecondaryTranscriptPath)
	}
	if strings.TrimSpace(c.SecondaryXMLPath) != "" {
		args = append(args, "--xml-b", c.SecondaryXMLPath)
	}
	if strings.TrimSpace(c.SequencePlan) != "" {
		args = append(args, "--sequence-plan", c.SequencePlan)
	}
	if strings.TrimSpace(c.Brief) != "" {
		args = append(args, "--brief", c.Brief)
	}
	if operation == "assistant" && strings.TrimSpace(c.RefineInstruction) != "" {
		args = append(args, "--refine-instruction", c.RefineInstruction)
	}
	if operation == "assistant" && strings.TrimSpace(c.SelectedBoardJSON) != "" {
		args = append(args, "--selected-bites-json", c.SelectedBoardJSON)
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

// RunGeneration invokes the Python NDJSON generation bridge and returns captured output.
func (Runner) RunGeneration(ctx context.Context, config Config) (RunResult, error) {
	args, err := config.BuildGenerationArgs()
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
		return result, fmt.Errorf("run BiteBuilder generation bridge: %w", err)
	}
	return result, nil
}

// RunRefinement invokes the Python NDJSON refinement bridge and returns captured output.
func (Runner) RunRefinement(ctx context.Context, config Config) (RunResult, error) {
	args, err := config.BuildRefinementArgs()
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
		return result, fmt.Errorf("run BiteBuilder refinement bridge: %w", err)
	}
	return result, nil
}

// RunExport invokes the Python NDJSON final-export bridge and returns captured output.
func (Runner) RunExport(ctx context.Context, config Config) (RunResult, error) {
	args, err := config.BuildExportArgs()
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
		return result, fmt.Errorf("run BiteBuilder export bridge: %w", err)
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
