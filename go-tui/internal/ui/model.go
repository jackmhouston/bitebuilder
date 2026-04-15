package ui

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/charmbracelet/bubbles/filepicker"
	"github.com/charmbracelet/bubbles/key"
	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/textinput"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/jackmhouston/bitebuilder/go-tui/internal/bridge"
)

const fieldCount = 6
const (
	navRow             = 2
	bodyContentRow     = 4
	filesTranscriptA   = bodyContentRow + 3
	filesXMLA          = bodyContentRow + 6
	filesTranscriptB   = bodyContentRow + 9
	filesXMLB          = bodyContentRow + 12
)

type firstPassRunner interface {
	RunFirstPass(context.Context, bridge.Config) (bridge.RunResult, error)
	RunBridgeOperation(context.Context, bridge.Config, string) (bridge.RunResult, error)
	RunGeneration(context.Context, bridge.Config) (bridge.RunResult, error)
	RunExport(context.Context, bridge.Config) (bridge.RunResult, error)
}

type screen int

const (
	screenWelcome screen = iota
	screenFiles
	screenPlan
	screenAssistant
	screenBite
	screenTranscript
)

type pickTarget int

const (
	pickNone pickTarget = iota
	pickTranscript
	pickXML
	pickTranscriptB
	pickXMLB
)

type bridgeErrorState struct {
	Operation string
	Code      string
	Message   string
	Hint      string
}

type chatMessage struct {
	Role string
	Text string
}

type nativeFilePickedMsg struct {
	target pickTarget
	path   string
}

type nativeFilePickErrorMsg struct {
	target pickTarget
	err    error
}

type bridgeFinishedMsg struct {
	operation string
	result    bridge.RunResult
	err       error
}

type generationFinishedMsg struct {
	result bridge.RunResult
	err    error
}

type exportFinishedMsg struct {
	result bridge.RunResult
	err    error
}

type boardColumn int

const (
	boardCandidates boardColumn = iota
	boardSelected
)

type biteCard struct {
	ID         string
	Label      string
	Segment    int
	TCIn       string
	TCOut      string
	Timecode   string
	Text       string
	Purpose    string
	Rationale  string
	Status     string
	ReplacesID string
}

type biteEditMode int

const (
	biteEditNone biteEditMode = iota
	biteEditPurpose
	biteEditLabel
	biteEditNotes
	biteEditTrimStart
	biteEditTrimEnd
)

type biteBoardState struct {
	Candidates     []biteCard
	Selected       []biteCard
	FocusColumn    boardColumn
	CandidateIndex int
	SelectedIndex  int
	Editing        bool
	EditMode       biteEditMode
	ValidationErr  string
}

// Model is the Bubble Tea state for BiteBuilder's Go TUI.
type Model struct {
	ctx    context.Context
	runner firstPassRunner
	config bridge.Config

	transcript     textinput.Model
	xml            textinput.Model
	transcriptB    textinput.Model
	xmlB           textinput.Model
	brief          textarea.Model
	outputDir      textinput.Model
	assistantInput textinput.Model
	viewport       viewport.Model
	picker         filepicker.Model

	activeScreen      screen
	picking           pickTarget
	focus             int
	width             int
	height            int
	status            string
	helpOpen          bool
	bridgeError       *bridgeErrorState
	bridgePreview     string
	assistantResult   string
	assistantChat     []chatMessage
	assistantToBoard  bool
	bridgeRunning     bool
	transcriptSummary string
	summaryRunning    bool
	generationPreview string
	generationEvents  []bridge.GenerationEvent
	generationRunning bool
	exportPreview     string
	exportEvents      []bridge.GenerationEvent
	exportRunning     bool
	latestExportPath  string
	sequencePlanPath  string
	boardHydrated     bool
	board             biteBoardState
	biteEdit          textinput.Model
	trimStart         textinput.Model
	trimEnd           textinput.Model
	trimFocus         int
	trimEditing       bool
	trimError         string
}

// New constructs the Go TUI model with defaults from bridge.Config.
func New(ctx context.Context, runner firstPassRunner, config bridge.Config) Model {
	transcript := textinput.New()
	transcript.Placeholder = "/path/to/timecoded-transcript.txt"
	transcript.Prompt = "Transcript: "
	transcript.SetValue(config.TranscriptPath)
	transcript.Focus()

	xml := textinput.New()
	xml.Placeholder = "/path/to/source.xml"
	xml.Prompt = "XML A:      "
	xml.SetValue(config.XMLPath)

	transcriptB := textinput.New()
	transcriptB.Placeholder = "/path/to/second-transcript.txt"
	transcriptB.Prompt = "Transcript B: "
	transcriptB.SetValue(config.SecondaryTranscriptPath)

	xmlB := textinput.New()
	xmlB.Placeholder = "/path/to/second-source.xml"
	xmlB.Prompt = "XML B:        "
	xmlB.SetValue(config.SecondaryXMLPath)

	brief := textarea.New()
	brief.Placeholder = "5-7 minute story arc, emotional target, intended XML use..."
	brief.Prompt = ""
	brief.SetValue(config.Brief)
	brief.SetHeight(5)
	brief.Blur()

	outputDir := textinput.New()
	outputDir.Placeholder = "./output"
	outputDir.Prompt = "Output:     "
	outputDir.SetValue(config.OutputDir)

	assistantInput := textinput.New()
	assistantInput.Placeholder = "Ask for a sharper hook, selected-bite context, or another angle"
	assistantInput.Prompt = "You: "
	assistantInput.Blur()

	biteEdit := textinput.New()
	biteEdit.Placeholder = "Why this bite belongs in the cut"
	biteEdit.Prompt = "Purpose: "
	biteEdit.Blur()

	trimStart := textinput.New()
	trimStart.Placeholder = "00:00:00:00"
	trimStart.Prompt = "Start: "
	trimStart.Blur()

	trimEnd := textinput.New()
	trimEnd.Placeholder = "00:00:08:00"
	trimEnd.Prompt = "End:   "
	trimEnd.Blur()

	picker := newFilePicker(config.RepoRoot, []string{".txt"})

	vp := viewport.New(78, 10)
	model := Model{
		ctx:            ctx,
		runner:         runner,
		config:         config,
		transcript:     transcript,
		xml:            xml,
		transcriptB:    transcriptB,
		xmlB:           xmlB,
		brief:          brief,
		outputDir:      outputDir,
		assistantInput: assistantInput,
		viewport:       vp,
		picker:         picker,
		biteEdit:       biteEdit,
		trimStart:      trimStart,
		trimEnd:        trimEnd,
		board:          defaultBiteBoard(),
		activeScreen:   initialScreen(config),
		status:         "Load transcript/XML, summarize with s, enter a creative ask, select bites, ask with o, export with x.",
	}
	model.refreshViewport()
	return model
}

func (m Model) Init() tea.Cmd {
	return textinput.Blink
}

func initialScreen(config bridge.Config) screen {
	if strings.TrimSpace(config.TranscriptPath) == "" || strings.TrimSpace(config.XMLPath) == "" {
		return screenFiles
	}
	return screenPlan
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.viewport.Width = max(24, msg.Width-4)
		m.viewport.Height = max(6, msg.Height-13)
		m.picker.SetHeight(max(6, msg.Height-14))
		m.refreshViewport()
	case tea.MouseMsg:
		return m.handleMouse(msg)
	case nativeFilePickedMsg:
		m.picking = msg.target
		m = m.applyPickedFile(msg.path)
		m.activeScreen = screenFiles
		m.refreshViewport()
		return m, nil
	case bridgeFinishedMsg:
		m = m.handleBridgeFinished(msg)
		m.refreshViewport()
		return m, nil
	case generationFinishedMsg:
		var cmd tea.Cmd
		m, cmd = m.handleGenerationFinished(msg)
		m.refreshViewport()
		return m, cmd
	case exportFinishedMsg:
		m = m.handleExportFinished(msg)
		m.refreshViewport()
		return m, nil
	case nativeFilePickErrorMsg:
		m.picking = pickNone
		if isUserCancelledFilePick(msg.err) {
			m.status = "Finder file selection cancelled."
		} else {
			m.status = fmt.Sprintf("Finder file selection failed: %s", msg.err)
		}
		m.refreshViewport()
		return m, nil
	case tea.KeyMsg:
		if m.picking != pickNone {
			switch {
			case key.Matches(msg, keys.quit):
				m.picking = pickNone
				m.status = "File picker closed."
				m.refreshViewport()
				return m, nil
			}

			var cmd tea.Cmd
			m.picker, cmd = m.picker.Update(msg)
			if didSelect, path := m.picker.DidSelectFile(msg); didSelect {
				m = m.applyPickedFile(path)
				m.refreshViewport()
				return m, nil
			}
			if didSelect, path := m.picker.DidSelectDisabledFile(msg); didSelect {
				m.status = fmt.Sprintf("Cannot select %s for this field.", filepath.Base(path))
				m.refreshViewport()
				return m, cmd
			}
			m.refreshViewport()
			return m, cmd
		}

		if m.helpOpen {
			switch {
			case key.Matches(msg, keys.help), key.Matches(msg, keys.escape), key.Matches(msg, keys.quit):
				m.helpOpen = false
				m.status = "Help closed."
				m.refreshViewport()
				return m, nil
			}
		}

		if m.activeScreen == screenFiles && !m.helpOpen && m.focus == 4 {
			switch {
			case msg.Type == tea.KeyCtrlC:
				return m, tea.Quit
			case key.Matches(msg, keys.next):
				m = m.focusNext()
				m.status = "File/setup field focus changed."
				m.refreshViewport()
				return m, nil
			case key.Matches(msg, keys.prev):
				m = m.focusPrev()
				m.status = "File/setup field focus changed."
				m.refreshViewport()
				return m, nil
			default:
				var cmd tea.Cmd
				m.brief, cmd = m.brief.Update(msg)
				m.refreshViewport()
				return m, cmd
			}
		}

		if m.activeScreen == screenAssistant && !m.helpOpen {
			return m.handleAssistantChatKey(msg)
		}

		if (m.activeScreen == screenPlan || m.activeScreen == screenBite) && !m.helpOpen {
			if m.trimEditing {
				return m.handleBiteTrimKey(msg)
			}
			if m.board.Editing {
				return m.handleBiteEditKey(msg)
			}
			if updated, cmd, handled := m.handleBoardKey(msg); handled {
				return updated, cmd
			}
		}

		switch {
		case key.Matches(msg, keys.quit):
			return m, tea.Quit
		case key.Matches(msg, keys.help):
			m.helpOpen = !m.helpOpen
			if m.helpOpen {
				m.status = "Help overlay open. Press h, Esc, or q to close it."
			} else {
				m.status = "Help closed."
			}
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.next):
			m = m.focusNext()
			m.activeScreen = screenFiles
			m.status = "File/setup field focus changed."
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.prev):
			m = m.focusPrev()
			m.activeScreen = screenFiles
			m.status = "File/setup field focus changed."
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.validate):
			return m.runAssistantBridge()
		case key.Matches(msg, keys.askSelected):
			return m.runSelectedBiteQuestion()
		case key.Matches(msg, keys.summary):
			return m.runSummaryBridge()
		case key.Matches(msg, keys.generate):
			return m.runGeneration()
		case key.Matches(msg, keys.export):
			return m.runExport()
		case key.Matches(msg, keys.acceptSuggestion):
			m = m.acceptAssistantSuggestion()
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.browseTranscript):
			return m.startFileSelection(pickTranscript, []string{".txt"}, m.transcript.Value())
		case key.Matches(msg, keys.browseXML):
			return m.startFileSelection(pickXML, []string{".xml"}, m.xml.Value())
		case key.Matches(msg, keys.browseTranscriptB):
			return m.startFileSelection(pickTranscriptB, []string{".txt"}, m.transcriptB.Value())
		case key.Matches(msg, keys.browseXMLB):
			return m.startFileSelection(pickXMLB, []string{".xml"}, m.xmlB.Value())
		case key.Matches(msg, keys.welcome):
			m.activeScreen = screenWelcome
			m.status = "Welcome/setup screen selected."
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.files):
			m.activeScreen = screenFiles
			m.status = "Path/file selection screen selected."
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.plan):
			m.activeScreen = screenPlan
			m.status = "Editorial workspace selected."
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.assistant):
			m.activeScreen = screenAssistant
			m.assistantInput.Focus()
			m.status = "Model assistant chat selected. Type a message and press Enter."
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.bite):
			m.activeScreen = screenBite
			m.status = "Bite detail screen selected."
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.transcript):
			m.activeScreen = screenTranscript
			m.status = "Transcript viewport selected."
			m.refreshViewport()
			return m, nil
		}
	}

	if m.activeScreen == screenFiles && !m.helpOpen {
		var cmd tea.Cmd
		switch m.focus {
		case 0:
			m.transcript, cmd = m.transcript.Update(msg)
		case 1:
			m.xml, cmd = m.xml.Update(msg)
		case 2:
			m.transcriptB, cmd = m.transcriptB.Update(msg)
		case 3:
			m.xmlB, cmd = m.xmlB.Update(msg)
		case 4:
			m.brief, cmd = m.brief.Update(msg)
		case 5:
			m.outputDir, cmd = m.outputDir.Update(msg)
		default:
			m.viewport, cmd = m.viewport.Update(msg)
		}
		m.refreshViewport()
		return m, cmd
	}

	var cmd tea.Cmd
	m.viewport, cmd = m.viewport.Update(msg)
	return m, cmd
}

