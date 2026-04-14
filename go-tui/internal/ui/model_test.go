package ui

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/jackmhouston/bitebuilder/go-tui/internal/bridge"
)

type fakeRunner struct {
	calls        int
	bridgeCalls  int
	bridgeResult bridge.RunResult
	bridgeErr    error
}

func (f *fakeRunner) RunFirstPass(context.Context, bridge.Config) (bridge.RunResult, error) {
	f.calls++
	return bridge.RunResult{Command: "python3 bitebuilder.py", Stdout: "ok"}, nil
}

func (f *fakeRunner) RunBridgeOperation(_ context.Context, _ bridge.Config, operation string) (bridge.RunResult, error) {
	f.bridgeCalls++
	if f.bridgeResult.Command == "" {
		f.bridgeResult = bridge.RunResult{
			Command: "python3 bitebuilder.py --go-tui-bridge " + operation,
			Stdout:  `{"ok":true,"data":{"suggestion":"Suggested Creative Brief:\nMake it concise."}}`,
		}
	}
	return f.bridgeResult, f.bridgeErr
}

func TestNewModelViewIncludesReadOnlyWelcome(t *testing.T) {
	runner := &fakeRunner{}
	model := New(context.Background(), runner, bridge.DefaultConfig("/repo"))
	view := model.View()
	for _, want := range []string{"BiteBuilder Go TUI", "Welcome / setup", "interactive BiteBuilder workspace"} {
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
			t.Fatalf("Update(%q) returned command; navigation should not start commands", string(tc.key))
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
		t.Fatal("Update(v) returned command despite missing required assistant inputs")
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

func TestValidateRunsAssistantBridgeAndDisplaysSuggestion(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "find one strong proof point"
	model := tea.Model(New(context.Background(), runner, config))

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'v'}})
	if cmd == nil {
		t.Fatal("Update(v) command = nil, want assistant bridge command")
	}
	model = updated
	model, _ = model.Update(cmd())
	view := model.View()
	for _, want := range []string{"Model assistant suggestion", "Suggested Creative Brief:", "Make it concise."} {
		if !strings.Contains(view, want) {
			t.Fatalf("assistant view missing %q: %q", want, view)
		}
	}
	if runner.bridgeCalls != 1 {
		t.Fatalf("bridge calls = %d, want 1", runner.bridgeCalls)
	}
}

func TestAcceptAssistantSuggestionUpdatesBriefField(t *testing.T) {
	runner := &fakeRunner{}
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig("/repo")))
	model, _ = model.Update(bridgeFinishedMsg{
		operation: "assistant",
		result: bridge.RunResult{
			Command: "python3 bitebuilder.py --go-tui-bridge assistant",
			Stdout:  `{"ok":true,"data":{"suggestion":"Suggested Creative Brief:\nMake a concise narrative.\n\nWhy This Direction Works:\nIt fits."}}`,
		},
	})

	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'a'}})
	accepted := model.(Model)
	if got := accepted.brief.Value(); got != "Make a concise narrative." {
		t.Fatalf("brief = %q, want accepted suggested brief", got)
	}
	if accepted.activeScreen != screenFiles {
		t.Fatalf("activeScreen = %v, want screenFiles", accepted.activeScreen)
	}
}

func TestExtractSuggestedBriefFallsBackToWholeSuggestion(t *testing.T) {
	if got := extractSuggestedBrief("Use the strongest proof point."); got != "Use the strongest proof point." {
		t.Fatalf("fallback extracted %q", got)
	}
}

func TestBriefTextareaAcceptsGlobalHotkeyCharacters(t *testing.T) {
	runner := &fakeRunner{}
	model := New(context.Background(), runner, bridge.DefaultConfig("/repo"))
	model.activeScreen = screenFiles
	model.focus = 2
	model.blurFocused()
	model.focusFocused()

	for _, r := range []rune("qhvTX") {
		updated, cmd := tea.Model(model).Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{r}})
		model = updated.(Model)
		if cmd != nil {
			// Textarea may return cursor blink commands; executing them is not needed here.
		}
	}
	if got := model.brief.Value(); got != "qhvTX" {
		t.Fatalf("brief value = %q, want hotkey characters typed into textarea", got)
	}
	if runner.bridgeCalls != 0 {
		t.Fatalf("typing invoked bridge %d times, want 0", runner.bridgeCalls)
	}
}

func TestBrowseTranscriptStartsFilePicker(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig(t.TempDir())
	model := tea.Model(New(context.Background(), runner, config))

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'T'}})
	if cmd == nil {
		t.Fatal("Update(T) command = nil, want file picker init command")
	}

	browsing := updated.(Model)
	if runtime.GOOS == "darwin" {
		if browsing.picking != pickNone {
			t.Fatalf("picking = %v, want pickNone while Finder command is running", browsing.picking)
		}
		if !strings.Contains(browsing.View(), "Opening Finder to choose a transcript .txt file") {
			t.Fatalf("Finder browse view missing status: %q", browsing.View())
		}
	} else {
		if browsing.picking != pickTranscript {
			t.Fatalf("picking = %v, want pickTranscript", browsing.picking)
		}
		for _, want := range []string{"Browse transcript (.txt)", "Browsing for a transcript .txt file", "q cancels"} {
			if !strings.Contains(browsing.View(), want) {
				t.Fatalf("browse view missing %q: %q", want, browsing.View())
			}
		}
	}
	if runner.calls != 0 {
		t.Fatalf("browse invoked bridge runner %d times, want 0", runner.calls)
	}
}

func TestNativeFilePickedMessagePopulatesPath(t *testing.T) {
	runner := &fakeRunner{}
	root := t.TempDir()
	transcriptPath := filepath.Join(root, "interview.txt")
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig(root)))

	updated, cmd := model.Update(nativeFilePickedMsg{target: pickTranscript, path: transcriptPath})
	if cmd != nil {
		t.Fatal("nativeFilePickedMsg returned command")
	}
	got := updated.(Model).transcript.Value()
	if got != transcriptPath {
		t.Fatalf("transcript path = %q, want %q", got, transcriptPath)
	}
}

func TestApplyPickedFilesPopulatePathFields(t *testing.T) {
	runner := &fakeRunner{}
	root := t.TempDir()
	transcriptPath := filepath.Join(root, "interview.txt")
	xmlPath := filepath.Join(root, "source.xml")
	if err := os.WriteFile(transcriptPath, []byte("transcript"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(xmlPath, []byte("<xml/>"), 0o644); err != nil {
		t.Fatal(err)
	}
	model := New(context.Background(), runner, bridge.DefaultConfig(root))

	model = model.startPicking(pickTranscript, []string{".txt"}, "")
	model = model.applyPickedFile(transcriptPath)
	if got := model.transcript.Value(); got != transcriptPath {
		t.Fatalf("transcript path = %q, want %q", got, transcriptPath)
	}

	model = model.startPicking(pickXML, []string{".xml"}, "")
	model = model.applyPickedFile(xmlPath)
	if got := model.xml.Value(); got != xmlPath {
		t.Fatalf("XML path = %q, want %q", got, xmlPath)
	}
	if model.picking != pickNone {
		t.Fatalf("picking = %v, want pickNone after selection", model.picking)
	}
	if runner.calls != 0 {
		t.Fatalf("file picking invoked bridge runner %d times, want 0", runner.calls)
	}
}
