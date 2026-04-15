package app

import (
	"bytes"
	"context"
	"testing"
)

func TestRunDoesNotPanicWhenParsingFlags(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	defer func() {
		if recovered := recover(); recovered != nil {
			t.Fatalf("Run panicked while registering or parsing flags: %v", recovered)
		}
	}()

	var stdout bytes.Buffer
	var stderr bytes.Buffer

	err := Run(ctx, []string{"--help"}, bytes.NewBuffer(nil), &stdout, &stderr)
	if err != nil {
		t.Fatalf("Run(--help) error = %v, want nil", err)
	}
}