func (m Model) View() string {
	top := lipgloss.JoinVertical(
		lipgloss.Left,
		titleStyle.Render("BiteBuilder Go TUI"),
		subtitleStyle.Render("Selection-aware editorial workspace for shaping transcript-backed Premiere XML."),
		navStyle.Render("[2 Setup] [3 Workspace] [T SourceA TXT] [X SourceA XML] [Y SourceB TXT] [U SourceB XML] [s Summary] [o Ask] [g Generate] [x Export] [h Help] [q Quit]"),
	)

	body := boxStyle.Render(m.viewport.View())
	if m.helpOpen {
		body = boxStyle.Render(helpOverlay())
	}

	return lipgloss.JoinVertical(
		lipgloss.Left,
		top,
		body,
		statusStyle.Render(m.status),
		helpStyle.Render("Mouse enabled. Setup supports Source A and optional Source B. Workspace: s summarizes, g generates/regenerates, x exports, o asks about focused bite. Board: arrows/j/k navigate, space selects/removes, e edits, t trims, r replaces, u/d reorders."),
	)
}

func (m Model) handleMouse(msg tea.MouseMsg) (tea.Model, tea.Cmd) {
	if msg.Button != tea.MouseButtonLeft || msg.Action != tea.MouseActionPress {
		return m, nil
	}

	if m.helpOpen {
		m.helpOpen = false
		m.status = "Help closed."
		m.refreshViewport()
		return m, nil
	}

	if msg.Y == navRow {
		return m.handleNavClick(msg.X)
	}

	if m.activeScreen == screenFiles {
		switch msg.Y {
		case filesTranscriptA:
			return m.startFileSelection(pickTranscript, []string{".txt"}, m.transcript.Value())
		case filesXMLA:
			return m.startFileSelection(pickXML, []string{".xml"}, m.xml.Value())
		case filesTranscriptB:
			return m.startFileSelection(pickTranscriptB, []string{".txt"}, m.transcriptB.Value())
		case filesXMLB:
			return m.startFileSelection(pickXMLB, []string{".xml"}, m.xmlB.Value())
		}
	}

	return m, nil
}

func (m Model) handleNavClick(x int) (tea.Model, tea.Cmd) {
	switch {
	case x < 12:
		m.activeScreen = screenWelcome
		m.status = "Welcome/setup screen selected."
	case x < 22:
		m.activeScreen = screenFiles
		m.status = "Setup/file selection screen selected."
	case x < 38:
		m.activeScreen = screenPlan
		m.status = "Editorial workspace selected."
	case x < 47:
		m.activeScreen = screenBite
		m.status = "Bite detail screen selected."
	case x < 62:
		m.activeScreen = screenTranscript
		m.status = "Transcript viewport selected."
	case x < 72:
		m.activeScreen = screenAssistant
		m.assistantInput.Focus()
		m.status = "Model assistant chat selected. Type a message and press Enter."
	case x < 80:
		return m.startFileSelection(pickTranscript, []string{".txt"}, m.transcript.Value())
	case x < 88:
		return m.startFileSelection(pickXML, []string{".xml"}, m.xml.Value())
	case x < 100:
		return m.runSummaryBridge()
	case x < 108:
		return m.runAssistantBridge()
	case x < 121:
		return m.runGeneration()
	case x < 132:
		return m.runExport()
	case x < 141:
		m.helpOpen = true
		m.status = "Help overlay open. Press h, Esc, q, or click to close it."
	default:
		return m, tea.Quit
	}
	m.refreshViewport()
	return m, nil
}

func (m Model) focusNext() Model {
	m.blurFocused()
	m.focus = (m.focus + 1) % fieldCount
	m.focusFocused()
	return m
}

func (m Model) focusPrev() Model {
	m.blurFocused()
	m.focus = (m.focus + fieldCount - 1) % fieldCount
	m.focusFocused()
	return m
}

func (m *Model) blurFocused() {
	switch m.focus {
	case 0:
		m.transcript.Blur()
	case 1:
		m.xml.Blur()
	case 2:
		m.transcriptB.Blur()
	case 3:
		m.xmlB.Blur()
	case 4:
		m.brief.Blur()
	case 5:
		m.outputDir.Blur()
	}
}

func (m *Model) focusFocused() {
	switch m.focus {
	case 0:
		m.transcript.Focus()
	case 1:
		m.xml.Focus()
	case 2:
		m.transcriptB.Focus()
	case 3:
		m.xmlB.Focus()
	case 4:
		m.brief.Focus()
	case 5:
		m.outputDir.Focus()
	}
}

func (m Model) startFileSelection(target pickTarget, allowedTypes []string, currentPath string) (Model, tea.Cmd) {
	startDir := m.fileSelectionStartDir(currentPath)
	m.activeScreen = screenFiles
	if runtime.GOOS == "darwin" {
		m.picking = pickNone
		switch target {
		case pickTranscript:
			m.status = "Opening Finder to choose transcript A .txt file..."
		case pickXML:
			m.status = "Opening Finder to choose Premiere XML A .xml file..."
		case pickTranscriptB:
			m.status = "Opening Finder to choose transcript B .txt file..."
		case pickXMLB:
			m.status = "Opening Finder to choose Premiere XML B .xml file..."
		}
		m.refreshViewport()
		return m, chooseFileWithFinderCmd(target, startDir, allowedTypes)
	}

	m = m.startPicking(target, allowedTypes, currentPath)
	m.refreshViewport()
	return m, m.picker.Init()
}

func (m Model) startPicking(target pickTarget, allowedTypes []string, currentPath string) Model {
	startDir := m.fileSelectionStartDir(currentPath)

	m.picker = newFilePicker(startDir, allowedTypes)
	m.picking = target
	m.activeScreen = screenFiles
	switch target {
	case pickTranscript:
		m.status = "Browsing for transcript A .txt file. Enter selects; q cancels."
	case pickXML:
		m.status = "Browsing for Premiere XML A .xml file. Enter selects; q cancels."
	case pickTranscriptB:
		m.status = "Browsing for transcript B .txt file. Enter selects; q cancels."
	case pickXMLB:
		m.status = "Browsing for Premiere XML B .xml file. Enter selects; q cancels."
	}
	return m
}

func (m Model) fileSelectionStartDir(currentPath string) string {
	startDir := m.config.RepoRoot
	if strings.TrimSpace(currentPath) != "" {
		startDir = filepath.Dir(currentPath)
	}
	if strings.TrimSpace(startDir) == "" {
		startDir = "."
	}
	if stat, err := os.Stat(startDir); err != nil || !stat.IsDir() {
		startDir = m.config.RepoRoot
	}
	if strings.TrimSpace(startDir) == "" {
		startDir = "."
	}
	return startDir
}

func newFilePicker(startDir string, allowedTypes []string) filepicker.Model {
	picker := filepicker.New()
	picker.CurrentDirectory = defaultIfBlank(startDir, ".")
	picker.AllowedTypes = allowedTypes
	picker.ShowHidden = false
	picker.ShowPermissions = false
	picker.ShowSize = true
	picker.AutoHeight = false
	picker.SetHeight(12)
	return picker
}

func chooseFileWithFinderCmd(target pickTarget, startDir string, allowedTypes []string) tea.Cmd {
	return func() tea.Msg {
		if runtime.GOOS != "darwin" {
			return nativeFilePickErrorMsg{target: target, err: fmt.Errorf("Finder file dialog is only available on macOS")}
		}

		extension := ""
		if len(allowedTypes) > 0 {
			extension = strings.TrimPrefix(allowedTypes[0], ".")
		}
		if extension == "" {
			extension = "*"
		}

		prompt := "Choose a BiteBuilder file"
		switch target {
		case pickTranscript:
			prompt = "Choose a BiteBuilder transcript .txt file"
		case pickXML:
			prompt = "Choose a BiteBuilder Premiere XML .xml file"
		}

		script := fmt.Sprintf(
			"set defaultFolder to POSIX file %q\nset chosenFile to choose file with prompt %q of type {%q} default location defaultFolder\nPOSIX path of chosenFile",
			startDir,
			prompt,
			extension,
		)
		output, err := exec.Command("osascript", "-e", script).CombinedOutput()
		if err != nil {
			return nativeFilePickErrorMsg{
				target: target,
				err:    fmt.Errorf("%w: %s", err, strings.TrimSpace(string(output))),
			}
		}

		path := strings.TrimSpace(string(output))
		if path == "" {
			return nativeFilePickErrorMsg{target: target, err: fmt.Errorf("Finder returned no file")}
		}
		return nativeFilePickedMsg{target: target, path: path}
	}
}

func isUserCancelledFilePick(err error) bool {
	if err == nil {
		return false
	}
	lower := strings.ToLower(err.Error())
	return strings.Contains(lower, "user canceled") || strings.Contains(lower, "user cancelled")
}

func (m Model) applyPickedFile(path string) Model {
	path = filepath.Clean(path)
	switch m.picking {
	case pickTranscript:
		m.transcript.SetValue(path)
		m.focus = 0
		m.status = fmt.Sprintf("Selected transcript A: %s", path)
	case pickXML:
		m.xml.SetValue(path)
		m.focus = 1
		m.status = fmt.Sprintf("Selected XML A: %s", path)
	case pickTranscriptB:
		m.transcriptB.SetValue(path)
		m.focus = 2
		m.status = fmt.Sprintf("Selected transcript B: %s", path)
	case pickXMLB:
		m.xmlB.SetValue(path)
		m.focus = 3
		m.status = fmt.Sprintf("Selected XML B: %s", path)
	}
	m.blurFocused()
	m.focusFocused()
	m.picking = pickNone
	m.bridgeError = nil
	return m
}

func (m Model) runAssistantBridge() (Model, tea.Cmd) {
	userMessage := m.assistantUserMessage()
	if userMessage == "" {
		m.activeScreen = screenAssistant
		m.assistantInput.Focus()
		m.status = "Type a model-assistant follow-up, then press Enter."
		m.refreshViewport()
		return m, nil
	}
	return m.runAssistantQuestion(userMessage, false)
}

