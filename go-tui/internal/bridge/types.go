package bridge

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"strings"
)

const (
	BridgeSchemaVersion           = "go_tui_bridge.v1"
	GenerationEventsSchemaVersion = "go_tui_generation_events.v1"
)

type Operation string

const (
	OperationSetup      Operation = "setup"
	OperationMedia      Operation = "media"
	OperationTranscript Operation = "transcript"
	OperationSummary    Operation = "summary"
	OperationPlan       Operation = "plan"
	OperationBite       Operation = "bite"
	OperationAssistant  Operation = "assistant"
)

type BridgeEnvelope struct {
	OK            bool            `json:"ok"`
	SchemaVersion string          `json:"schema_version"`
	Operation     Operation       `json:"operation"`
	Data          json.RawMessage `json:"data,omitempty"`
	Error         *BridgeError    `json:"error,omitempty"`
}

type BridgeError struct {
	Code                string         `json:"code"`
	Type                string         `json:"type"`
	Message             string         `json:"message"`
	ExpectedInputFormat string         `json:"expected_input_format,omitempty"`
	NextAction          string         `json:"next_action,omitempty"`
	Recoverable         bool           `json:"recoverable"`
	Stage               string         `json:"stage,omitempty"`
	Details             map[string]any `json:"details,omitempty"`
}

type SetupData struct {
	Version      string `json:"version"`
	Capabilities struct {
		Transport       string      `json:"transport"`
		MutatesOutput   bool        `json:"mutates_output"`
		Operations      []Operation `json:"operations"`
		RuntimeBoundary struct {
			PythonAuthoritativeFor []string `json:"python_authoritative_for"`
			GoTUIRole              string   `json:"go_tui_role"`
			GenerationTransport    string   `json:"generation_transport"`
		} `json:"runtime_boundary"`
	} `json:"capabilities"`
	Defaults struct {
		Model        string `json:"model"`
		Host         string `json:"host"`
		Timeout      int    `json:"timeout"`
		ThinkingMode string `json:"thinking_mode"`
		OutputDir    string `json:"output_dir"`
	} `json:"defaults"`
	Paths struct {
		Transcript   string `json:"transcript"`
		XML          string `json:"xml"`
		SequencePlan string `json:"sequence_plan"`
	} `json:"paths"`
}

type SourceData struct {
	SourceName string `json:"source_name"`
	SourcePath string `json:"source_path"`
	PathURL    string `json:"pathurl"`
	Duration   int    `json:"duration"`
	Timebase   int    `json:"timebase"`
	NTSC       bool   `json:"ntsc"`
}

type TranscriptSegment struct {
	Index   int    `json:"index"`
	Speaker string `json:"speaker"`
	Text    string `json:"text"`
	TCIn    string `json:"tc_in"`
	TCOut   string `json:"tc_out"`
}

type TranscriptWindow struct {
	TotalCount  int                 `json:"total_count"`
	StartIndex  int                 `json:"start_index"`
	Count       int                 `json:"count"`
	Query       string              `json:"query"`
	Segments    []TranscriptSegment `json:"segments"`
	DisplayText string              `json:"display_text"`
}

type MediaData struct {
	Source     SourceData       `json:"source"`
	Transcript TranscriptWindow `json:"transcript"`
}

type TranscriptData struct {
	Transcript TranscriptWindow `json:"transcript"`
}

type SummaryData struct {
	SummaryText string `json:"summary_text"`
}

type PlanOption struct {
	OptionID                 string  `json:"option_id"`
	Name                     string  `json:"name"`
	Description              string  `json:"description"`
	EstimatedDurationSeconds float64 `json:"estimated_duration_seconds"`
	BiteCount                int     `json:"bite_count"`
	SelectedBiteCount        int     `json:"selected_bite_count"`
	SelectedDurationSeconds  float64 `json:"selected_duration_seconds"`
}

type BiteCardData struct {
	BiteID          string  `json:"bite_id"`
	OptionID        string  `json:"option_id"`
	Label           string  `json:"label"`
	SegmentIndex    int     `json:"segment_index"`
	TCIn            string  `json:"tc_in"`
	TCOut           string  `json:"tc_out"`
	Timecode        string  `json:"timecode"`
	Speaker         string  `json:"speaker"`
	Text            string  `json:"text"`
	Purpose         string  `json:"purpose"`
	Rationale       string  `json:"rationale"`
	Status          string  `json:"status"`
	ReplacesBiteID  *string `json:"replaces_bite_id"`
	DurationSeconds float64 `json:"duration_seconds"`
}

type BoardData struct {
	OptionID         string         `json:"option_id"`
	SequencePlanPath string         `json:"sequence_plan_path"`
	Candidates       []BiteCardData `json:"candidates"`
	Selected         []BiteCardData `json:"selected"`
}

type PlanData struct {
	Source           SourceData      `json:"source"`
	Plan             json.RawMessage `json:"plan"`
	SequencePlanPath string          `json:"sequence_plan_path"`
	Options          []PlanOption    `json:"options"`
	CurrentOptionID  string          `json:"current_option_id"`
	Board            BoardData       `json:"board"`
	SummaryText      string          `json:"summary_text"`
}

type BiteData struct {
	Source          SourceData        `json:"source"`
	Option          PlanOption        `json:"option"`
	Bite            json.RawMessage   `json:"bite"`
	Segment         TranscriptSegment `json:"segment"`
	DurationSeconds float64           `json:"duration_seconds"`
}

