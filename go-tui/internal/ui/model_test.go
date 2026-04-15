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
	calls            int
	bridgeCalls      int
	generationCalls  int
	exportCalls      int
	bridgeResult     bridge.RunResult
	bridgeErr        error
	bridgeConfigs    []bridge.Config
	bridgeOperations []string
	generationResult bridge.RunResult
	generationErr    error
	exportResult     bridge.RunResult
	exportErr        error
	exportConfigs    []bridge.Config
}

func (f *fakeRunner) RunFirstPass(context.Context, bridge.Config) (bridge.RunResult, error) {
	f.calls++
	return bridge.RunResult{Command: "python3 bitebuilder.py", Stdout: "ok"}, nil
}

func (f *fakeRunner) RunBridgeOperation(_ context.Context, config bridge.Config, operation string) (bridge.RunResult, error) {
	f.bridgeCalls++
	f.bridgeOperations = append(f.bridgeOperations, operation)
	f.bridgeConfigs = append(f.bridgeConfigs, config)
	if f.bridgeResult.Command == "" {
		f.bridgeResult = bridge.RunResult{
			Command: "python3 bitebuilder.py --go-tui-bridge " + operation,
			Stdout:  `{"ok":true,"data":{"suggestion":"Suggested Creative Brief:\nMake it concise."}}`,
		}
	}
	return f.bridgeResult, f.bridgeErr
}

func (f *fakeRunner) RunGeneration(context.Context, bridge.Config) (bridge.RunResult, error) {
	f.generationCalls++
	if f.generationResult.Command == "" {
		f.generationResult = bridge.RunResult{
			Command: "python3 bitebuilder.py --go-tui-generate",
			Stdout: strings.Join([]string{
				`{"event":"started","request_id":"req-1","schema_version":"go_tui_generation_events.v1","stage":"setup","message":"starting"}`,
				`{"event":"progress","message":"Writing output files.","request_id":"req-1","schema_version":"go_tui_generation_events.v1","stage":"output"}`,
				`{"event":"artifact","kind":"sequence_plan","path":"out/_sequence_plan.json","request_id":"req-1","schema_version":"go_tui_generation_events.v1"}`,
				`{"event":"artifact","kind":"xmeml","path":"out/option-1.xml","request_id":"req-1","schema_version":"go_tui_generation_events.v1"}`,
				`{"event":"completed","ok":true,"request_id":"req-1","schema_version":"go_tui_generation_events.v1","stage":"complete","data":{"output_file_count":1}}`,
			}, "\n"),
		}
	}
	return f.generationResult, f.generationErr
}

func (f *fakeRunner) RunExport(_ context.Context, config bridge.Config) (bridge.RunResult, error) {
	f.exportCalls++
	f.exportConfigs = append(f.exportConfigs, config)
	if f.exportResult.Command == "" {
		f.exportResult = bridge.RunResult{
			Command: "python3 bitebuilder.py --go-tui-export",
			Stdout: strings.Join([]string{
				`{"event":"started","request_id":"req-export","schema_version":"go_tui_generation_events.v1","stage":"start","message":"starting"}`,
				`{"event":"artifact","kind":"xmeml","path":"out/selected.xml","request_id":"req-export","schema_version":"go_tui_generation_events.v1"}`,
				`{"event":"completed","ok":true,"request_id":"req-export","schema_version":"go_tui_generation_events.v1","stage":"complete","data":{"output_path":"out/selected.xml"}}`,
			}, "\n"),
		}
	}
	return f.exportResult, f.exportErr
}

func TestNewModelViewIncludesReadOnlyWelcome(t *testing.T) {
	runner := &fakeRunner{}
	model := New(context.Background(), runner, bridge.DefaultConfig("/repo"))
	view := model.View()
	for _, want := range []string{"BiteBuilder Go TUI", "Setup / file selection", "Source A"} {
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
		{'2', "Setup / file selection"},
		{'3', "Editorial workspace"},
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

func TestMouseNavigationClicksSwitchScreens(t *testing.T) {
	runner := &fakeRunner{}
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig("/repo")))

	updated, cmd := model.Update(tea.MouseMsg{
		X:      14,
		Y:      navRow,
		Button: tea.MouseButtonLeft,
		Action: tea.MouseActionPress,
	})
	if cmd != nil {
		t.Fatal("Files nav mouse click returned command")
	}
	if got := updated.(Model).activeScreen; got != screenFiles {
		t.Fatalf("activeScreen = %v, want screenFiles", got)
	}
}

