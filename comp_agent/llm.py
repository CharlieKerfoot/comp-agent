"""LLM provider abstraction supporting both API and Claude Code CLI modes."""

from __future__ import annotations

import json
import subprocess


class LLMProvider:
    """Unified interface for calling Claude via API or Claude Code CLI."""

    def __init__(self, provider: str = "api", model: str = "claude-sonnet-4-20250514"):
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
        """Call the Claude Code CLI using --print for non-interactive use."""
        cmd = [
            "claude",
            "--print",
            "--output-format", "text",
            "--max-turns", "1",
            prompt,
        ]
        if self.model:
            cmd.insert(1, "--model")
            cmd.insert(2, self.model)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Claude Code CLI failed (exit {result.returncode}): {result.stderr.strip()}"
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


def set_default_provider(provider: str = "api", model: str = "claude-sonnet-4-20250514") -> None:
    """Configure the default LLM provider used by all modules."""
    global _default_provider
    _default_provider = LLMProvider(provider=provider, model=model)
