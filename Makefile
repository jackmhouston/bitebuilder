SHELL := /bin/bash
BITEBUILDER := ./bin/bitebuilder

.PHONY: setup bitebuilder up tui tui-solar workspace model stop-model smoke flask-smoke test go-test alias print-alias

setup:
	python3 -m venv .venv
	PIP_DISABLE_PIP_VERSION_CHECK=1 .venv/bin/python -m pip install -q -r requirements.txt

bitebuilder up: setup
	$(BITEBUILDER) up

tui: setup
	$(BITEBUILDER) tui $(ARGS)

tui-solar: setup
	$(BITEBUILDER) tui \
		--transcript "/Volumes/Two Jackson/001_Transcode/transcripts/CEO Interview.txt" \
		--xml "/Volumes/Two Jackson/001_Transcode/transcripts/CEO-intv.xml" \
		--transcript-b "/Volumes/Two Jackson/001_Transcode/transcripts/Technician Interview.txt" \
		--xml-b "/Volumes/Two Jackson/001_Transcode/transcripts/Technician Interview.xml" \
		--brief "5-7 minute sequence: innovation-forward opening, technical middle, insightful resolution"

workspace: setup
	.venv/bin/python webapp.py

model: setup
	$(BITEBUILDER) model

stop-model:
	$(BITEBUILDER) stop-model

smoke: setup
	$(BITEBUILDER) smoke

flask-smoke: setup
	$(BITEBUILDER) flask-smoke

test: setup
	$(BITEBUILDER) test

go-test:
	cd go-tui && go test ./...

alias print-alias:
	@printf "alias bitebuilder='%s/bin/bitebuilder'\n" "$$(pwd)"
	@printf "# Add that line to ~/.zshrc, or run it in your current shell for this session.\n"