func TestMouseClickOnFileRowsStartsFinderOrPicker(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig(t.TempDir())
	model := tea.Model(New(context.Background(), runner, config))
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'2'}})

	updated, cmd := model.Update(tea.MouseMsg{
		X:      5,
		Y:      filesTranscriptA,
		Button: tea.MouseButtonLeft,
		Action: tea.MouseActionPress,
	})
	if cmd == nil {
		t.Fatal("transcript row mouse click returned nil command")
	}
	browsing := updated.(Model)
	if runtime.GOOS == "darwin" {
		if browsing.picking != pickNone {
			t.Fatalf("picking = %v, want pickNone while Finder command is running", browsing.picking)
		}
		if !strings.Contains(browsing.View(), "Opening Finder to choose transcript A .txt file") {
			t.Fatalf("Finder status missing from view: %q", browsing.View())
		}
	} else if browsing.picking != pickTranscript {
		t.Fatalf("picking = %v, want pickTranscript", browsing.picking)
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

func TestAssistantChatLoopSendsFollowUpWithConversationContext(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "find one strong proof point"
	model := tea.Model(New(context.Background(), runner, config))

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'v'}})
	if cmd == nil {
		t.Fatal("Update(v) command = nil, want initial assistant chat command")
	}
	model = updated
	model, _ = model.Update(cmd())
	afterFirst := model.(Model)
	if afterFirst.activeScreen != screenAssistant {
		t.Fatalf("activeScreen = %v, want screenAssistant", afterFirst.activeScreen)
	}
	if got := len(afterFirst.assistantChat); got != 2 {
		t.Fatalf("assistant chat length = %d, want user+assistant messages", got)
	}
	for _, want := range []string{"Model assistant chat loop", "Conversation", "Suggested Creative Brief:"} {
		if !strings.Contains(afterFirst.View(), want) {
			t.Fatalf("assistant chat view missing %q: %q", want, afterFirst.View())
		}
	}

	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune("Make it punchier")})
	model, cmd = model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd == nil {
		t.Fatal("Enter command = nil, want follow-up assistant chat command")
	}
	model, _ = model.Update(cmd())
	finished := model.(Model)
	if runner.bridgeCalls != 2 {
		t.Fatalf("bridge calls = %d, want 2", runner.bridgeCalls)
	}
	if len(runner.bridgeConfigs) != 2 {
		t.Fatalf("captured bridge configs = %d, want 2", len(runner.bridgeConfigs))
	}
	followUpBrief := runner.bridgeConfigs[1].Brief
	for _, want := range []string{
		"Current creative ask:\nfind one strong proof point",
		"Assistant chat so far:",
		"Suggested Creative Brief:",
		"Latest user request:\nMake it punchier",
	} {
		if !strings.Contains(followUpBrief, want) {
			t.Fatalf("follow-up bridge brief missing %q: %q", want, followUpBrief)
		}
	}
	if got := finished.assistantInput.Value(); got != "" {
		t.Fatalf("assistant input = %q, want cleared after send", got)
	}
	if got := len(finished.assistantChat); got != 4 {
		t.Fatalf("assistant chat length = %d, want two user+assistant turns", got)
	}
}

func TestSummaryBridgeStoresAndRendersWorkspaceSummary(t *testing.T) {
	runner := &fakeRunner{
		bridgeResult: bridge.RunResult{
			Command: "python3 bitebuilder.py --go-tui-bridge summary",
			Stdout:  `{"ok":true,"schema_version":"go_tui_bridge.v1","operation":"summary","data":{"summary_text":"Interview covers origin, technical proof, and resolution."}}`,
		},
	}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	model := tea.Model(New(context.Background(), runner, config))

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'s'}})
	if cmd == nil {
		t.Fatal("Update(s) command = nil, want summary bridge command")
	}
	if !updated.(Model).summaryRunning {
		t.Fatal("summaryRunning = false, want true")
	}

	model, _ = updated.Update(cmd())
	finished := model.(Model)
	if got := runner.bridgeOperations[0]; got != "summary" {
		t.Fatalf("bridge operation = %q, want summary", got)
	}
	if !strings.Contains(finished.workspaceContent(), "Interview covers origin") {
		t.Fatalf("workspace missing summary: %q", finished.workspaceContent())
	}
}

