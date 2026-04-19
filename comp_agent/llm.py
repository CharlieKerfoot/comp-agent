"""LLM provider abstraction supporting both API and Claude Code CLI modes."""

from __future__ import annotations

import json
import subprocess


class LLMProvider:
    """Unified interface for calling Claude via API or Claude Code CLI."""

    def __init__(self, provider: str = "api", model: str = "claude-opus-4-7"):
        self.provider = provider
        self.model = model

        if provider == "api":
            import anthropic
            self.client = anthropic.Anthropic()
        elif provider == "claude-code":
            self.client = None
        else:
            raise ValueError(f"Unknown provider: {provider!r}. Use 'api' or 'claude-code'.")

    def ask(self, prompt: str, max_tokens: int = 4096) -> str:
        """Send a prompt and return the text response."""
        if self.provider == "api":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        else:
            return self._call_claude_code(prompt, max_tokens)

    def _call_claude_code(self, prompt: str, max_tokens: int) -> str:
        """Call the Claude Code CLI using --print for non-interactive use.

        The prompt is piped on stdin so long prompts don't blow through argv
        limits or trigger shell quoting issues.
        """
        cmd = ["claude", "--print", "--output-format", "text"]
        if self.model:
            cmd.extend(["--model", self.model])

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "The 'claude' CLI is not installed or not on PATH.\n"
                "Install Claude Code (https://docs.claude.com/en/docs/claude-code) "
                "or switch providers with `--provider api` / COMPETE_PROVIDER=api."
            ) from e

        if result.returncode != 0:
            detail = (result.stderr or "").strip() or (result.stdout or "").strip() or "(no output)"
            raise RuntimeError(
                f"Claude Code CLI failed (exit {result.returncode}).\n"
                f"Command: {' '.join(cmd)}\n"
                f"Output:\n{detail}"
            )

        return result.stdout.strip()


# Module-level default instance, configured via set_default_provider()
_default_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Get the default LLM provider, creating one if needed."""
    global _default_provider
    if _default_provider is None:
        _default_provider = LLMProvider()
    return _default_provider


def set_default_provider(provider: str = "api", model: str = "claude-opus-4-7") -> None:
    """Configure the default LLM provider used by all modules."""
    global _default_provider
    _default_provider = LLMProvider(provider=provider, model=model)
