package ui

import (
	"context"
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

const fieldCount = 4

type firstPassRunner interface {
	RunFirstPass(context.Context, bridge.Config) (bridge.RunResult, error)
}

type screen int

const (
	screenWelcome screen = iota
	screenFiles
	screenPlan
	screenBite
	screenTranscript
)

type pickTarget int

const (
	pickNone pickTarget = iota
	pickTranscript
	pickXML
)

type bridgeErrorState struct {
	Operation string
	Code      string
	Message   string
	Hint      string
}

type nativeFilePickedMsg struct {
	target pickTarget
	path   string
}

type nativeFilePickErrorMsg struct {
	target pickTarget
	err    error
}

// Model is a read-only Bubble Tea prototype for BiteBuilder's Go TUI lane.
type Model struct {
	ctx    context.Context
	runner firstPassRunner
	config bridge.Config

	transcript textinput.Model
	xml        textinput.Model
	brief      textarea.Model
	outputDir  textinput.Model
	viewport   viewport.Model
	picker     filepicker.Model

	activeScreen  screen
	picking       pickTarget
	focus         int
	width         int
	height        int
	status        string
	helpOpen      bool
	bridgeError   *bridgeErrorState
	bridgePreview string
}

// New constructs the read-only Go TUI model with defaults from bridge.Config.
func New(ctx context.Context, runner firstPassRunner, config bridge.Config) Model {
	transcript := textinput.New()
	transcript.Placeholder = "/path/to/timecoded-transcript.txt"
	transcript.Prompt = "Transcript: "
	transcript.SetValue(config.TranscriptPath)
	transcript.Focus()

	xml := textinput.New()
	xml.Placeholder = "/path/to/source.xml"
	xml.Prompt = "XML:        "
	xml.SetValue(config.XMLPath)

	brief := textarea.New()
	brief.Placeholder = "45 second proof-of-concept edit focused on..."
	brief.Prompt = ""
	brief.SetValue(config.Brief)
	brief.SetHeight(5)
	brief.Blur()

	outputDir := textinput.New()
	outputDir.Placeholder = "./output"
	outputDir.Prompt = "Output:     "
	outputDir.SetValue(config.OutputDir)

	picker := newFilePicker(config.RepoRoot, []string{".txt"})

	vp := viewport.New(78, 10)
	model := Model{
		ctx:          ctx,
		runner:       runner,
		config:       config,
		transcript:   transcript,
		xml:          xml,
		brief:        brief,
		outputDir:    outputDir,
		viewport:     vp,
		picker:       picker,
		activeScreen: screenWelcome,
		status:       "Read-only prototype. Tab changes focus; T browses .txt; X browses .xml; v validates; h opens help.",
	}
	model.refreshViewport()
	return model
}

func (m Model) Init() tea.Cmd {
	return textinput.Blink
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
	case nativeFilePickedMsg:
		m.picking = msg.target
		m = m.applyPickedFile(msg.path)
		m.activeScreen = screenFiles
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
			m = m.validateBridgeRequest()
			m.refreshViewport()
			return m, nil
		case key.Matches(msg, keys.browseTranscript):
			return m.startFileSelection(pickTranscript, []string{".txt"}, m.transcript.Value())
		case key.Matches(msg, keys.browseXML):
			return m.startFileSelection(pickXML, []string{".xml"}, m.xml.Value())
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
			m.status = "Sequence-plan viewer selected."
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
			m.brief, cmd = m.brief.Update(msg)
		case 3:
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
		subtitleStyle.Render("Read-only prototype for planning, reviewing, and validating the Python bridge request."),
		navStyle.Render("1 Welcome • 2 Files • 3 Plan • 4 Bite • 5 Transcript • T Browse TXT • X Browse XML • v Validate • h Help • q Quit"),
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
		helpStyle.Render("Read-only mode: validation previews the bridge request; it never invokes bitebuilder.py or writes output."),
	)
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
		m.brief.Blur()
	case 3:
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
		m.brief.Focus()
	case 3:
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
			m.status = "Opening Finder to choose a transcript .txt file..."
		case pickXML:
			m.status = "Opening Finder to choose a Premiere XML .xml file..."
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
		m.status = "Browsing for a transcript .txt file. Enter selects; q cancels."
	case pickXML:
		m.status = "Browsing for a Premiere XML .xml file. Enter selects; q cancels."
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
		m.status = fmt.Sprintf("Selected transcript: %s", path)
	case pickXML:
		m.xml.SetValue(path)
		m.focus = 1
		m.status = fmt.Sprintf("Selected XML: %s", path)
	}
	m.blurFocused()
	m.focusFocused()
	m.picking = pickNone
	m.bridgeError = nil
	return m
}