func TestAskFocusedBiteUsesAssistantContextWithoutLeavingWorkspace(t *testing.T) {
	runner := &fakeRunner{
		bridgeResult: bridge.RunResult{
			Command: "python3 bitebuilder.py --go-tui-bridge assistant",
			Stdout:  `{"ok":true,"data":{"suggestion":"This bite fits because it resolves the ask."}}`,
		},
	}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "make a proof point"
	model := New(context.Background(), runner, config)
	model.transcriptSummary = "The interview covers a problem and proof."
	model.activeScreen = screenPlan

	updated, cmd := tea.Model(model).Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'o'}})
	if cmd == nil {
		t.Fatal("Update(o) command = nil, want assistant question command")
	}
	running := updated.(Model)
	if running.activeScreen != screenPlan {
		t.Fatalf("activeScreen while asking = %v, want workspace", running.activeScreen)
	}
	if len(runner.bridgeConfigs) != 0 {
		t.Fatal("assistant runner called before command execution")
	}

	modelAfter, _ := updated.Update(cmd())
	finished := modelAfter.(Model)
	if runner.bridgeOperations[0] != "assistant" {
		t.Fatalf("operation = %q, want assistant", runner.bridgeOperations[0])
	}
	brief := runner.bridgeConfigs[0].Brief
	for _, want := range []string{"Current creative ask:\nmake a proof point", "Transcript summary:\nThe interview covers", "Focused selected bite:", "Opening proof point"} {
		if !strings.Contains(brief, want) {
			t.Fatalf("assistant prompt missing %q: %q", want, brief)
		}
	}
	if finished.activeScreen != screenPlan {
		t.Fatalf("activeScreen after reply = %v, want workspace", finished.activeScreen)
	}
	if !strings.Contains(finished.workspaceContent(), "This bite fits") {
		t.Fatalf("workspace missing assistant answer: %q", finished.workspaceContent())
	}
}

func TestGenerateRunsNDJSONBridgeAndDisplaysArtifacts(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "find one strong proof point"
	model := tea.Model(New(context.Background(), runner, config))

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'g'}})
	if cmd == nil {
		t.Fatal("Update(g) command = nil, want generation command")
	}
	running := updated.(Model)
	if !running.generationRunning || !strings.Contains(running.generationPreview, "--go-tui-generate") {
		t.Fatalf("running generation state missing preview: %#v", running)
	}

	model = updated
	model, _ = model.Update(cmd())
	finished := model.(Model)
	content := finished.workspaceContent()
	for _, want := range []string{"Editorial workspace", "artifact[sequence_plan]: out/_sequence_plan.json", "artifact[xmeml]: out/option-1.xml", "completed:"} {
		if !strings.Contains(content, want) {
			t.Fatalf("generation content missing %q: %q", want, content)
		}
	}
	if runner.generationCalls != 1 {
		t.Fatalf("generation calls = %d, want 1", runner.generationCalls)
	}
}

func TestGenerationIgnoresSelectedBoardValidationUntilExport(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "find proof"
	model := New(context.Background(), runner, config)
	model.board.Selected[0].TCOut = "00:00:00:00"
	model.board.Selected[0].Timecode = "00:00:00:00 - 00:00:00:00"

	_, cmd := tea.Model(model).Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'g'}})
	if cmd == nil {
		t.Fatal("generation command = nil, want generation to ignore selected-board export validation")
	}
	if runner.generationCalls != 0 {
		t.Fatalf("generation calls before command execution = %d, want 0", runner.generationCalls)
	}
}