func (m Model) runSelectedBiteQuestion() (Model, tea.Cmd) {
	bite := m.currentSelectedBite()
	if bite == nil {
		bite = m.currentCandidateBite()
	}
	if bite == nil {
		m.status = "Select a bite before asking about it."
		m.activeScreen = screenPlan
		m.refreshViewport()
		return m, nil
	}
	ask := defaultIfBlank(m.brief.Value(), "(creative ask not entered yet)")
	summary := defaultIfBlank(m.transcriptSummary, "(transcript summary not generated yet)")
	message := strings.Join([]string{
		"Ask about selected bite in the current editorial workspace.",
		"",
		"Current creative ask:",
		ask,
		"",
		"Transcript summary:",
		summary,
		"",
		"Focused selected bite:",
		fmt.Sprintf("ID: %s", bite.ID),
		fmt.Sprintf("Label: %s", bite.Label),
		fmt.Sprintf("Timecode: %s", biteTimecode(*bite)),
		fmt.Sprintf("Text: %s", bite.Text),
		fmt.Sprintf("Purpose: %s", bite.Purpose),
		fmt.Sprintf("Rationale: %s", bite.Rationale),
		"",
		"Answer concisely: why does this bite fit or not fit the creative ask, and what should the editor do next?",
	}, "\n")
	return m.runAssistantQuestion(message, true)
}

func (m Model) runAssistantQuestion(userMessage string, returnToWorkspace bool) (Model, tea.Cmd) {
	config := m.currentConfig()
	config.Brief = m.assistantBridgeBrief(userMessage)
	args, err := config.BuildReadOnlyBridgeArgs("assistant")
	if err != nil {
		m.bridgePreview = ""
		m.assistantResult = ""
		m.bridgeError = &bridgeErrorState{
			Operation: "assistant",
			Code:      "invalid_request",
			Message:   err.Error(),
			Hint:      "Choose transcript and XML files before asking the model assistant about the creative ask.",
		}
		m.status = fmt.Sprintf("Bridge validation failed: %s", err)
		m.activeScreen = screenFiles
		m.refreshViewport()
		return m, nil
	}

	m.bridgeError = nil
	m.assistantResult = ""
	m.assistantChat = append(m.assistantChat, chatMessage{Role: "You", Text: userMessage})
	m.assistantInput.SetValue("")
	m.assistantInput.Blur()
	m.bridgePreview = fmt.Sprintf("$ %s %s", config.Python, strings.Join(args, " "))
	m.bridgeRunning = true
	m.assistantToBoard = returnToWorkspace
	if returnToWorkspace {
		m.status = "Asking model assistant about the focused bite..."
		m.activeScreen = screenPlan
	} else {
		m.status = "Sending chat turn to BiteBuilder's model assistant..."
		m.activeScreen = screenAssistant
	}
	m.refreshViewport()
	return m, func() tea.Msg {
		result, err := m.runner.RunBridgeOperation(m.ctx, config, "assistant")
		return bridgeFinishedMsg{operation: "assistant", result: result, err: err}
	}
}

func (m Model) runSummaryBridge() (Model, tea.Cmd) {
	config := m.currentConfig()
	args, err := config.BuildReadOnlyBridgeArgs("summary")
	if err != nil {
		m.bridgePreview = ""
		m.bridgeError = &bridgeErrorState{
			Operation: "summary",
			Code:      "invalid_request",
			Message:   err.Error(),
			Hint:      "Choose transcript and XML files before summarizing the interview.",
		}
		m.status = fmt.Sprintf("Summary validation failed: %s", err)
		m.activeScreen = screenFiles
		m.refreshViewport()
		return m, nil
	}

	m.bridgeError = nil
	m.summaryRunning = true
	m.bridgePreview = fmt.Sprintf("$ %s %s", config.Python, strings.Join(args, " "))
	m.status = "Summarizing transcript through the Python bridge..."
	m.activeScreen = screenPlan
	m.refreshViewport()
	return m, func() tea.Msg {
		result, err := m.runner.RunBridgeOperation(m.ctx, config, "summary")
		return bridgeFinishedMsg{operation: "summary", result: result, err: err}
	}
}

func (m Model) runGeneration() (Model, tea.Cmd) {
	config := m.currentConfig()
	args, err := config.BuildGenerationArgs()
	if err != nil {
		m.generationPreview = ""
		m.generationEvents = nil
		m.bridgeError = &bridgeErrorState{
			Operation: "generate",
			Code:      "invalid_request",
			Message:   err.Error(),
			Hint:      "Choose transcript/XML files and enter a creative ask before running generation.",
		}
		m.status = fmt.Sprintf("Generation validation failed: %s", err)
		m.activeScreen = screenFiles
		m.refreshViewport()
		return m, nil
	}

	m.bridgeError = nil
	m.generationEvents = nil
	m.generationPreview = fmt.Sprintf("$ %s %s", config.Python, strings.Join(args, " "))
	m.generationRunning = true
	m.status = "Running BiteBuilder generation through the Python NDJSON bridge..."
	m.activeScreen = screenPlan
	m.refreshViewport()
	return m, func() tea.Msg {
		result, err := m.runner.RunGeneration(m.ctx, config)
		return generationFinishedMsg{result: result, err: err}
	}
}

func (m Model) runExport() (Model, tea.Cmd) {
	if validationErr := m.boardValidationError(); validationErr != "" {
		m.board.ValidationErr = validationErr
		m.status = "Export disabled: " + validationErr
		m.activeScreen = screenPlan
		m.refreshViewport()
		return m, nil
	}

	config := m.currentConfig()
	if strings.TrimSpace(config.SequencePlan) == "" {
		config.SequencePlan = m.sequencePlanPath
	}
	selectedJSON, err := m.selectedBoardJSON()
	if err != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "export",
			Code:      "invalid_selected_board",
			Message:   err.Error(),
			Hint:      "Fix the selected sequence before exporting.",
		}
		m.status = "Export validation failed before Python subprocess."
		m.activeScreen = screenPlan
		m.refreshViewport()
		return m, nil
	}
	config.SelectedBoardJSON = selectedJSON

	args, err := config.BuildExportArgs()
	if err != nil {
		m.exportPreview = ""
		m.exportEvents = nil
		m.bridgeError = &bridgeErrorState{
			Operation: "export",
			Code:      "invalid_request",
			Message:   err.Error(),
			Hint:      "Generate a sequence plan, keep at least one selected bite, then export.",
		}
		m.status = fmt.Sprintf("Export validation failed: %s", err)
		m.activeScreen = screenPlan
		m.refreshViewport()
		return m, nil
	}

	m.bridgeError = nil
	m.exportEvents = nil
	m.exportPreview = fmt.Sprintf("$ %s %s", config.Python, strings.Join(args, " "))
	m.exportRunning = true
	m.status = "Exporting selected sequence through Python validation/XMEML..."
	m.activeScreen = screenPlan
	m.refreshViewport()
	return m, func() tea.Msg {
		result, err := m.runner.RunExport(m.ctx, config)
		return exportFinishedMsg{result: result, err: err}
	}
}

func (m Model) handleBridgeFinished(msg bridgeFinishedMsg) Model {
	m.bridgeRunning = false
	if msg.operation == "summary" {
		m.summaryRunning = false
	}
	m.bridgePreview = msg.result.Command
	if msg.operation == "plan" {
		return m.handlePlanBridgeFinished(msg)
	}
	if msg.operation == "summary" {
		return m.handleSummaryBridgeFinished(msg)
	}
	if msg.err != nil {
		returnToWorkspace := m.assistantToBoard
		m.assistantToBoard = false
		m.assistantResult = strings.TrimSpace(msg.result.Stderr + "\n" + msg.result.Stdout)
		m.bridgeError = &bridgeErrorState{
			Operation: msg.operation,
			Code:      "bridge_run_failed",
			Message:   msg.err.Error(),
			Hint:      "Start gemma4server, confirm the selected files are readable, then retry.",
		}
		m.status = "Model assistant bridge failed."
		if returnToWorkspace {
			m.activeScreen = screenPlan
		}
		return m
	}

	suggestion, err := extractAssistantSuggestion(msg.result.Stdout)
	if err != nil {
		m.assistantResult = strings.TrimSpace(msg.result.Stdout)
		m.bridgeError = &bridgeErrorState{
			Operation: msg.operation,
			Code:      "invalid_bridge_json",
			Message:   err.Error(),
			Hint:      "The Python bridge should emit one JSON envelope on stdout.",
		}
		m.status = "Model assistant returned an unreadable bridge response."
		return m
	}

	m.bridgeError = nil
	m.assistantResult = suggestion
	m.assistantChat = append(m.assistantChat, chatMessage{Role: "Assistant", Text: suggestion})
	m.assistantInput.Focus()
	if m.assistantToBoard {
		m.assistantInput.Blur()
		m.assistantToBoard = false
		m.status = "Model assistant answered about the focused bite."
		m.activeScreen = screenPlan
		return m
	}
	m.status = "Model assistant replied. Type a follow-up and press Enter to continue the loop."
	m.activeScreen = screenAssistant
	return m
}

func (m Model) handlePlanBridgeFinished(msg bridgeFinishedMsg) Model {
	if msg.err != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "plan",
			Code:      "plan_bridge_failed",
			Message:   msg.err.Error(),
			Hint:      "The generated sequence plan exists, but the board could not be hydrated from Python yet.",
		}
		m.status = "Plan bridge failed while loading candidate/selected board data."
		return m
	}
	planData, err := bridge.DecodeResultData[bridge.PlanData](msg.result)
	if err != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "plan",
			Code:      "invalid_plan_bridge_json",
			Message:   err.Error(),
			Hint:      "The Python plan bridge should emit a typed board payload.",
		}
		m.status = "Plan bridge returned unreadable board data."
		return m
	}
	m.bridgeError = nil
	m.applyBoardData(planData.Board)
	m.status = "Candidate bites and selected sequence loaded from Python plan data."
	m.activeScreen = screenPlan
	return m
}

func (m Model) handleSummaryBridgeFinished(msg bridgeFinishedMsg) Model {
	if msg.err != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "summary",
			Code:      "summary_bridge_failed",
			Message:   msg.err.Error(),
			Hint:      "Start the model runtime, confirm the selected files are readable, then retry.",
		}
		m.status = "Transcript summary bridge failed."
		m.activeScreen = screenPlan
		return m
	}
	data, err := bridge.DecodeResultData[bridge.SummaryData](msg.result)
	if err != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "summary",
			Code:      "invalid_summary_bridge_json",
			Message:   err.Error(),
			Hint:      "The Python summary bridge should emit data.summary_text.",
		}
		m.status = "Transcript summary returned unreadable bridge data."
		m.activeScreen = screenPlan
		return m
	}
	if strings.TrimSpace(data.SummaryText) == "" {
		m.bridgeError = &bridgeErrorState{
			Operation: "summary",
			Code:      "empty_summary",
			Message:   "summary bridge response did not include data.summary_text",
			Hint:      "Retry the summary request.",
		}
		m.status = "Transcript summary was empty."
		m.activeScreen = screenPlan
		return m
	}
	m.bridgeError = nil
	m.transcriptSummary = strings.TrimSpace(data.SummaryText)
	m.status = "Transcript summary updated."
	m.activeScreen = screenPlan
	return m
}

func (m Model) handleGenerationFinished(msg generationFinishedMsg) (Model, tea.Cmd) {
	m.generationRunning = false
	m.generationPreview = msg.result.Command

	events, parseErr := bridge.ParseGenerationEvents(msg.result.Stdout)
	if parseErr != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "generate",
			Code:      "generation_protocol_error",
			Message:   parseErr.Error(),
			Hint:      "The Python generation bridge must emit newline-delimited JSON events on stdout only.",
		}
		if msg.err != nil {
			m.bridgeError.Message = fmt.Sprintf("%s; process error: %s", m.bridgeError.Message, msg.err)
		}
		m.status = "Generation bridge returned unreadable NDJSON."
		return m, nil
	}

	m.generationEvents = events
	if eventErr := generationError(events); eventErr != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "generate",
			Code:      eventErr.Code,
			Message:   eventErr.Message,
			Hint:      defaultIfBlank(eventErr.NextAction, "Check generation inputs and retry."),
		}
		m.status = "Generation failed with a structured bridge error."
		return m, nil
	}

	if msg.err != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "generate",
			Code:      "generation_run_failed",
			Message:   msg.err.Error(),
			Hint:      "Check the model runtime, selected files, and output directory, then retry.",
		}
		m.status = "Generation process failed."
		return m, nil
	}

	if hydrated, ok := boardFromGenerationEvents(events); ok {
		m.board = hydrated
		m.boardHydrated = true
		m.status = "Generation completed; board hydrated from backend event data."
		m.activeScreen = screenPlan
		return m, nil
	}

	m.bridgeError = nil
	m.status = "Generation completed; artifact paths are listed in the workspace."
	m.activeScreen = screenPlan
	if path := generationSequencePlanPath(events); path != "" {
		m.sequencePlanPath = path
		m.config.SequencePlan = path
		return m, m.runPlanBridge(path)
	}
	return m, nil
}