func (m Model) validateBridgeRequest() Model {
	config := m.currentConfig()
	args, err := config.BuildFirstPassArgs()
	if err != nil {
		m.bridgePreview = ""
		m.bridgeError = &bridgeErrorState{
			Operation: "validate first-pass bridge request",
			Code:      "invalid_request",
			Message:   err.Error(),
			Hint:      "Complete transcript, XML, brief, repository, Python, and timeout inputs before enabling generation.",
		}
		m.status = fmt.Sprintf("Bridge validation failed: %s", err)
		m.activeScreen = screenFiles
		return m
	}

	m.bridgeError = nil
	m.bridgePreview = fmt.Sprintf("$ %s %s", config.Python, strings.Join(args, " "))
	m.status = "Bridge request valid. Preview only; no subprocess was started."
	m.activeScreen = screenPlan
	return m
}

func (m Model) currentConfig() bridge.Config {
	config := m.config
	config.TranscriptPath = strings.TrimSpace(m.transcript.Value())
	config.XMLPath = strings.TrimSpace(m.xml.Value())
	config.Brief = strings.TrimSpace(m.brief.Value())
	config.OutputDir = strings.TrimSpace(m.outputDir.Value())
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
			"This prototype surfaces bridge errors without running generation or mutating output files.",
			"Press 2 to return to path/file selection or h for help.",
		}, "\n")
	}

	switch m.activeScreen {
	case screenFiles:
		return m.filesContent()
	case screenPlan:
		return m.planContent()
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
		"This Go TUI is intentionally read-only for the prototype lane:",
		"  • collect and review file paths",
		"  • preview sequence-plan and bite-detail screens",
		"  • validate the existing Python bridge request",
		"  • surface structured bridge errors",
		"",
		fmt.Sprintf("Repository: %s", defaultIfBlank(m.config.RepoRoot, "(not set)")),
		fmt.Sprintf("Python:     %s", defaultIfBlank(m.config.Python, "(not set)")),
		"",
		"Press 2 for path/file selection, 3 for plan viewer, or h for help.",
	}, "\n")
}

func (m Model) filesContent() string {
	return strings.Join([]string{
		"Path / file selection",
		"",
		m.transcript.View(),
		"  [T] Choose transcript .txt in Finder",
		m.xml.View(),
		"  [X] Choose Premiere XML .xml in Finder",
		"Creative brief:",
		m.brief.View(),
		m.outputDir.View(),
		"",
		"These fields are editable for request preview only. Press T/X to open Finder; press v to validate; no subprocess starts.",
		fmt.Sprintf("Output basename preview: %s", outputPreview(m.outputDir.Value())),
	}, "\n")
}