func TestGenerateShowsStructuredValidationErrorWithoutRunning(t *testing.T) {
	runner := &fakeRunner{}
	model := New(context.Background(), runner, bridge.DefaultConfig("/repo"))
	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'g'}})
	if cmd != nil {
		t.Fatal("Update(g) returned command despite missing required generation inputs")
	}
	view := updated.(Model).View()
	for _, want := range []string{"Structured bridge error state", "operation: generate", "transcript path is required"} {
		if !strings.Contains(view, want) {
			t.Fatalf("generation validation view missing %q: %q", want, view)
		}
	}
	if runner.generationCalls != 0 {
		t.Fatalf("validation invoked generation runner %d times, want 0", runner.generationCalls)
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
	model.focus = 4
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
		if !strings.Contains(browsing.View(), "Opening Finder to choose transcript A .txt file") {
			t.Fatalf("Finder browse view missing status: %q", browsing.View())
		}
	} else {
		if browsing.picking != pickTranscript {
			t.Fatalf("picking = %v, want pickTranscript", browsing.picking)
		}
		for _, want := range []string{"Browse transcript A (.txt)", "Browsing for transcript A .txt file", "q cancels"} {
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

func TestGenerateRunsGenerationBridgeAndDisplaysEvents(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "find proof"
	model := tea.Model(New(context.Background(), runner, config))

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'g'}})
	if cmd == nil {
		t.Fatal("Update(g) command = nil, want generation bridge command")
	}
	running := updated.(Model)
	if !running.generationRunning || !strings.Contains(running.generationPreview, "--go-tui-generate") {
		t.Fatalf("generation running state missing preview: %#v", running)
	}

	model = updated
	model, _ = model.Update(cmd())
	finished := model.(Model)
	if finished.generationRunning {
		t.Fatal("generation still running after completion message")
	}
	if runner.generationCalls != 1 {
		t.Fatalf("generation calls = %d, want 1", runner.generationCalls)
	}
	view := finished.workspaceContent()
	for _, want := range []string{"Generation events", "started", "setup", "Candidate bites"} {
		if !strings.Contains(view, want) {
			t.Fatalf("generation view missing %q: %q", want, view)
		}
	}
}

func TestGenerationHydratesBoardFromBackendEventData(t *testing.T) {
	runner := &fakeRunner{}
	runner.generationResult = bridge.RunResult{
		Command: "python3 bitebuilder.py --go-tui-generate",
		Stdout: strings.Join([]string{
			`{"event":"started","request_id":"req-board","schema_version":"go_tui_generation_events.v1","stage":"setup","message":"starting"}`,
			`{"event":"completed","ok":true,"request_id":"req-board","schema_version":"go_tui_generation_events.v1","stage":"complete","data":{"candidate_bites":[{"id":"cand-77","label":"Backend candidate","segment":7,"timecode":"00:00:07:00 - 00:00:12:00","text":"Backend candidate text.","purpose":"HOOK","rationale":"Backend candidate rationale.","status":"candidate"}],"selected_bites":[{"id":"sel-88","label":"Backend selected","segment":8,"timecode":"00:00:12:00 - 00:00:18:00","text":"Backend selected text.","purpose":"PROOF","rationale":"Backend selected rationale.","status":"selected"}]}}`,
		}, "\n"),
	}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "find proof"
	model := tea.Model(New(context.Background(), runner, config))
	model, _ = model.Update(tea.WindowSizeMsg{Width: 120, Height: 32})

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'g'}})
	if cmd == nil {
		t.Fatal("Update(g) command = nil, want generation bridge command")
	}
	model = updated
	model, _ = model.Update(cmd())
	finished := model.(Model)
	if got := finished.board.Candidates[0].ID; got != "cand-77" {
		t.Fatalf("candidate ID = %q, want backend candidate", got)
	}
	if got := finished.board.Selected[0].ID; got != "sel-88" {
		t.Fatalf("selected ID = %q, want backend selected", got)
	}
	view := finished.workspaceContent()
	for _, want := range []string{"Backend candidate", "Backend candidate rationale", "Backend selected", "Generation completed; board hydrated"} {
		if !strings.Contains(view, want) {
			t.Fatalf("hydrated generation view missing %q: %q", want, view)
		}
	}

	model, cmd = model.Update(tea.KeyMsg{Type: tea.KeySpace, Runes: []rune{' '}})
	if cmd != nil {
		t.Fatal("selecting hydrated candidate returned command")
	}
	selected := model.(Model)
	if got := len(selected.board.Selected); got != 2 {
		t.Fatalf("selected bite count after adding hydrated candidate = %d, want 2", got)
	}
	if got := selected.board.Selected[1].ID; got != "cand-77" {
		t.Fatalf("added selected ID = %q, want hydrated candidate", got)
	}
}