func (m Model) handleExportFinished(msg exportFinishedMsg) Model {
	m.exportRunning = false
	m.exportPreview = msg.result.Command

	events, parseErr := bridge.ParseGenerationEvents(msg.result.Stdout)
	if parseErr != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "export",
			Code:      "export_protocol_error",
			Message:   parseErr.Error(),
			Hint:      "The Python export bridge must emit newline-delimited JSON events on stdout only.",
		}
		if msg.err != nil {
			m.bridgeError.Message = fmt.Sprintf("%s; process error: %s", m.bridgeError.Message, msg.err)
		}
		m.status = "Export bridge returned unreadable NDJSON."
		m.activeScreen = screenPlan
		return m
	}

	m.exportEvents = events
	if eventErr := generationError(events); eventErr != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "export",
			Code:      eventErr.Code,
			Message:   eventErr.Message,
			Hint:      defaultIfBlank(eventErr.NextAction, "Check export inputs and retry."),
		}
		m.status = "Export failed with a structured bridge error."
		m.activeScreen = screenPlan
		return m
	}

	if msg.err != nil {
		m.bridgeError = &bridgeErrorState{
			Operation: "export",
			Code:      "export_run_failed",
			Message:   msg.err.Error(),
			Hint:      "Check selected files, sequence plan, output directory, and selected-board edits, then retry.",
		}
		m.status = "Export process failed."
		m.activeScreen = screenPlan
		return m
	}

	m.bridgeError = nil
	if path := eventArtifactPath(events, "xmeml"); path != "" {
		m.latestExportPath = path
		m.status = "Export completed: " + path
	} else {
		m.status = "Export completed."
	}
	if path := eventArtifactPath(events, "sequence_plan"); path != "" {
		m.sequencePlanPath = path
		m.config.SequencePlan = path
	}
	m.activeScreen = screenPlan
	return m
}

func (m Model) runPlanBridge(sequencePlanPath string) tea.Cmd {
	config := m.currentConfig()
	config.SequencePlan = sequencePlanPath
	args, err := config.BuildReadOnlyBridgeArgs("plan")
	if err != nil {
		return nil
	}
	return func() tea.Msg {
		result, runErr := m.runner.RunBridgeOperation(m.ctx, config, "plan")
		if result.Command == "" {
			result.Command = fmt.Sprintf("$ %s %s", config.Python, strings.Join(args, " "))
		}
		return bridgeFinishedMsg{operation: "plan", result: result, err: runErr}
	}
}

func (m Model) acceptAssistantSuggestion() Model {
	if strings.TrimSpace(m.assistantResult) == "" {
		m.status = "No model assistant suggestion to accept yet. Press v first."
		return m
	}
	brief := extractSuggestedBrief(m.assistantResult)
	m.brief.SetValue(brief)
	m.activeScreen = screenFiles
	m.focus = 2
	m.blurFocused()
	m.focusFocused()
	m.status = "Accepted model suggestion into the creative ask field."
	return m
}

func (m Model) currentConfig() bridge.Config {
	config := m.config
	config.TranscriptPath = strings.TrimSpace(m.transcript.Value())
	config.XMLPath = strings.TrimSpace(m.xml.Value())
	config.SecondaryTranscriptPath = strings.TrimSpace(m.transcriptB.Value())
	config.SecondaryXMLPath = strings.TrimSpace(m.xmlB.Value())
	config.Brief = strings.TrimSpace(m.brief.Value())
	config.OutputDir = strings.TrimSpace(m.outputDir.Value())
	if strings.TrimSpace(m.sequencePlanPath) != "" {
		config.SequencePlan = strings.TrimSpace(m.sequencePlanPath)
	}
	return config
}

func (m *Model) refreshViewport() {
	if m.helpOpen {
		return
	}
	m.viewport.SetContent(m.screenContent())
}

func (m Model) screenContent() string {
	if m.picking != pickNone {
		return m.filePickerContent()
	}

	if m.bridgeError != nil {
		return strings.Join([]string{
			"Structured bridge error state",
			"",
			fmt.Sprintf("operation: %s", m.bridgeError.Operation),
			fmt.Sprintf("code:      %s", m.bridgeError.Code),
			fmt.Sprintf("message:   %s", m.bridgeError.Message),
			fmt.Sprintf("hint:      %s", m.bridgeError.Hint),
			"",
			"This app surfaces bridge errors without mutating output files.",
			"Press 2 to return to path/file selection or h for help.",
		}, "\n")
	}

	switch m.activeScreen {
	case screenFiles:
		return m.filesContent()
	case screenPlan:
		return m.planContent()
	case screenAssistant:
		return m.assistantContent()
	case screenBite:
		return m.biteContent()
	case screenTranscript:
		return m.transcriptContent()
	default:
		return m.welcomeContent()
	}
}

func (m Model) welcomeContent() string {
	return strings.Join([]string{
		"Welcome / setup",
		"",
		"BiteBuilder turns a timecoded transcript and Premiere XML into a sequence plan and edit artifacts.",
		"This Go TUI is the selection-aware editorial workspace for:",
		"  • collect and review file paths",
		"  • summarize source context",
		"  • shape candidate and selected transcript bites",
		"  • export selected bites through Python validation/XMEML",
		"  • surface structured bridge errors",
		"",
		fmt.Sprintf("Repository: %s", defaultIfBlank(m.config.RepoRoot, "(not set)")),
		fmt.Sprintf("Python:     %s", defaultIfBlank(m.config.Python, "(not set)")),
		"",
		"Press 2 for setup, enter a creative ask, then press 3 for the editorial workspace.",
	}, "\n")
}

func (m Model) filesContent() string {
	return strings.Join([]string{
		"Setup / file selection",
		"",
		m.transcript.View(),
		"  [T] Transcript A",
		m.xml.View(),
		"  [X] XML A",
		m.transcriptB.View(),
		"  [Y] Transcript B (optional)",
		m.xmlB.View(),
		"  [U] XML B (optional)",
		"Creative ask:",
		m.brief.View(),
		m.outputDir.View(),
		"",
		"Two-interview mode: load A + optional B, then press s to summarize or g to generate.",
		fmt.Sprintf("Output basename preview: %s", outputPreview(m.outputDir.Value())),
	}, "\n")
}

func (m Model) filePickerContent() string {
	title := "Browse for file"
	switch m.picking {
	case pickTranscript:
		title = "Browse transcript A (.txt)"
	case pickXML:
		title = "Browse Premiere XML A (.xml)"
	case pickTranscriptB:
		title = "Browse transcript B (.txt)"
	case pickXMLB:
		title = "Browse Premiere XML B (.xml)"
	}
	return strings.Join([]string{
		title,
		"",
		m.picker.View(),
		"",
		"Enter/right opens directories or selects an allowed file. q cancels.",
	}, "\n")
}

func (m Model) planContent() string {
	return m.workspaceContent()
}

func (m Model) workspaceContent() string {
	ask := strings.TrimSpace(m.brief.Value())
	if ask == "" {
		ask = "(creative ask not entered yet)"
	}
	summary := strings.TrimSpace(m.transcriptSummary)
	if summary == "" {
		summary = "(not summarized yet — press s)"
	}
	transcriptContext := m.workspaceTranscriptContext()

	lines := []string{
		"Editorial workspace",
		"",
		"Source context",
		"  Transcript A: " + defaultIfBlank(m.transcript.Value(), "(not selected)"),
		"  XML A:        " + defaultIfBlank(m.xml.Value(), "(not selected)"),
		"  Transcript B: " + defaultIfBlank(m.transcriptB.Value(), "(optional / not selected)"),
		"  XML B:        " + defaultIfBlank(m.xmlB.Value(), "(optional / not selected)"),
		"  Output:       " + outputPreview(m.outputDir.Value()),
		"  " + transcriptContext,
		"",
		"Transcript summary",
		summary,
		"",
		"Creative ask",
		ask,
		"",
		m.boardContent(),
		"",
		"Status / export",
		"  " + defaultIfBlank(m.status, "(idle)"),
	}
	if strings.TrimSpace(m.sequencePlanPath) != "" {
		lines = append(lines, "  Sequence plan: "+m.sequencePlanPath)
	}
	if strings.TrimSpace(m.latestExportPath) != "" {
		lines = append(lines, "  Latest export: "+m.latestExportPath)
	}
	if m.summaryRunning {
		lines = append(lines, "", "Summary is running through Python...")
	}
	if m.bridgeRunning {
		lines = append(lines, "", "Assistant is responding through Python...")
	}
	if latest := m.latestAssistantReply(); latest != "" {
		lines = append(lines, "", "Latest assistant answer", latest)
	}
	if m.generationRunning {
		lines = append(lines, "", "Generation in progress", m.generationPreview)
	}
	if len(m.generationEvents) > 0 {
		lines = append(lines, "", "Generation events", m.generationEventsContent())
	}
	if m.exportRunning {
		lines = append(lines, "", "Export in progress", m.exportPreview)
	}
	if len(m.exportEvents) > 0 {
		lines = append(lines, "", "Export events", m.exportEventsContent())
	}
	if strings.TrimSpace(m.bridgePreview) != "" && (m.summaryRunning || m.bridgeRunning) {
		lines = append(lines, "", "Command:", m.bridgePreview)
	}
	lines = append(lines, "", "Controls: s summarize; g generate/regenerate; x export; o ask focused bite; left/right/up/down board; space delete/add; r replace; e/l/n/t edit/trim.")
	return strings.Join(lines, "\n")
}

func (m Model) workspaceTranscriptContext() string {
	if selected := m.currentSelectedBite(); selected != nil {
		return fmt.Sprintf("Focused selected: %s — %s — %s", selected.Label, biteTimecode(*selected), fitLine(selected.Text, 72))
	}
	if candidate := m.currentCandidateBite(); candidate != nil {
		return fmt.Sprintf("Focused candidate: %s — %s — %s", candidate.Label, biteTimecode(*candidate), fitLine(candidate.Text, 72))
	}
	return "Transcript context appears here after generation or selection."
}

func (m Model) handleAssistantChatKey(msg tea.KeyMsg) (Model, tea.Cmd) {
	if msg.Type == tea.KeyCtrlC {
		return m, tea.Quit
	}
	if m.bridgeRunning {
		switch {
		case key.Matches(msg, keys.escape):
			m.activeScreen = screenPlan
			m.status = "Workspace selected while assistant response continues."
			m.refreshViewport()
			return m, nil
		default:
			return m, nil
		}
	}
	switch {
	case strings.TrimSpace(m.assistantInput.Value()) == "" && key.Matches(msg, keys.help):
		m.helpOpen = true
		m.status = "Help overlay open. Press h, Esc, or q to close it."
		m.refreshViewport()
		return m, nil
	case strings.TrimSpace(m.assistantInput.Value()) == "" && key.Matches(msg, keys.acceptSuggestion):
		m = m.acceptAssistantSuggestion()
		m.refreshViewport()
		return m, nil
	case key.Matches(msg, keys.escape):
		m.activeScreen = screenPlan
		m.assistantInput.Blur()
		m.status = "Editorial workspace selected."
		m.refreshViewport()
		return m, nil
	case msg.Type == tea.KeyEnter:
		return m.runAssistantBridge()
	}

	var cmd tea.Cmd
	m.assistantInput, cmd = m.assistantInput.Update(msg)
	m.refreshViewport()
	return m, cmd
}

func (m Model) assistantUserMessage() string {
	message := strings.TrimSpace(m.assistantInput.Value())
	if message != "" {
		return message
	}
	if len(m.assistantChat) == 0 {
		if strings.TrimSpace(m.brief.Value()) == "" {
			return "Suggest a strong creative ask for this BiteBuilder edit."
		}
		return "Suggest a stronger creative ask rewrite for the current BiteBuilder setup."
	}
	return ""
}

