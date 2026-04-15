package bridge

import (
	"bytes"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"
)

func TestProductionGoCodeStaysWithinUISubprocessBoundary(t *testing.T) {
	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	goRoot := filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", ".."))

	forbiddenImports := map[string]string{
		"encoding/xml": "XMEML/XML generation must remain in Python",
		"net/http":     "model/runtime calls must go through the Python subprocess bridge",
	}
	forbiddenSnippets := map[string]string{
		"http.NewRequest":  "Go must not call the model runtime directly",
		"http.Client":      "Go must not call the model runtime directly",
		"http.Post(":       "Go must not call the model runtime directly",
		"os.Create(":       "Go must not write generated XMEML/plan artifacts directly",
		"os.WriteFile(":    "Go must not write generated XMEML/plan artifacts directly",
		"ioutil.WriteFile": "Go must not write generated XMEML/plan artifacts directly",
	}

	err := filepath.WalkDir(goRoot, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if entry.Name() == "vendor" {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(path, ".go") || strings.HasSuffix(path, "_test.go") {
			return nil
		}

		source, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		for snippet, reason := range forbiddenSnippets {
			if bytes.Contains(source, []byte(snippet)) {
				t.Fatalf("%s contains %q: %s", relPath(t, goRoot, path), snippet, reason)
			}
		}

		parsed, err := parser.ParseFile(token.NewFileSet(), path, source, parser.ImportsOnly)
		if err != nil {
			return err
		}
		for _, importSpec := range parsed.Imports {
			importPath, err := strconv.Unquote(importSpec.Path.Value)
			if err != nil {
				return err
			}
			if reason, forbidden := forbiddenImports[importPath]; forbidden {
				t.Fatalf("%s imports %q: %s", relPath(t, goRoot, path), importPath, reason)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walk Go TUI source: %v", err)
	}
}

func relPath(t *testing.T, base, path string) string {
	t.Helper()
	rel, err := filepath.Rel(base, path)
	if err != nil {
		return path
	}
	return rel
}
