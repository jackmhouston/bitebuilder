# Claude Auth Local Quickstart

This is the fastest way to use Claude locally while working on BiteBuilder without configuring Anthropic API keys.

Important scope note:

- This is for your local development workflow in the repo.
- It does not change the BiteBuilder runtime backend.
- The current scaffold still calls Ollama for transcript selection and XML generation.

## 1. Install Claude Code

Use the official installer that matches your environment.

WSL / macOS / Linux:

```bash
curl -fsSL https://claude.ai/install.sh | bash
```

Windows PowerShell:

```powershell
irm https://claude.ai/install.ps1 | iex
```

Windows CMD:

```cmd
curl -fsSL https://claude.ai/install.cmd -o install.cmd && install.cmd && del install.cmd
```

## 2. Log In with Claude Account Auth

From the BiteBuilder repo:

```bash
cd /path/to/bitebuilder
claude
```

On first run, Claude Code will prompt you to log in. For local usage without API keys, choose your Claude account login flow rather than a Console/API-credit workflow.

If you already logged in a different way and want to switch:

```text
/login
```

The official docs note that supported account types include Claude Pro, Max, Teams, and Enterprise, along with Console and cloud-provider options. For the no-API-key path, use the Claude subscription account route.

## 3. Use It in This Repo

Typical local prompts:

```text
review the XMEML generator for Premiere import risks
```

```text
wire the GUI fields to a saved preset file
```

```text
compare the generated XML structure against docs/Premiere_XML_Generation_Technical_Reference.md
```

## 4. Keep the Runtime Distinction Clear

There are two separate things here:

- Claude Code auth: how you work on the repo locally
- Ollama model backend: how the current BiteBuilder scaffold performs transcript-selection inference

If you later want BiteBuilder itself to support Claude as a provider, add a separate provider adapter in code rather than replacing the documented local dev workflow.

## Source

Official Claude Code quickstart:

- https://code.claude.com/docs/en/quickstart