func TestBiteBoardRendersCandidateAndSelectedColumns(t *testing.T) {
	runner := &fakeRunner{}
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig("/repo")))

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'3'}})
	if cmd != nil {
		t.Fatalf("Update(3) returned command; board navigation should be local")
	}
	view := updated.(Model).workspaceContent()
	for _, want := range []string{"Editorial workspace", "Candidate bites", "Problem setup", "Rationale:", "Introduces the story problem", "Selected cut", "Opening proof point", "space delete/add"} {
		if !strings.Contains(view, want) {
			t.Fatalf("board view missing %q: %q", want, view)
		}
	}
	if runner.calls != 0 || runner.bridgeCalls != 0 {
		t.Fatalf("board render invoked runner calls=%d bridgeCalls=%d, want no bridge work", runner.calls, runner.bridgeCalls)
	}
}

func TestBiteBoardSelectsAndReordersCandidates(t *testing.T) {
	runner := &fakeRunner{}
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig("/repo")))
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'3'}})

	model, cmd := model.Update(tea.KeyMsg{Type: tea.KeySpace, Runes: []rune{' '}})
	if cmd != nil {
		t.Fatal("selecting a candidate returned command")
	}
	selected := model.(Model)
	if got := len(selected.board.Selected); got != 2 {
		t.Fatalf("selected bite count = %d, want 2", got)
	}
	if got := selected.board.Selected[1].ID; got != "candidate-001" {
		t.Fatalf("new selected bite ID = %q, want candidate-001", got)
	}

	model, cmd = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'u'}})
	if cmd != nil {
		t.Fatal("reordering selected bite returned command")
	}
	reordered := model.(Model)
	if got := reordered.board.Selected[0].ID; got != "candidate-001" {
		t.Fatalf("selected order first ID = %q, want candidate-001 after move up", got)
	}
	if reordered.board.SelectedIndex != 0 {
		t.Fatalf("selected index = %d, want 0 after move up", reordered.board.SelectedIndex)
	}
}

func TestBiteBoardReplaceAndEditSelectedLabelPurposeAndNotes(t *testing.T) {
	runner := &fakeRunner{}
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig("/repo")))
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'3'}})
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'j'}})

	model, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'r'}})
	if cmd != nil {
		t.Fatal("replacing selected bite returned command")
	}
	replaced := model.(Model)
	if got := replaced.board.Selected[0].ID; got != "candidate-002" {
		t.Fatalf("replaced selected ID = %q, want candidate-002", got)
	}
	if got := replaced.board.Selected[0].Status; got != "replacement" {
		t.Fatalf("replacement status = %q, want replacement", got)
	}
	if got := replaced.board.Selected[0].ReplacesID; got != "selected-001" {
		t.Fatalf("replacement ReplacesID = %q, want selected-001", got)
	}

	model, cmd = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'e'}})
	if cmd != nil {
		t.Fatal("starting edit returned command")
	}
	editing := model.(Model)
	if !editing.board.Editing || editing.activeScreen != screenBite {
		t.Fatalf("editing=%v activeScreen=%v, want editing bite screen", editing.board.Editing, editing.activeScreen)
	}

	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(" for final cut")})
	model, cmd = model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd != nil {
		t.Fatal("saving edit returned command")
	}
	saved := model.(Model)
	if saved.board.Editing {
		t.Fatal("board still editing after Enter")
	}
	if got := saved.board.Selected[0].Purpose; !strings.Contains(got, "for final cut") {
		t.Fatalf("edited purpose = %q, want typed suffix", got)
	}
	if view := saved.View(); !strings.Contains(view, "for final cut") {
		t.Fatalf("bite detail view missing edited purpose: %q", view)
	}

	model, cmd = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'l'}})
	if cmd != nil {
		t.Fatal("starting label edit returned command")
	}
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(" revised")})
	model, cmd = model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd != nil {
		t.Fatal("saving label edit returned command")
	}
	saved = model.(Model)
	if got := saved.board.Selected[0].Label; !strings.Contains(got, "revised") {
		t.Fatalf("edited label = %q, want typed suffix", got)
	}

	model, cmd = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}})
	if cmd != nil {
		t.Fatal("starting notes edit returned command")
	}
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(" with clearer rationale")})
	model, cmd = model.Update(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd != nil {
		t.Fatal("saving notes edit returned command")
	}
	saved = model.(Model)
	if got := saved.board.Selected[0].Rationale; !strings.Contains(got, "clearer rationale") {
		t.Fatalf("edited notes = %q, want typed suffix", got)
	}
	if view := saved.View(); !strings.Contains(view, "clearer rationale") {
		t.Fatalf("bite detail view missing edited notes: %q", view)
	}
}

