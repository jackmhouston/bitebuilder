package main

import (
	"context"
	"fmt"
	"os"

	"github.com/jackmhouston/bitebuilder/go-tui/internal/app"
)

func main() {
	if err := app.Run(context.Background(), os.Args[1:], os.Stdin, os.Stdout, os.Stderr); err != nil {
		fmt.Fprintf(os.Stderr, "bitebuilder-tui: %v\n", err)
		os.Exit(1)
	}
}