func (m Model) assistantBridgeBrief(userMessage string) string {
	var sections []string
	if brief := strings.TrimSpace(m.brief.Value()); brief != "" {
		sections = append(sections, "Current creative ask:\n"+brief)
	}
	if summary := strings.TrimSpace(m.transcriptSummary); summary != "" {
		sections = append(sections, "Transcript summary:\n"+summary)
	}
	if len(m.assistantChat) > 0 {
		lines := []string{"Assistant chat so far:"}
		for _, message := range m.assistantChat {
			lines = append(lines, fmt.Sprintf("%s: %s", message.Role, message.Text))
		}
		sections = append(sections, strings.Join(lines, "\n"))
	}
	sections = append(sections, "Latest user request:\n"+strings.TrimSpace(userMessage))
	return strings.TrimSpace(strings.Join(sections, "\n\n"))
}

func (m Model) assistantContent() string {
	lines := []string{
		"Model assistant chat loop",
		"",
		"Use this chat as a small tool for the creative ask or selected bite context.",
	}
	if len(m.assistantChat) > 0 {
		lines = append(lines, fmt.Sprintf("Conversation: %d message(s)", len(m.assistantChat)))
	}
	if latest := m.latestAssistantReply(); latest != "" {
		lines = append(lines,
			"",
			"Model assistant suggestion",
			"",
			latest,
			"",
			"Press a to accept the Suggested Creative Brief into the editable creative ask field.",
		)
	}
	if len(m.assistantChat) > 0 {
		lines = append(lines,
			"",
			"Conversation",
			m.assistantTranscriptContent(),
		)
	} else {
		lines = append(lines,
			"",
			"No assistant turns yet. Press Enter to ask about the current creative ask.",
		)
	}
	if m.bridgeRunning {
		lines = append(lines,
			"",
			"Assistant is responding...",
		)
	} else {
		lines = append(lines,
			"",
			m.assistantInput.View(),
			"Enter sends a follow-up. Esc returns to the board. Ctrl+C quits.",
		)
	}
	if strings.TrimSpace(m.bridgePreview) != "" {
		lines = append(lines, "", "Command:", m.bridgePreview)
	}
	return strings.Join(lines, "\n")
}

func (m Model) latestAssistantReply() string {
	for i := len(m.assistantChat) - 1; i >= 0; i-- {
		if m.assistantChat[i].Role == "Assistant" {
			return m.assistantChat[i].Text
		}
	}
	return strings.TrimSpace(m.assistantResult)
}

func (m Model) assistantTranscriptContent() string {
	if len(m.assistantChat) == 0 {
		return "(empty)"
	}
	lines := make([]string, 0, len(m.assistantChat)*2)
	for _, message := range m.assistantChat {
		for i, line := range splitDisplayLines(message.Text, 72) {
			prefix := "    "
			if i == 0 {
				prefix = fmt.Sprintf("  %s: ", message.Role)
			}
			lines = append(lines, prefix+line)
		}
	}
	return strings.Join(lines, "\n")
}

func (m Model) generationEventsContent() string {
	lines := make([]string, 0, len(m.generationEvents))
	for _, event := range m.generationEvents {
		switch event.Event {
		case bridge.GenerationEventStarted:
			lines = append(lines, fmt.Sprintf("started: %s", defaultIfBlank(event.Stage, "start")))
		case bridge.GenerationEventProgress:
			lines = append(lines, fmt.Sprintf("progress[%s]: %s", defaultIfBlank(event.Stage, "pipeline"), event.Message))
		case bridge.GenerationEventArtifact:
			lines = append(lines, fmt.Sprintf("artifact[%s]: %s", defaultIfBlank(event.Kind, "file"), event.Path))
		case bridge.GenerationEventCompleted:
			detail := "ok"
			if len(event.Data) > 0 {
				detail = string(event.Data)
			}
			lines = append(lines, fmt.Sprintf("completed: %s", detail))
		case bridge.GenerationEventError:
			if event.Error != nil {
				lines = append(lines, fmt.Sprintf("error[%s]: %s", event.Error.Code, event.Error.Message))
			} else {
				lines = append(lines, "error: generation failed")
			}
		default:
			lines = append(lines, fmt.Sprintf("%s: %s", event.Event, event.Message))
		}
	}
	if len(lines) == 0 {
		return "(no generation events yet)"
	}
	return strings.Join(lines, "\n")
}

func (m Model) exportEventsContent() string {
	if len(m.exportEvents) == 0 {
		return "(no export events yet)"
	}
	lines := make([]string, 0, len(m.exportEvents))
	for _, event := range m.exportEvents {
		switch event.Event {
		case bridge.GenerationEventStarted:
			lines = append(lines, fmt.Sprintf("started: %s", defaultIfBlank(event.Stage, "start")))
		case bridge.GenerationEventProgress:
			lines = append(lines, fmt.Sprintf("progress[%s]: %s", defaultIfBlank(event.Stage, "export"), event.Message))
		case bridge.GenerationEventArtifact:
			lines = append(lines, fmt.Sprintf("artifact[%s]: %s", defaultIfBlank(event.Kind, "file"), event.Path))
		case bridge.GenerationEventCompleted:
			lines = append(lines, "completed: ok")
		case bridge.GenerationEventError:
			if event.Error != nil {
				lines = append(lines, fmt.Sprintf("error[%s]: %s", event.Error.Code, event.Error.Message))
			} else {
				lines = append(lines, "error: export failed")
			}
		default:
			lines = append(lines, fmt.Sprintf("%s: %s", event.Event, event.Message))
		}
	}
	return strings.Join(lines, "\n")
}

func (m Model) generationContent() string {
	lines := []string{
		"Generation result",
	}
	if m.boardHydrated {
		lines = append(lines, "", m.boardContent(), "")
	}
	lines = append(lines,
		"",
		"Generation events / candidate bites",
		"",
		m.generationEventsContent(),
	)
	if strings.TrimSpace(m.generationPreview) != "" {
		lines = append(lines, "", "Command:", m.generationPreview)
	}
	return strings.Join(lines, "\n")
}

func boardFromGenerationEvents(events []bridge.GenerationEvent) (biteBoardState, bool) {
	for i := len(events) - 1; i >= 0; i-- {
		if len(events[i].Data) == 0 {
			continue
		}
		if board, ok := boardFromBackendPayload(events[i].Data); ok {
			return board, true
		}
	}
	return biteBoardState{}, false
}

func boardFromBackendPayload(raw json.RawMessage) (biteBoardState, bool) {
	if len(raw) == 0 {
		return biteBoardState{}, false
	}
	var payload map[string]json.RawMessage
	if err := json.Unmarshal(raw, &payload); err != nil {
		return biteBoardState{}, false
	}
	if nested, ok := firstRaw(payload, "board", "data"); ok {
		if board, ok := boardFromBackendPayload(nested); ok {
			return board, true
		}
	}
	if plan, ok := firstRaw(payload, "sequence_plan", "plan"); ok {
		if board, ok := boardFromSequencePlanPayload(plan); ok {
			return board, true
		}
	}
	if _, ok := payload["options"]; ok {
		if board, ok := boardFromSequencePlanPayload(raw); ok {
			return board, true
		}
	}

	candidates, hasCandidates := bitesFromPayloadArrays(payload, []string{"candidate_bites", "candidates"})
	selected, hasSelected := bitesFromPayloadArrays(payload, []string{"selected_bites", "selected", "selected_sequence"})
	if allBites, ok := bitesFromPayloadArrays(payload, []string{"bites"}); ok {
		for _, bite := range allBites {
			switch strings.ToLower(strings.TrimSpace(bite.Status)) {
			case "selected", "replacement":
				selected = append(selected, bite)
				hasSelected = true
			case "removed":
				continue
			default:
				candidates = append(candidates, bite)
				hasCandidates = true
			}
		}
	}
	return normalizeHydratedBoard(candidates, selected, hasCandidates || hasSelected)
}

func boardFromSequencePlanPayload(raw json.RawMessage) (biteBoardState, bool) {
	var plan struct {
		Options []struct {
			OptionID string        `json:"option_id"`
			Name     string        `json:"name"`
			Bites    []backendBite `json:"bites"`
		} `json:"options"`
		CurrentOptionID string `json:"current_option_id"`
	}
	if err := json.Unmarshal(raw, &plan); err != nil || len(plan.Options) == 0 {
		return biteBoardState{}, false
	}
	option := plan.Options[0]
	if plan.CurrentOptionID != "" {
		for _, candidate := range plan.Options {
			if candidate.OptionID == plan.CurrentOptionID {
				option = candidate
				break
			}
		}
	}
	candidates := make([]biteCard, 0, len(option.Bites))
	selected := make([]biteCard, 0, len(option.Bites))
	for i, bite := range option.Bites {
		card := bite.toCard("candidate", i)
		switch strings.ToLower(strings.TrimSpace(card.Status)) {
		case "removed":
			continue
		case "selected", "replacement":
			selected = append(selected, card)
			candidate := card
			candidate.Status = "candidate"
			candidates = append(candidates, candidate)
		default:
			candidates = append(candidates, card)
		}
	}
	return normalizeHydratedBoard(candidates, selected, len(candidates) > 0 || len(selected) > 0)
}

func bitesFromPayloadArrays(payload map[string]json.RawMessage, keys []string) ([]biteCard, bool) {
	raw, ok := firstRaw(payload, keys...)
	if !ok {
		return nil, false
	}
	var bites []backendBite
	if err := json.Unmarshal(raw, &bites); err != nil {
		return nil, false
	}
	cards := make([]biteCard, 0, len(bites))
	defaultStatus := "candidate"
	for _, key := range keys {
		if strings.Contains(key, "selected") {
			defaultStatus = "selected"
			break
		}
	}
	for i, bite := range bites {
		card := bite.toCard(defaultStatus, i)
		if strings.EqualFold(card.Status, "removed") {
			continue
		}
		cards = append(cards, card)
	}
	return cards, len(cards) > 0
}

func normalizeHydratedBoard(candidates, selected []biteCard, ok bool) (biteBoardState, bool) {
	if !ok || (len(candidates) == 0 && len(selected) == 0) {
		return biteBoardState{}, false
	}
	board := biteBoardState{
		Candidates:  candidates,
		Selected:    selected,
		FocusColumn: boardCandidates,
	}
	if len(board.Candidates) == 0 && len(board.Selected) > 0 {
		board.FocusColumn = boardSelected
	}
	board.CandidateIndex = clampIndex(0, len(board.Candidates))
	board.SelectedIndex = clampIndex(0, len(board.Selected))
	return board, true
}

func firstRaw(payload map[string]json.RawMessage, keys ...string) (json.RawMessage, bool) {
	for _, key := range keys {
		if raw, ok := payload[key]; ok && len(raw) > 0 && string(raw) != "null" {
			return raw, true
		}
	}
	return nil, false
}

type backendBite struct {
	ID              string `json:"id"`
	BiteID          string `json:"bite_id"`
	Label           string `json:"label"`
	Name            string `json:"name"`
	Segment         *int   `json:"segment"`
	SegmentIndex    *int   `json:"segment_index"`
	Timecode        string `json:"timecode"`
	TCIn            string `json:"tc_in"`
	TCOut           string `json:"tc_out"`
	Text            string `json:"text"`
	DialogueSummary string `json:"dialogue_summary"`
	Purpose         string `json:"purpose"`
	Rationale       string `json:"rationale"`
	Status          string `json:"status"`
	ReplacesID      string `json:"replaces_id"`
	ReplacesBiteID  string `json:"replaces_bite_id"`
}