func TestBiteBoardTrimsSelectedStartAndEndTimecodes(t *testing.T) {
	runner := &fakeRunner{}
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig("/repo")))
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'4'}})

	model, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}})
	if cmd != nil {
		t.Fatal("starting trim edit returned command")
	}
	trimming := model.(Model)
	if !trimming.trimEditing || trimming.activeScreen != screenBite {
		t.Fatalf("trimEditing=%v activeScreen=%v, want trim editor on bite screen", trimming.trimEditing, trimming.activeScreen)
	}
	if got := trimming.trimStart.Value(); got != "00:00:00:00" {
		t.Fatalf("trim start = %q, want existing start timecode", got)
	}
	if got := trimming.trimEnd.Value(); got != "00:00:08:00" {
		t.Fatalf("trim end = %q, want existing end timecode", got)
	}

	trimming.trimStart.SetValue("00:00:01:00")
	trimming.trimEnd.SetValue("00:00:07:12")
	model, cmd = tea.Model(trimming).Update(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd != nil {
		t.Fatal("saving trim edit returned command")
	}
	saved := model.(Model)
	if saved.trimEditing {
		t.Fatal("trim editor still open after saving valid trim")
	}
	selected := saved.board.Selected[0]
	if selected.TCIn != "00:00:01:00" || selected.TCOut != "00:00:07:12" {
		t.Fatalf("selected trim = %s - %s, want saved start/end", selected.TCIn, selected.TCOut)
	}
	if got := selected.Timecode; got != "00:00:01:00 - 00:00:07:12" {
		t.Fatalf("selected timecode = %q, want joined trimmed range", got)
	}
	if view := saved.View(); !strings.Contains(view, "00:00:01:00 - 00:00:07:12") {
		t.Fatalf("bite detail view missing trimmed timecode: %q", view)
	}
}

func TestInvalidBiteTrimIsBlockedWithInlineValidationError(t *testing.T) {
	runner := &fakeRunner{}
	model := New(context.Background(), runner, bridge.DefaultConfig("/repo"))
	model = model.startBiteTrimEdit()
	model.trimStart.SetValue("00:00:08:00")
	model.trimEnd.SetValue("00:00:07:12")

	updated, cmd := tea.Model(model).Update(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd != nil {
		t.Fatal("invalid trim save returned command")
	}
	blocked := updated.(Model)
	if !blocked.trimEditing {
		t.Fatal("trim editor closed despite invalid trim")
	}
	if got := blocked.board.Selected[0].Timecode; got != "00:00:00:00 - 00:00:08:00" {
		t.Fatalf("selected timecode mutated to %q, want original after blocked invalid trim", got)
	}
	for _, want := range []string{
		"Validation: Start timecode must be before end timecode.",
		"Invalid trim; fix the inline validation error before saving.",
	} {
		if !strings.Contains(blocked.View(), want) {
			t.Fatalf("invalid trim view missing %q: %q", want, blocked.View())
		}
	}
}

func TestBiteBoardEditsLabelNotesAndTrimTimecodes(t *testing.T) {
	runner := &fakeRunner{}
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig("/repo")))
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'3'}})

	model, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'l'}})
	if cmd != nil {
		t.Fatal("starting label edit returned command")
	}
	editing := model.(Model)
	editing.biteEdit.SetValue("Cold open")
	model, cmd = tea.Model(editing).Update(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd != nil {
		t.Fatal("saving label edit returned command")
	}
	edited := model.(Model)
	if got := edited.board.Selected[0].Label; got != "Cold open" {
		t.Fatalf("label = %q, want edited label", got)
	}

	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'n'}})
	editing = model.(Model)
	editing.biteEdit.SetValue("Trimmed for pace.")
	model, _ = tea.Model(editing).Update(tea.KeyMsg{Type: tea.KeyEnter})
	edited = model.(Model)
	if got := edited.board.Selected[0].Rationale; got != "Trimmed for pace." {
		t.Fatalf("notes/rationale = %q, want edited notes", got)
	}

	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'['}})
	editing = model.(Model)
	editing.biteEdit.SetValue("00:00:01:00")
	model, _ = tea.Model(editing).Update(tea.KeyMsg{Type: tea.KeyEnter})
	edited = model.(Model)
	if got := edited.board.Selected[0].TCIn; got != "00:00:01:00" {
		t.Fatalf("trim start = %q, want edited trim start", got)
	}
	if got := edited.board.Selected[0].Timecode; got != "00:00:01:00 - 00:00:08:00" {
		t.Fatalf("timecode = %q, want recomputed range", got)
	}
	if view := edited.View(); !strings.Contains(view, "Cold open") || !strings.Contains(view, "00:00:01:00 - 00:00:08:00") {
		t.Fatalf("view missing edited label/trim: %q", view)
	}
}

