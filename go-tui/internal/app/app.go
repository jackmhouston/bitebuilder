package app

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/jackmhouston/bitebuilder/go-tui/internal/bridge"
	"github.com/jackmhouston/bitebuilder/go-tui/internal/ui"
)

// Run parses command-line flags and starts the Bubble Tea program.
func Run(ctx context.Context, args []string, stdin io.Reader, stdout, stderr io.Writer) error {
	flags := flag.NewFlagSet("bitebuilder-tui", flag.ContinueOnError)
	flags.SetOutput(stderr)

	cwd, err := os.Getwd()
	if err != nil {
		return fmt.Errorf("get working directory: %w", err)
	}

	config := bridge.DefaultConfig(cwd)
	if root, err := bridge.FindRepoRoot(cwd); err == nil {
		config.RepoRoot = root
	}

	noAltScreen := flags.Bool("no-alt-screen", false, "run without entering the terminal alternate screen")
	flags.StringVar(&config.RepoRoot, "repo", config.RepoRoot, "path to the BiteBuilder repository root")
	flags.StringVar(&config.Python, "python", config.Python, "python executable used to run bitebuilder.py")
	flags.StringVar(&config.TranscriptPath, "transcript", config.TranscriptPath, "path to a timecoded transcript .txt file")
	flags.StringVar(&config.XMLPath, "xml", config.XMLPath, "path to a Premiere XML export")
	flags.StringVar(&config.SecondaryTranscriptPath, "transcript-b", config.SecondaryTranscriptPath, "optional second timecoded transcript .txt file")
	flags.StringVar(&config.SecondaryXMLPath, "xml-b", config.SecondaryXMLPath, "optional second Premiere XML export")
	flags.StringVar(&config.SequencePlan, "sequence-plan", config.SequencePlan, "path to an existing _sequence_plan.json file")
	flags.StringVar(&config.Brief, "brief", config.Brief, "creative brief used for generation or assistant context")
	flags.StringVar(&config.OutputDir, "output", config.OutputDir, "directory for BiteBuilder output artifacts")
	flags.StringVar(&config.Model, "model", config.Model, "model name passed to bitebuilder.py")
	flags.StringVar(&config.Host, "host", config.Host, "LLM host URL passed to bitebuilder.py")
	flags.IntVar(&config.TimeoutSeconds, "timeout", config.TimeoutSeconds, "LLM timeout in seconds")
	flags.StringVar(&config.ThinkingMode, "thinking-mode", config.ThinkingMode, "model thinking mode: auto, on, or off")
	flags.StringVar(&config.RefineInstruction, "refine-instruction", config.RefineInstruction, "assistant instruction for refining an existing sequence plan")
	flags.StringVar(&config.OptionID, "option-id", config.OptionID, "sequence-plan option id to render/refine")
	flags.Float64Var(&config.MaxBiteDurationSeconds, "max-bite-duration", config.MaxBiteDurationSeconds, "maximum selected bite duration in seconds for refinement checks")
	flags.Float64Var(&config.MaxTotalDurationSeconds, "max-total-duration", config.MaxTotalDurationSeconds, "maximum selected total duration in seconds for refinement checks")
	flags.BoolVar(&config.RequireChangedSelectedCuts, "require-changed-cuts", config.RequireChangedSelectedCuts, "require refined selected cuts to differ from the source plan option")
	flags.IntVar(&config.RefinementRetries, "refinement-retries", config.RefinementRetries, "retries after a structurally valid refinement fails editorial constraints")

	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return nil
		}
		return err
	}

	options := []tea.ProgramOption{
		tea.WithInput(stdin),
		tea.WithOutput(stdout),
		tea.WithMouseCellMotion(),
	}
	if !*noAltScreen {
		options = append(options, tea.WithAltScreen())
	}

	program := tea.NewProgram(ui.New(ctx, bridge.Runner{}, config), options...)
	if _, err := program.Run(); err != nil {
		return fmt.Errorf("run terminal UI: %w", err)
	}
	return nil
}
