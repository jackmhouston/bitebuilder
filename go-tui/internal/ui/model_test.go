package ui

import (
	"context"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/jackmhouston/bitebuilder/go-tui/internal/bridge"
)

type fakeRunner struct {
	calls int
}

func (f *fakeRunner) RunFirstPass(context.Context, bridge.Config) (bridge.RunResult, error) {
	f.calls++
	return bridge.RunResult{Command: "python3 bitebuilder.py", Stdout: "ok"}, nil
}

func TestNewModelViewIncludesReadOnlyWelcome(t *testing.T) {
	runner := &fakeRunner{}
	model := New(context.Background(), runner, bridge.DefaultConfig("/repo"))
	view := model.View()
	for _, want := range []string{"BiteBuilder Go TUI", "Welcome / setup", "Read-only prototype"} {
		if !strings.Contains(view, want) {
			t.Fatalf("View() missing %q: %q", want, view)
		}
	}
	if runner.calls != 0 {
		t.Fatalf("New/View invoked bridge runner %d times, want 0", runner.calls)
	}
}

func TestScreenNavigationShowsPrototypeScreens(t *testing.T) {
	runner := &fakeRunner{}
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig("/repo")))

	cases := []struct {
		key  rune
		want string
	}{
		{'2', "Path / file selection"},
		{'3', "Sequence-plan viewer"},
		{'4', "Bite detail / transcript viewport"},
		{'5', "Transcript viewport"},
		{'h', "Help overlay"},
	}

	for _, tc := range cases {
		updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{tc.key}})
		if cmd != nil {
			t.Fatalf("Update(%q) returned command; navigation should be read-only", string(tc.key))
		}
		model = updated
		view := model.View()
		if !strings.Contains(view, tc.want) {
			t.Fatalf("Update(%q) view missing %q: %q", string(tc.key), tc.want, view)
		}
	}
	if runner.calls != 0 {
		t.Fatalf("navigation invoked bridge runner %d times, want 0", runner.calls)
	}
}

func TestValidateShowsStructuredBridgeErrorWithoutRunning(t *testing.T) {
	runner := &fakeRunner{}
	model := New(context.Background(), runner, bridge.DefaultConfig("/repo"))
	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'v'}})
	if cmd != nil {
		t.Fatal("Update(v) returned command despite read-only validation")
	}
	view := updated.(Model).View()
	for _, want := range []string{"Structured bridge error state", "code:      invalid_request", "transcript path is required"} {
		if !strings.Contains(view, want) {
			t.Fatalf("validation view missing %q: %q", want, view)
		}
	}
	if runner.calls != 0 {
		t.Fatalf("validation invoked bridge runner %d times, want 0", runner.calls)
	}
}

func TestValidatePreviewDoesNotStartSubprocess(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "find one strong proof point"
	model := New(context.Background(), runner, config)

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'v'}})
	if cmd != nil {
		t.Fatal("Update(v) returned command; preview must remain read-only")
	}
	view := updated.(Model).View()
	for _, want := range []string{"Bridge request preview", "bitebuilder.py", "no subprocess was started"} {
		if !strings.Contains(view, want) {
			t.Fatalf("preview view missing %q: %q", want, view)
		}
	}
	if runner.calls != 0 {
		t.Fatalf("preview invoked bridge runner %d times, want 0", runner.calls)
	}
}