func TestInvalidTrimBlocksEditAndExport(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "find proof"
	model := tea.Model(New(context.Background(), runner, config))
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'4'}})

	model, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{']'}})
	if cmd != nil {
		t.Fatal("starting trim end edit returned command")
	}
	editing := model.(Model)
	editing.biteEdit.SetValue("00:00:00:00")
	model, cmd = tea.Model(editing).Update(tea.KeyMsg{Type: tea.KeyEnter})
	if cmd != nil {
		t.Fatal("invalid trim save returned command")
	}
	blocked := model.(Model)
	if !blocked.board.Editing {
		t.Fatal("invalid trim save ended edit mode; want blocked inline")
	}
	if !strings.Contains(blocked.board.ValidationErr, "trim start must be before trim end") {
		t.Fatalf("validation error = %q, want trim ordering error", blocked.board.ValidationErr)
	}
	if !strings.Contains(blocked.View(), "Validation: trim start must be before trim end") {
		t.Fatalf("inline validation missing from view: %q", blocked.View())
	}

	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyEsc})
	blocked = model.(Model)
	blocked.board.Selected[0].TCOut = "00:00:00:00"
	blocked.board.Selected[0].Timecode = "00:00:00:00 - 00:00:00:00"
	model, cmd = tea.Model(blocked).Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'x'}})
	if cmd != nil {
		t.Fatal("export returned command despite invalid trim")
	}
	disabled := model.(Model)
	if runner.exportCalls != 0 {
		t.Fatalf("export calls = %d, want export disabled before Python subprocess", runner.exportCalls)
	}
	if !strings.Contains(disabled.status, "Export disabled") || !strings.Contains(disabled.View(), "Export disabled") {
		t.Fatalf("export disabled state missing: status=%q view=%q", disabled.status, disabled.View())
	}
}

func TestExportRunsPythonWithSelectedBoardIntent(t *testing.T) {
	runner := &fakeRunner{}
	config := bridge.DefaultConfig("/repo")
	config.TranscriptPath = "transcript.txt"
	config.XMLPath = "source.xml"
	config.Brief = "find proof"
	config.SequencePlan = "out/_sequence_plan.json"
	model := tea.Model(New(context.Background(), runner, config))
	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'3'}})

	updated, cmd := model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'x'}})
	if cmd == nil {
		t.Fatal("Update(x) command = nil, want export command")
	}
	running := updated.(Model)
	if !running.exportRunning || !strings.Contains(running.exportPreview, "--go-tui-export") {
		t.Fatalf("export running state missing preview: %#v", running)
	}
	if len(runner.exportConfigs) != 0 {
		t.Fatal("export runner called before command execution")
	}

	model, _ = updated.Update(cmd())
	finished := model.(Model)
	if runner.exportCalls != 1 {
		t.Fatalf("export calls = %d, want 1", runner.exportCalls)
	}
	selectedJSON := runner.exportConfigs[0].SelectedBoardJSON
	for _, want := range []string{`"selected_bites"`, `"bite_id":"selected-001"`, `"tc_in":"00:00:00:00"`, `"tc_out":"00:00:08:00"`} {
		if !strings.Contains(selectedJSON, want) {
			t.Fatalf("SelectedBoardJSON missing %q: %s", want, selectedJSON)
		}
	}
	if !strings.Contains(finished.workspaceContent(), "Latest export: out/selected.xml") {
		t.Fatalf("workspace missing latest export: %q", finished.workspaceContent())
	}
}

func TestBiteDetailShowsSelectedAndCandidateRationale(t *testing.T) {
	runner := &fakeRunner{}
	model := tea.Model(New(context.Background(), runner, bridge.DefaultConfig("/repo")))

	model, _ = model.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'4'}})
	view := model.View()
	for _, want := range []string{"Bite detail / transcript viewport", "Notes:    Starts with the clearest setup"} {
		if !strings.Contains(view, want) {
			t.Fatalf("bite detail view missing %q: %q", want, view)
		}
	}
}