func (b backendBite) toCard(defaultStatus string, index int) biteCard {
	segment := 0
	if b.Segment != nil {
		segment = *b.Segment
	} else if b.SegmentIndex != nil {
		segment = *b.SegmentIndex
	}
	status := defaultIfBlank(b.Status, defaultStatus)
	id := firstNonBlank(b.ID, b.BiteID, fmt.Sprintf("%s-%03d", status, index+1))
	label := firstNonBlank(b.Label, b.Name, b.Purpose, fmt.Sprintf("Bite %d", index+1))
	tcIn, tcOut := normalizedCardTimecodes(firstNonBlank(b.Timecode, joinedTimecode(b.TCIn, b.TCOut)), b.TCIn, b.TCOut)
	return biteCard{
		ID:         id,
		Label:      label,
		Segment:    segment,
		TCIn:       tcIn,
		TCOut:      tcOut,
		Timecode:   joinedTimecode(tcIn, tcOut),
		Text:       firstNonBlank(b.Text, b.DialogueSummary),
		Purpose:    b.Purpose,
		Rationale:  b.Rationale,
		Status:     status,
		ReplacesID: firstNonBlank(b.ReplacesID, b.ReplacesBiteID),
	}
}

func joinedTimecode(tcIn, tcOut string) string {
	if strings.TrimSpace(tcIn) == "" && strings.TrimSpace(tcOut) == "" {
		return ""
	}
	return fmt.Sprintf("%s - %s", strings.TrimSpace(tcIn), strings.TrimSpace(tcOut))
}

func normalizedCardTimecodes(timecode, tcIn, tcOut string) (string, string) {
	rangeStart, rangeEnd := splitTimecodeRange(timecode)
	return firstNonBlank(tcIn, rangeStart), firstNonBlank(tcOut, rangeEnd)
}

func biteTimecode(bite biteCard) string {
	return bite.displayTimecode()
}

func splitTimecodeRange(value string) (string, string) {
	parts := strings.Split(strings.TrimSpace(value), " - ")
	if len(parts) == 2 {
		return strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1])
	}
	parts = strings.Split(strings.TrimSpace(value), "-")
	if len(parts) == 2 {
		return strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1])
	}
	return "", ""
}

func firstNonBlank(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}

func generationError(events []bridge.GenerationEvent) *bridge.BridgeError {
	for _, event := range events {
		if event.Event == bridge.GenerationEventError && event.Error != nil {
			return event.Error
		}
	}
	return nil
}

func (m Model) biteContent() string {
	selected := m.currentSelectedBite()
	candidate := m.currentCandidateBite()
	lines := []string{
		"Bite detail / transcript viewport / edit / trim / replace",
	}
	if strings.TrimSpace(m.board.ValidationErr) != "" {
		lines = append(lines, "", "Validation: "+m.board.ValidationErr)
	}
	lines = append(lines, "")
	if m.trimEditing && m.trimError != "" {
		lines = append(lines, "Validation: "+m.trimError, "")
	}
	if strings.TrimSpace(m.board.ValidationErr) != "" {
		lines = append(lines, "Validation: "+m.board.ValidationErr, "")
	}
	if selected == nil {
		lines = append(lines,
			"No selected bites yet.",
			"Press 3 for the board, focus a candidate, then press space to add it to the selected cut.",
		)
	} else {
		lines = append(lines,
			fmt.Sprintf("Selected: %s (%s)", selected.Label, selected.ID),
			fmt.Sprintf("Status:   %s", selected.Status),
			fmt.Sprintf("Segment:  %d", selected.Segment),
			fmt.Sprintf("Timecode: %s", selected.displayTimecode()),
			"Text:     "+selected.Text,
			"Purpose:  "+defaultIfBlank(selected.Purpose, "(none yet)"),
			"Rationale: "+defaultIfBlank(selected.Rationale, "(none yet)")+" (editable notes)",
			"Notes:    "+defaultIfBlank(selected.Rationale, "(none yet)"),
		)
		if selected.ReplacesID != "" {
			lines = append(lines, "Replaces: "+selected.ReplacesID)
		}
		if m.trimEditing {
			lines = append(lines,
				"",
				"Editing selected bite trim:",
				m.trimStart.View(),
				m.trimEnd.View(),
			)
			if m.trimError != "" {
				lines = append(lines, "Validation: "+m.trimError)
			}
			lines = append(lines, "Enter saves; Tab switches start/end; Esc cancels.")
			return strings.Join(lines, "\n")
		}
		if m.board.Editing {
			lines = append(lines,
				"",
				"Editing selected bite "+m.biteEditModeLabel()+":",
				m.biteEdit.View(),
			)
			if m.board.ValidationErr != "" {
				lines = append(lines, "Validation: "+m.board.ValidationErr)
			}
			lines = append(lines, "Enter saves; Esc cancels.")
			return strings.Join(lines, "\n")
		}
	}
	lines = append(lines, "")
	if candidate != nil {
		lines = append(lines,
			fmt.Sprintf("Focused candidate for replacement: %s (%s)", candidate.Label, candidate.ID),
			"Candidate text: "+candidate.Text,
			"Candidate rationale: "+defaultIfBlank(candidate.Rationale, "(none yet)"),
		)
	}
	lines = append(lines, "")
	lines = append(lines,
		"Controls: e edits purpose; l label; n notes; t trims start/end; r replaces selected with focused candidate; u/d reorders; space removes selected.",
		"Press 3 to return to the full board.",
	)
	return strings.Join(lines, "\n")
}

func defaultBiteBoard() biteBoardState {
	return biteBoardState{
		Candidates: []biteCard{
			{
				ID:        "candidate-001",
				Label:     "Problem setup",
				Segment:   0,
				TCIn:      "00:00:00:00",
				TCOut:     "00:00:08:00",
				Timecode:  "00:00:00:00 - 00:00:08:00",
				Text:      "Host sets up the story problem.",
				Purpose:   "Open the cut with clear context.",
				Rationale: "Introduces the story problem before the proof point lands.",
				Status:    "candidate",
			},
			{
				ID:        "candidate-002",
				Label:     "Constraint quote",
				Segment:   1,
				TCIn:      "00:00:08:00",
				TCOut:     "00:00:18:00",
				Timecode:  "00:00:08:00 - 00:00:18:00",
				Text:      "Guest names the constraint that makes the bite useful.",
				Purpose:   "Explain why the proof point matters.",
				Rationale: "Names the constraint so the selected cut has stakes.",
				Status:    "candidate",
			},
			{
				ID:        "candidate-003",
				Label:     "Resolution line",
				Segment:   2,
				TCIn:      "00:00:18:00",
				TCOut:     "00:00:27:00",
				Timecode:  "00:00:18:00 - 00:00:27:00",
				Text:      "The key quote resolves the sequence premise.",
				Purpose:   "Close with the strongest evidence.",
				Rationale: "Gives the edit a clean button after the setup.",
				Status:    "candidate",
			},
		},
		Selected: []biteCard{
			{
				ID:        "selected-001",
				Label:     "Opening proof point",
				Segment:   0,
				TCIn:      "00:00:00:00",
				TCOut:     "00:00:08:00",
				Timecode:  "00:00:00:00 - 00:00:08:00",
				Text:      "Host sets up the story problem.",
				Purpose:   "Start with a concise setup.",
				Rationale: "Starts with the clearest setup for the sequence.",
				Status:    "selected",
			},
		},
	}
}

func (m Model) boardContent() string {
	lines := []string{
		"Candidate bites",
	}
	if strings.TrimSpace(m.sequencePlanPath) != "" {
		lines = append(lines, "Exportable sequence plan: "+m.sequencePlanPath)
	}
	if validationErr := strings.TrimSpace(firstNonBlank(m.board.ValidationErr, m.boardValidationError())); validationErr != "" {
		lines = append(lines, "Export disabled: "+validationErr)
	}
	for i, bite := range m.board.Candidates {
		marker := "  "
		if m.board.FocusColumn == boardCandidates && i == m.board.CandidateIndex {
			marker = "> "
		}
		lines = append(lines, fmt.Sprintf("%s[%d] %s — seg %d — %s — %s", marker, i+1, bite.Label, bite.Segment, bite.Timecode, fitLine(bite.Text, 34)))
		if m.board.FocusColumn == boardCandidates && i == m.board.CandidateIndex {
			lines = append(lines, "    Rationale: "+fitLine(defaultIfBlank(bite.Rationale, "(none yet)"), 64))
		}
	}
	lines = append(lines, "", "Selected cut")
	if len(m.board.Selected) == 0 {
		lines = append(lines, "  (empty — focus a candidate and press space to add it)")
	} else {
		for i, bite := range m.board.Selected {
			marker := "  "
			if m.board.FocusColumn == boardSelected && i == m.board.SelectedIndex {
				marker = "> "
			}
			replacement := ""
			if bite.ReplacesID != "" {
				replacement = " replaces " + bite.ReplacesID
			}
			lines = append(lines, fmt.Sprintf("%s%d. %s — %s%s — %s — %s", marker, i+1, bite.Label, bite.Status, replacement, biteTimecode(bite), fitLine(bite.Purpose, 34)))
			if m.board.FocusColumn == boardSelected && i == m.board.SelectedIndex {
				lines = append(lines, "    Notes: "+fitLine(defaultIfBlank(bite.Rationale, "(none yet)"), 64))
			}
		}
	}
	return strings.Join(lines, "\n")
}

func (m *Model) applyBoardData(data bridge.BoardData) {
	if strings.TrimSpace(data.SequencePlanPath) != "" {
		m.sequencePlanPath = data.SequencePlanPath
		m.config.SequencePlan = data.SequencePlanPath
	}
	m.board.Candidates = biteCardsFromBridge(data.Candidates, "candidate")
	m.board.Selected = biteCardsFromBridge(data.Selected, "selected")
	m.board.CandidateIndex = clampIndex(m.board.CandidateIndex, len(m.board.Candidates))
	m.board.SelectedIndex = clampIndex(m.board.SelectedIndex, len(m.board.Selected))
	m.board.FocusColumn = boardCandidates
	m.boardHydrated = true
}

func biteCardsFromBridge(items []bridge.BiteCardData, fallbackStatus string) []biteCard {
	cards := make([]biteCard, 0, len(items))
	for _, item := range items {
		status := item.Status
		if strings.TrimSpace(status) == "" {
			status = fallbackStatus
		}
		replaces := ""
		if item.ReplacesBiteID != nil {
			replaces = *item.ReplacesBiteID
		}
		tcIn, tcOut := normalizedCardTimecodes(item.Timecode, item.TCIn, item.TCOut)
		cards = append(cards, biteCard{
			ID:         defaultIfBlank(item.BiteID, item.Label),
			Label:      defaultIfBlank(item.Label, item.BiteID),
			Segment:    item.SegmentIndex,
			TCIn:       tcIn,
			TCOut:      tcOut,
			Timecode:   joinedTimecode(tcIn, tcOut),
			Text:       item.Text,
			Purpose:    item.Purpose,
			Rationale:  item.Rationale,
			Status:     status,
			ReplacesID: replaces,
		})
	}
	return cards
}

func generationSequencePlanPath(events []bridge.GenerationEvent) string {
	return eventArtifactPath(events, "sequence_plan")
}

func eventArtifactPath(events []bridge.GenerationEvent, kind string) string {
	for _, event := range events {
		if event.Event == bridge.GenerationEventArtifact && event.Kind == kind && strings.TrimSpace(event.Path) != "" {
			return strings.TrimSpace(event.Path)
		}
	}
	return ""
}

func (m Model) selectedBoardJSON() (string, error) {
	type selectedBiteIntent struct {
		BiteID         string `json:"bite_id"`
		Label          string `json:"label,omitempty"`
		SegmentIndex   int    `json:"segment_index"`
		TCIn           string `json:"tc_in"`
		TCOut          string `json:"tc_out"`
		Timecode       string `json:"timecode,omitempty"`
		Text           string `json:"text,omitempty"`
		Purpose        string `json:"purpose,omitempty"`
		Rationale      string `json:"rationale,omitempty"`
		Status         string `json:"status"`
		ReplacesBiteID string `json:"replaces_bite_id,omitempty"`
	}
	type selectedBoardIntent struct {
		SelectedBites []selectedBiteIntent `json:"selected_bites"`
	}
	if len(m.board.Selected) == 0 {
		return "", fmt.Errorf("selected sequence must include at least one bite")
	}
	payload := selectedBoardIntent{SelectedBites: make([]selectedBiteIntent, 0, len(m.board.Selected))}
	for _, bite := range m.board.Selected {
		tcIn, tcOut := bite.trimRange()
		payload.SelectedBites = append(payload.SelectedBites, selectedBiteIntent{
			BiteID:         bite.ID,
			Label:          bite.Label,
			SegmentIndex:   bite.Segment,
			TCIn:           tcIn,
			TCOut:          tcOut,
			Timecode:       joinedTimecode(tcIn, tcOut),
			Text:           bite.Text,
			Purpose:        bite.Purpose,
			Rationale:      bite.Rationale,
			Status:         defaultIfBlank(bite.Status, "selected"),
			ReplacesBiteID: bite.ReplacesID,
		})
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}
	return string(encoded), nil
}

