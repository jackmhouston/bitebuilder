# Claude Auth Local Quickstart

This is the fastest way to use Claude locally with BiteBuilder without configuring Anthropic API keys in the app itself.

Important scope note:

- This covers local Claude Code usage for both repo work and the BiteBuilder localhost UI.
- Ollama support still remains available.
- BiteBuilder does not send a raw Claude subscription token directly to the Anthropic API.
- The Claude option in BiteBuilder shells out to the local Claude Code CLI.

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

You can also create a long-lived Claude Code token locally:

```bash
claude setup-token
```

That command is available in the local Claude CLI help and requires a Claude subscription.

## 3. Use It in BiteBuilder

Launch the local UI:

```bash
bitebuilder-gui
```

Then in the browser UI:

1. Choose `Claude Code` as the provider.
2. Set the model to something like `sonnet` or `opus`.
3. Leave the auth token blank to use your current Claude login session.
4. Or paste a token into the `Claude Auth Token` field to override the local session for that run.

CLI example:

```bash
bitebuilder generate \
  --transcript /path/to/transcript.txt \
  --premiere-xml /path/to/source.xml \
  --brief "Find the most self-contained emotional beats." \
  --provider claude-code \
  --model sonnet \
  --claude-command claude \
  --output /path/to/bitebuilder_selects.xml
```

CLI with token override:

```bash
bitebuilder generate \
  --transcript /path/to/transcript.txt \
  --premiere-xml /path/to/source.xml \
  --brief "Find the strongest short-form sequence." \
  --provider claude-code \
  --model sonnet \
  --claude-auth-token "$ANTHROPIC_AUTH_TOKEN" \
  --output /path/to/bitebuilder_selects.xml
```

## 4. Use Claude For Repo Work Too

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

## 5. Keep The Auth Distinction Clear

There are two separate things here:

- Claude Code auth/login or token: used by the local Claude CLI
- Anthropic API key: required for direct Anthropic API calls
- Ollama: separate local inference backend with no Claude dependency

Official Anthropic API examples use the `x-api-key` header. BiteBuilder's Claude provider does not pretend a Claude Code login is the same thing as an Anthropic API key. It calls the local `claude` CLI instead.

## Source

Official Claude Code quickstart:

- https://code.claude.com/docs/en/quickstart

Official Claude Code headless / SDK docs:

- https://docs.anthropic.com/fr/docs/claude-code/sdk

Anthropic Messages API examples:

- https://docs.anthropic.com/en/api/messages-examples