type AssistantData struct {
	Suggestion string `json:"suggestion"`
	Model      struct {
		RequestedID     string   `json:"requested_id"`
		ResolvedID      string   `json:"resolved_id"`
		Host            string   `json:"host"`
		AvailableModels []string `json:"available_models"`
		ThinkingMode    string   `json:"thinking_mode"`
	} `json:"model"`
	Transcript struct {
		SegmentCount     int    `json:"segment_count"`
		LineByLineFormat string `json:"line_by_line_format"`
	} `json:"transcript"`
	Source           SourceData           `json:"source"`
	SelectionContext SelectionContextData `json:"selection_context"`
	PromptPreview    string               `json:"prompt_preview"`
	RawText          string               `json:"raw_text"`
}

type SelectionContextData struct {
	Question         string         `json:"question"`
	SelectedBites    []BiteCardData `json:"selected_bites"`
	SequencePlanPath string         `json:"sequence_plan_path"`
	OptionID         string         `json:"option_id"`
}

type GenerationEventName string

const (
	GenerationEventStarted   GenerationEventName = "started"
	GenerationEventProgress  GenerationEventName = "progress"
	GenerationEventArtifact  GenerationEventName = "artifact"
	GenerationEventCompleted GenerationEventName = "completed"
	GenerationEventError     GenerationEventName = "error"
)

type GenerationEvent struct {
	Event         GenerationEventName `json:"event"`
	SchemaVersion string              `json:"schema_version"`
	RequestID     string              `json:"request_id,omitempty"`
	Stage         string              `json:"stage,omitempty"`
	Message       string              `json:"message,omitempty"`
	Kind          string              `json:"kind,omitempty"`
	Path          string              `json:"path,omitempty"`
	OK            *bool               `json:"ok,omitempty"`
	Error         *BridgeError        `json:"error,omitempty"`
	Data          json.RawMessage     `json:"data,omitempty"`
}

func DecodeEnvelope(stdout string) (BridgeEnvelope, error) {
	var envelope BridgeEnvelope
	trimmed := strings.TrimSpace(stdout)
	if trimmed == "" {
		return envelope, fmt.Errorf("decode bridge envelope: stdout is empty")
	}
	if err := json.Unmarshal([]byte(trimmed), &envelope); err != nil {
		return envelope, fmt.Errorf("decode bridge envelope: %w", err)
	}
	if envelope.SchemaVersion != BridgeSchemaVersion {
		return envelope, fmt.Errorf("decode bridge envelope: schema_version %q, want %q", envelope.SchemaVersion, BridgeSchemaVersion)
	}
	if envelope.Operation == "" {
		return envelope, fmt.Errorf("decode bridge envelope: operation is required")
	}
	if !envelope.OK && envelope.Error == nil {
		return envelope, fmt.Errorf("decode bridge envelope: error envelope missing error payload")
	}
	return envelope, nil
}

func DecodeEnvelopeData[T any](envelope BridgeEnvelope) (T, error) {
	var data T
	if !envelope.OK {
		if envelope.Error != nil {
			return data, fmt.Errorf("decode bridge data: bridge error %s: %s", envelope.Error.Code, envelope.Error.Message)
		}
		return data, fmt.Errorf("decode bridge data: bridge error")
	}
	if len(envelope.Data) == 0 {
		return data, fmt.Errorf("decode bridge data: data payload is empty")
	}
	if err := json.Unmarshal(envelope.Data, &data); err != nil {
		return data, fmt.Errorf("decode bridge data: %w", err)
	}
	return data, nil
}

func DecodeResultData[T any](result RunResult) (T, error) {
	envelope, err := DecodeEnvelope(result.Stdout)
	if err != nil {
		var zero T
		return zero, err
	}
	return DecodeEnvelopeData[T](envelope)
}

func ParseGenerationEvents(stdout string) ([]GenerationEvent, error) {
	return ReadGenerationEvents(strings.NewReader(stdout))
}

func ReadGenerationEvents(reader io.Reader) ([]GenerationEvent, error) {
	scanner := bufio.NewScanner(reader)
	scanner.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)

	var events []GenerationEvent
	for lineNumber := 1; scanner.Scan(); lineNumber++ {
		line := bytes.TrimSpace(scanner.Bytes())
		if len(line) == 0 {
			continue
		}
		var event GenerationEvent
		if err := json.Unmarshal(line, &event); err != nil {
			return nil, fmt.Errorf("parse generation event line %d: %w", lineNumber, err)
		}
		if event.SchemaVersion != GenerationEventsSchemaVersion {
			return nil, fmt.Errorf("parse generation event line %d: schema_version %q, want %q", lineNumber, event.SchemaVersion, GenerationEventsSchemaVersion)
		}
		if event.Event == "" {
			return nil, fmt.Errorf("parse generation event line %d: event is required", lineNumber)
		}
		if event.Event == GenerationEventError && event.Error == nil {
			return nil, fmt.Errorf("parse generation event line %d: error event missing error payload", lineNumber)
		}
		events = append(events, event)
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("parse generation events: %w", err)
	}
	if len(events) == 0 {
		return nil, fmt.Errorf("parse generation events: no events")
	}
	return events, nil
}