func (m Model) currentCandidateBite() *biteCard {
	if len(m.board.Candidates) == 0 || m.board.CandidateIndex < 0 || m.board.CandidateIndex >= len(m.board.Candidates) {
		return nil
	}
	return &m.board.Candidates[m.board.CandidateIndex]
}

func (m Model) currentSelectedBite() *biteCard {
	if len(m.board.Selected) == 0 || m.board.SelectedIndex < 0 || m.board.SelectedIndex >= len(m.board.Selected) {
		return nil
	}
	return &m.board.Selected[m.board.SelectedIndex]
}

func (m Model) handleBoardKey(msg tea.KeyMsg) (Model, tea.Cmd, bool) {
	switch {
	case key.Matches(msg, keys.boardLeft):
		m.board.FocusColumn = boardCandidates
		m.status = "Candidate bite column focused."
	case key.Matches(msg, keys.boardRight):
		m.board.FocusColumn = boardSelected
		m.status = "Selected cut column focused."
	case key.Matches(msg, keys.boardUp):
		m = m.moveBoardFocus(-1)
	case key.Matches(msg, keys.boardDown):
		m = m.moveBoardFocus(1)
	case key.Matches(msg, keys.boardToggle):
		m = m.toggleFocusedBite()
	case key.Matches(msg, keys.editBite):
		m = m.startBiteEdit(biteEditPurpose)
	case key.Matches(msg, keys.editBiteLabel):
		m = m.startBiteEdit(biteEditLabel)
	case key.Matches(msg, keys.editBiteNotes):
		m = m.startBiteEdit(biteEditNotes)
	case key.Matches(msg, keys.trimBite):
		m = m.startBiteTrimEdit()
	case key.Matches(msg, keys.trimBiteStart):
		m = m.startBiteEdit(biteEditTrimStart)
	case key.Matches(msg, keys.trimBiteEnd):
		m = m.startBiteEdit(biteEditTrimEnd)
	case key.Matches(msg, keys.replaceBite):
		m = m.replaceSelectedWithCandidate()
	case key.Matches(msg, keys.moveBiteUp):
		m = m.moveSelectedBite(-1)
	case key.Matches(msg, keys.moveBiteDown):
		m = m.moveSelectedBite(1)
	default:
		return m, nil, false
	}
	m.refreshViewport()
	return m, nil, true
}

func (m Model) startBiteTrimEdit() Model {
	selected := m.currentSelectedBite()
	if selected == nil {
		m.status = "Select a bite before trimming it."
		return m
	}
	start, end := selected.trimRange()
	m.trimStart.SetValue(start)
	m.trimEnd.SetValue(end)
	m.trimFocus = 0
	m.trimError = ""
	m.trimEditing = true
	m.activeScreen = screenBite
	m.board.FocusColumn = boardSelected
	m.trimStart.Focus()
	m.trimEnd.Blur()
	m.status = fmt.Sprintf("Trimming %s.", selected.Label)
	return m
}

func (m *Model) stopBiteTrimEdit(status string) {
	m.trimEditing = false
	m.trimError = ""
	m.trimStart.Blur()
	m.trimEnd.Blur()
	m.status = status
}

func (m *Model) toggleTrimFocus() {
	if m.trimFocus == 0 {
		m.trimFocus = 1
		m.trimStart.Blur()
		m.trimEnd.Focus()
		return
	}
	m.trimFocus = 0
	m.trimEnd.Blur()
	m.trimStart.Focus()
}

func (m Model) boardValidationError() string {
	if strings.TrimSpace(m.board.ValidationErr) != "" {
		return strings.TrimSpace(m.board.ValidationErr)
	}
	if len(m.board.Selected) == 0 {
		return "selected sequence must include at least one bite"
	}
	for _, bite := range m.board.Selected {
		start, end := bite.trimRange()
		if validationErr := validateTrimRange(start, end); validationErr != "" {
			return fmt.Sprintf("%s: %s", bite.Label, validationErr)
		}
		if strings.TrimSpace(bite.Label) == "" {
			return fmt.Sprintf("%s: label cannot be blank", defaultIfBlank(bite.ID, "selected bite"))
		}
	}
	return ""
}

func (m Model) handleBiteTrimKey(msg tea.KeyMsg) (Model, tea.Cmd) {
	switch {
	case msg.Type == tea.KeyCtrlC:
		return m, tea.Quit
	case key.Matches(msg, keys.escape):
		m.stopBiteTrimEdit("Cancelled selected bite trim edit.")
		m.refreshViewport()
		return m, nil
	case key.Matches(msg, keys.next), key.Matches(msg, keys.prev):
		m.toggleTrimFocus()
		m.status = "Trim field focus changed."
		m.refreshViewport()
		return m, nil
	case msg.Type == tea.KeyEnter:
		start := strings.TrimSpace(m.trimStart.Value())
		end := strings.TrimSpace(m.trimEnd.Value())
		validationError := validateTrimRange(start, end)
		if validationError != "" {
			m.trimError = trimEditorValidationMessage(validationError)
			m.status = "Invalid trim; fix the inline validation error before saving."
			m.refreshViewport()
			return m, nil
		}
		if m.currentSelectedBite() != nil {
			m.board.Selected[m.board.SelectedIndex].TCIn = start
			m.board.Selected[m.board.SelectedIndex].TCOut = end
			m.board.Selected[m.board.SelectedIndex].Timecode = joinedTimecode(start, end)
			m.status = fmt.Sprintf("Trimmed %s to %s.", m.board.Selected[m.board.SelectedIndex].Label, joinedTimecode(start, end))
		}
		m.stopBiteTrimEdit(m.status)
		m.refreshViewport()
		return m, nil
	}

	var cmd tea.Cmd
	if m.trimFocus == 0 {
		m.trimStart, cmd = m.trimStart.Update(msg)
	} else {
		m.trimEnd, cmd = m.trimEnd.Update(msg)
	}
	m.trimError = ""
	m.refreshViewport()
	return m, cmd
}

func trimEditorValidationMessage(err string) string {
	if err == "trim start must be before trim end" {
		return "Start timecode must be before end timecode."
	}
	return err
}

func (m Model) handleBiteEditKey(msg tea.KeyMsg) (Model, tea.Cmd) {
	switch {
	case msg.Type == tea.KeyCtrlC:
		return m, tea.Quit
	case key.Matches(msg, keys.escape):
		m.board.Editing = false
		m.board.EditMode = biteEditNone
		m.biteEdit.Blur()
		m.status = "Cancelled selected bite edit."
		m.refreshViewport()
		return m, nil
	case msg.Type == tea.KeyEnter:
		if err := m.saveBiteEdit(); err != "" {
			m.board.ValidationErr = err
			m.status = "Edit blocked: " + err
			m.refreshViewport()
			return m, nil
		}
		m.board.Editing = false
		m.board.EditMode = biteEditNone
		m.biteEdit.Blur()
		m.board.ValidationErr = m.boardValidationError()
		m.status = "Saved selected bite edit."
		m.refreshViewport()
		return m, nil
	}
	var cmd tea.Cmd
	m.biteEdit, cmd = m.biteEdit.Update(msg)
	m.refreshViewport()
	return m, cmd
}

func (m Model) moveBoardFocus(delta int) Model {
	if m.board.FocusColumn == boardSelected {
		m.board.SelectedIndex = clampIndex(m.board.SelectedIndex+delta, len(m.board.Selected))
		m.status = "Selected bite focus moved."
		return m
	}
	m.board.CandidateIndex = clampIndex(m.board.CandidateIndex+delta, len(m.board.Candidates))
	m.status = "Candidate bite focus moved."
	return m
}

func (m Model) toggleFocusedBite() Model {
	if m.board.FocusColumn == boardSelected {
		if len(m.board.Selected) == 0 {
			m.status = "Selected cut is already empty."
			return m
		}
		removed := m.board.Selected[m.board.SelectedIndex]
		m.board.Selected = append(m.board.Selected[:m.board.SelectedIndex], m.board.Selected[m.board.SelectedIndex+1:]...)
		m.board.SelectedIndex = clampIndex(m.board.SelectedIndex, len(m.board.Selected))
		m.status = fmt.Sprintf("Removed %s from the selected cut.", removed.Label)
		return m
	}

	candidate := m.currentCandidateBite()
	if candidate == nil {
		m.status = "No candidate bite is available to select."
		return m
	}
	for _, selected := range m.board.Selected {
		if selected.ID == candidate.ID {
			m.status = fmt.Sprintf("%s is already in the selected cut.", candidate.Label)
			return m
		}
	}
	selected := *candidate
	selected.Status = "selected"
	m.board.Selected = append(m.board.Selected, selected)
	m.board.SelectedIndex = len(m.board.Selected) - 1
	m.board.FocusColumn = boardSelected
	m.status = fmt.Sprintf("Added %s to the selected cut.", candidate.Label)
	return m
}

func (m Model) startBiteEdit(mode biteEditMode) Model {
	selected := m.currentSelectedBite()
	if selected == nil {
		m.status = "Select a bite before editing it."
		return m
	}
	m.activeScreen = screenBite
	m.board.FocusColumn = boardSelected
	m.board.Editing = true
	m.board.EditMode = mode
	m.biteEdit.Prompt = m.biteEditPrompt(mode)
	m.biteEdit.SetValue(m.biteEditValue(selected, mode))
	m.biteEdit.Focus()
	m.status = fmt.Sprintf("Editing %s for %s.", m.biteEditModeLabel(), selected.Label)
	return m
}

func (m Model) biteEditValue(selected *biteCard, mode biteEditMode) string {
	switch mode {
	case biteEditLabel:
		return selected.Label
	case biteEditNotes:
		return selected.Rationale
	case biteEditTrimStart:
		tcIn, _ := splitTimecodeRange(selected.Timecode)
		return firstNonBlank(selected.TCIn, tcIn)
	case biteEditTrimEnd:
		_, tcOut := splitTimecodeRange(selected.Timecode)
		return firstNonBlank(selected.TCOut, tcOut)
	default:
		return selected.Purpose
	}
}

func (m Model) biteEditPrompt(mode biteEditMode) string {
	switch mode {
	case biteEditLabel:
		return "Label: "
	case biteEditNotes:
		return "Notes: "
	case biteEditTrimStart:
		return "Start: "
	case biteEditTrimEnd:
		return "End: "
	default:
		return "Purpose: "
	}
}

func (m Model) biteEditModeLabel() string {
	switch m.board.EditMode {
	case biteEditLabel:
		return "label"
	case biteEditNotes:
		return "notes"
	case biteEditTrimStart:
		return "trim start"
	case biteEditTrimEnd:
		return "trim end"
	default:
		return "purpose"
	}
}