func (m Model) filePickerContent() string {
	title := "Browse for file"
	switch m.picking {
	case pickTranscript:
		title = "Browse transcript (.txt)"
	case pickXML:
		title = "Browse Premiere XML (.xml)"
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
	if m.bridgePreview != "" {
		return strings.Join([]string{
			"Sequence-plan viewer",
			"",
			"Bridge request preview (read-only):",
			m.bridgePreview,
			"",
			"Bridge request valid. Preview only; no subprocess was started.",
			"Generation remains gated for a later NDJSON subprocess-events phase.",
		}, "\n")
	}

	brief := strings.TrimSpace(m.brief.Value())
	if brief == "" {
		brief = "(creative brief not entered yet)"
	}
	return strings.Join([]string{
		"Sequence-plan viewer",
		"",
		"Prototype plan outline:",
		"  1. Parse Premiere XML sequence metadata.",
		"  2. Align timecoded transcript segments to candidate bite windows.",
		"  3. Ask the generation lane for ranked bites in a future NDJSON progress stream.",
		"  4. Review selected bites before any Premiere XML export.",
		"",
		"Creative brief snapshot:",
		brief,
		"",
		"Press 4 for bite detail, 5 for transcript viewport, or v to validate bridge inputs.",
	}, "\n")
}

func (m Model) biteContent() string {
	return strings.Join([]string{
		"Bite detail / transcript viewport",
		"",
		"Selected bite: Prototype Bite 01",
		"Status: read-only placeholder until generation transport is wired.",
		"Source XML: " + defaultIfBlank(m.xml.Value(), "(not selected)"),
		"Transcript: " + defaultIfBlank(m.transcript.Value(), "(not selected)"),
		"",
		"Transcript excerpt:",
		"  [00:00:00] Host sets up the story problem.",
		"  [00:00:08] Guest names the constraint that makes the bite useful.",
		"  [00:00:18] The key quote resolves the sequence premise.",
		"",
		"Actions are intentionally disabled in this prototype: no export, no write, no generation.",
	}, "\n")
}

func (m Model) transcriptContent() string {
	return strings.Join([]string{
		"Transcript viewport",
		"",
		"Path: " + defaultIfBlank(m.transcript.Value(), "(not selected)"),
		"",
		"Read-only transcript preview placeholder:",
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
		"  3  Sequence-plan viewer",
		"  4  Bite detail / transcript viewport",
		"  5  Transcript viewport",
		"",
		"Actions:",
		"  Tab / Shift+Tab  Move focus between file/setup fields",
		"  T                Choose transcript .txt in Finder",
		"  X                Choose Premiere XML .xml in Finder",
		"  v                Validate the bridge request without running it",
		"  h or Esc         Toggle this help overlay",
		"  q / Ctrl+C       Quit",
		"",
		"Bridge boundary: the UI reuses internal/bridge validation and displays structured errors; it does not duplicate subprocess logic.",
	}, "\n")
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
	browseTranscript key.Binding
	browseXML        key.Binding
	welcome          key.Binding
	files            key.Binding
	plan             key.Binding
	bite             key.Binding
	transcript       key.Binding
}{
	quit:             key.NewBinding(key.WithKeys("q", "ctrl+c")),
	next:             key.NewBinding(key.WithKeys("tab")),
	prev:             key.NewBinding(key.WithKeys("shift+tab")),
	help:             key.NewBinding(key.WithKeys("h", "?")),
	escape:           key.NewBinding(key.WithKeys("esc")),
	validate:         key.NewBinding(key.WithKeys("v", "ctrl+r")),
	browseTranscript: key.NewBinding(key.WithKeys("T")),
	browseXML:        key.NewBinding(key.WithKeys("X")),
	welcome:          key.NewBinding(key.WithKeys("1")),
	files:            key.NewBinding(key.WithKeys("2")),
	plan:             key.NewBinding(key.WithKeys("3")),
	bite:             key.NewBinding(key.WithKeys("4")),
	transcript:       key.NewBinding(key.WithKeys("5")),
}

var (
	titleStyle    = lipgloss.NewStyle().Bold(true).Foreground(lipgloss.Color("212")).MarginBottom(1)
	subtitleStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("245")).MarginBottom(1)
	navStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("111")).MarginBottom(1)
	boxStyle      = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).BorderForeground(lipgloss.Color("62")).Padding(1, 2).MarginBottom(1)
	statusStyle   = lipgloss.NewStyle().Foreground(lipgloss.Color("229")).Background(lipgloss.Color("62")).Padding(0, 1)
	helpStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("245")).MarginTop(1)
)
