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
	flags.StringVar(&config.Model, "model", config.Model, "model name passed to bitebuilder.py")
	flags.StringVar(&config.Host, "host", config.Host, "LLM host URL passed to bitebuilder.py")
	flags.IntVar(&config.TimeoutSeconds, "timeout", config.TimeoutSeconds, "LLM timeout in seconds")
	flags.StringVar(&config.ThinkingMode, "thinking-mode", config.ThinkingMode, "model thinking mode: auto, on, or off")

	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return nil
		}
		return err
	}

	options := []tea.ProgramOption{
		tea.WithInput(stdin),
		tea.WithOutput(stdout),
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