func (m *Model) saveBiteEdit() string {
	if m.currentSelectedBite() == nil {
		return "select a bite before saving an edit"
	}
	value := strings.TrimSpace(m.biteEdit.Value())
	selected := &m.board.Selected[m.board.SelectedIndex]
	switch m.board.EditMode {
	case biteEditLabel:
		if value == "" {
			return "label cannot be blank"
		}
		selected.Label = value
	case biteEditNotes:
		selected.Rationale = value
	case biteEditTrimStart:
		_, rangeOut := splitTimecodeRange(selected.Timecode)
		tcOut := firstNonBlank(selected.TCOut, rangeOut)
		if err := validateTrimRange(value, tcOut); err != "" {
			return err
		}
		selected.TCIn = value
		selected.TCOut = tcOut
		selected.Timecode = joinedTimecode(value, tcOut)
	case biteEditTrimEnd:
		rangeIn, _ := splitTimecodeRange(selected.Timecode)
		tcIn := firstNonBlank(selected.TCIn, rangeIn)
		if err := validateTrimRange(tcIn, value); err != "" {
			return err
		}
		selected.TCIn = tcIn
		selected.TCOut = value
		selected.Timecode = joinedTimecode(tcIn, value)
	default:
		selected.Purpose = value
	}
	return ""
}

func (m Model) replaceSelectedWithCandidate() Model {
	selected := m.currentSelectedBite()
	candidate := m.currentCandidateBite()
	if selected == nil || candidate == nil {
		m.status = "Need both a focused selected bite and candidate bite before replacing."
		return m
	}
	replacement := *candidate
	replacement.Status = "replacement"
	replacement.ReplacesID = selected.ID
	m.board.Selected[m.board.SelectedIndex] = replacement
	m.board.FocusColumn = boardSelected
	m.status = fmt.Sprintf("Replaced %s with %s.", selected.Label, candidate.Label)
	return m
}

func (m Model) moveSelectedBite(delta int) Model {
	if len(m.board.Selected) < 2 {
		m.status = "Need at least two selected bites before reordering."
		return m
	}
	from := m.board.SelectedIndex
	to := from + delta
	if to < 0 || to >= len(m.board.Selected) {
		m.status = "Selected bite is already at that edge of the cut."
		return m
	}
	m.board.Selected[from], m.board.Selected[to] = m.board.Selected[to], m.board.Selected[from]
	m.board.SelectedIndex = to
	m.board.FocusColumn = boardSelected
	m.status = "Reordered selected bite."
	return m
}

func clampIndex(index, length int) int {
	if length <= 0 {
		return 0
	}
	if index < 0 {
		return 0
	}
	if index >= length {
		return length - 1
	}
	return index
}

func (b biteCard) trimRange() (string, string) {
	start := strings.TrimSpace(b.TCIn)
	end := strings.TrimSpace(b.TCOut)
	if start != "" || end != "" {
		return start, end
	}
	return splitTimecodeRange(b.Timecode)
}

func (b biteCard) displayTimecode() string {
	if strings.TrimSpace(b.Timecode) != "" {
		return strings.TrimSpace(b.Timecode)
	}
	start, end := b.trimRange()
	return joinedTimecode(start, end)
}

func validateTrimRange(startValue, endValue string) string {
	start := strings.TrimSpace(startValue)
	end := strings.TrimSpace(endValue)
	startFrames, startError := timecodeFrames(start)
	if startError != "" {
		return "trim start " + startError
	}
	endFrames, endError := timecodeFrames(end)
	if endError != "" {
		return "trim end " + endError
	}
	if startFrames >= endFrames {
		return "trim start must be before trim end"
	}
	return ""
}

func timecodeFrames(value string) (int, string) {
	if strings.TrimSpace(value) == "" {
		return 0, "timecode is required."
	}
	parts := strings.Split(strings.TrimSpace(value), ":")
	if len(parts) != 4 {
		return 0, "timecode must use HH:MM:SS:FF."
	}
	total := 0
	for i, part := range parts {
		if part == "" {
			return 0, "timecode must use HH:MM:SS:FF."
		}
		valuePart := 0
		for _, r := range part {
			if r < '0' || r > '9' {
				return 0, "timecode must use HH:MM:SS:FF."
			}
			valuePart = valuePart*10 + int(r-'0')
		}
		if (i == 1 || i == 2) && valuePart >= 60 {
			return 0, "timecode minutes and seconds must be below 60."
		}
		if i == 3 && valuePart >= 100 {
			return 0, "timecode frames must be below 100."
		}
		total = total*100 + valuePart
	}
	return total, ""
}

func (m Model) transcriptContent() string {
	return strings.Join([]string{
		"Transcript viewport",
		"",
		"Path: " + defaultIfBlank(m.transcript.Value(), "(not selected)"),
		"",
		"Transcript preview placeholder:",
		"  00:00:00 Speaker A: We need the edit to prove one concise idea.",
		"  00:00:07 Speaker B: The strongest moment is where the audience understands the tradeoff.",
		"  00:00:16 Speaker A: Keep the final cut short and evidence-driven.",
		"",
		"When the bridge returns real plan data, this viewport can bind to selected bite transcript ranges.",
	}, "\n")
}

func helpOverlay() string {
	return strings.Join([]string{
		"Help overlay",
		"",
		"Navigation:",
		"  1  Welcome/setup",
		"  2  Path/file selection",
		"  3  Editorial workspace",
		"  4  Bite detail / transcript viewport",
		"  5  Transcript viewport",
		"  6  Model assistant chat",
		"",
		"Actions:",
		"  Mouse            Click bracketed nav/actions directly",
		"  Tab / Shift+Tab  Move focus between file/setup fields",
		"  T                Choose transcript .txt in Finder",
		"  X                Choose Premiere XML .xml in Finder",
		"  s                Summarize transcript in Python",
		"  v                Open/send the model assistant chat",
		"  o                Ask about the focused bite from the workspace",
		"  Enter            Send a chat follow-up when the assistant screen is focused",
		"  space            Add focused candidate or remove focused selected bite",
		"  left/right       Switch between candidate and selected bite columns",
		"  up/down or j/k   Move bite focus within the active column",
		"  e                Edit the focused selected bite purpose",
		"  t                Trim the focused selected bite start/end timecodes",
		"  r                Replace selected bite with focused candidate",
		"  u / d            Move focused selected bite up / down",
		"  g                Generate/regenerate candidate bites",
		"  x                Export selected bites through Python validation/XMEML",
		"  a                Accept the assistant's Suggested Creative Brief into the creative ask field",
		"  h or Esc         Toggle this help overlay",
		"  q / Ctrl+C       Quit",
		"",
		"Bridge boundary: the UI reuses internal/bridge validation and displays structured errors; it does not duplicate subprocess logic.",
	}, "\n")
}

func extractSuggestedBrief(suggestion string) string {
	trimmed := strings.TrimSpace(suggestion)
	lower := strings.ToLower(trimmed)
	startLabel := "suggested creative brief:"
	start := strings.Index(lower, startLabel)
	if start == -1 {
		return trimmed
	}
	body := strings.TrimSpace(trimmed[start+len(startLabel):])
	bodyLower := strings.ToLower(body)
	end := len(body)
	for _, marker := range []string{"\nwhy this direction works:", "\ncandidate story beats:", "\nprompt tuning notes:"} {
		if index := strings.Index(bodyLower, marker); index >= 0 && index < end {
			end = index
		}
	}
	return strings.TrimSpace(body[:end])
}

func extractAssistantSuggestion(raw string) (string, error) {
	type envelope struct {
		OK   bool `json:"ok"`
		Data struct {
			Suggestion string `json:"suggestion"`
		} `json:"data"`
		Error struct {
			Code    string `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}
	var parsed envelope
	if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
		return "", err
	}
	if !parsed.OK {
		return "", fmt.Errorf("%s: %s", parsed.Error.Code, parsed.Error.Message)
	}
	suggestion := strings.TrimSpace(parsed.Data.Suggestion)
	if suggestion == "" {
		return "", fmt.Errorf("assistant bridge response did not include data.suggestion")
	}
	return suggestion, nil
}

func fitLine(value string, width int) string {
	value = strings.TrimSpace(value)
	if width <= 0 || len(value) <= width {
		return value
	}
	if width <= 1 {
		return "…"
	}
	return strings.TrimSpace(value[:width-1]) + "…"
}

func splitDisplayLines(value string, width int) []string {
	parts := strings.Split(strings.TrimSpace(value), "\n")
	if len(parts) == 0 {
		return []string{""}
	}
	lines := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			lines = append(lines, "")
			continue
		}
		lines = append(lines, fitLine(part, width))
	}
	return lines
}

func outputPreview(outputDir string) string {
	if strings.TrimSpace(outputDir) == "" {
		return filepath.Join(".", "output")
	}
	return filepath.Clean(outputDir)
}

func defaultIfBlank(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

var keys = struct {
	quit             key.Binding
	next             key.Binding
	prev             key.Binding
	help             key.Binding
	escape           key.Binding
	validate         key.Binding
	askSelected      key.Binding
	summary          key.Binding
	generate         key.Binding
	export           key.Binding
	acceptSuggestion key.Binding
	browseTranscript key.Binding
	browseXML        key.Binding
	browseTranscriptB key.Binding
	browseXMLB        key.Binding
	welcome          key.Binding
	files            key.Binding
	plan             key.Binding
	assistant        key.Binding
	bite             key.Binding
	transcript       key.Binding
	boardLeft        key.Binding
	boardRight       key.Binding
	boardUp          key.Binding
	boardDown        key.Binding
	boardToggle      key.Binding
	editBite         key.Binding
	editBiteLabel    key.Binding
	editBiteNotes    key.Binding
	trimBiteStart    key.Binding
	trimBiteEnd      key.Binding
	replaceBite      key.Binding
	trimBite         key.Binding
	moveBiteUp       key.Binding
	moveBiteDown     key.Binding
}{
	quit:             key.NewBinding(key.WithKeys("q", "ctrl+c")),
	next:             key.NewBinding(key.WithKeys("tab")),
	prev:             key.NewBinding(key.WithKeys("shift+tab")),
	help:             key.NewBinding(key.WithKeys("h", "?")),
	escape:           key.NewBinding(key.WithKeys("esc")),
	validate:         key.NewBinding(key.WithKeys("v", "ctrl+r")),
	askSelected:      key.NewBinding(key.WithKeys("o")),
	summary:          key.NewBinding(key.WithKeys("s")),
	generate:         key.NewBinding(key.WithKeys("g")),
	export:           key.NewBinding(key.WithKeys("x")),
	acceptSuggestion: key.NewBinding(key.WithKeys("a")),
	browseTranscript: key.NewBinding(key.WithKeys("T")),
	browseXML:        key.NewBinding(key.WithKeys("X")),
	browseTranscriptB: key.NewBinding(key.WithKeys("Y")),
	browseXMLB:        key.NewBinding(key.WithKeys("U")),
	welcome:          key.NewBinding(key.WithKeys("1")),
	files:            key.NewBinding(key.WithKeys("2")),
	plan:             key.NewBinding(key.WithKeys("3")),
	assistant:        key.NewBinding(key.WithKeys("6")),
	bite:             key.NewBinding(key.WithKeys("4")),
	transcript:       key.NewBinding(key.WithKeys("5")),
	boardLeft:        key.NewBinding(key.WithKeys("left")),
	boardRight:       key.NewBinding(key.WithKeys("right")),
	boardUp:          key.NewBinding(key.WithKeys("up", "k")),
	boardDown:        key.NewBinding(key.WithKeys("down", "j")),
	boardToggle:      key.NewBinding(key.WithKeys(" ", "enter")),
	editBite:         key.NewBinding(key.WithKeys("e")),
	editBiteLabel:    key.NewBinding(key.WithKeys("l")),
	editBiteNotes:    key.NewBinding(key.WithKeys("n")),
	trimBiteStart:    key.NewBinding(key.WithKeys("[")),
	trimBiteEnd:      key.NewBinding(key.WithKeys("]")),
	trimBite:         key.NewBinding(key.WithKeys("t")),
	replaceBite:      key.NewBinding(key.WithKeys("r")),
	moveBiteUp:       key.NewBinding(key.WithKeys("u")),
	moveBiteDown:     key.NewBinding(key.WithKeys("d")),
}

var (
	titleStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("212")).MarginBottom(1)
	subtitleStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("245")).MarginBottom(1)
	navStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("111")).MarginBottom(1)
	boxStyle      = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("62")).Padding(1, 2).MarginBottom(1)
	statusStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("229")).Background(lipgloss.Color("62")).Padding(0, 1)
	helpStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("245")).MarginTop(1)
)
