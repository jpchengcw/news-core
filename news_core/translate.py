"""Translation + analyst gloss.

Hybrid by default:
- DeepL handles verbatim translation (deterministic, copyright-defensible, cheap)
- Claude handles the one-line analyst gloss (analytical judgement)

Pure-Claude mode is supported as a fallback when DEEPL_API_KEY is absent.

Copyright cap: translate at most the headline + 4 sentences from the body.
Always preserve the original-language title and source URL in NewsItem.

NOTE: actual API calls are wired in the next iteration. This module ships
the stable interface and a no-op stub so the rest of the pipeline can be
end-to-end tested without burning API tokens.
"""
from __future__ import annotations

import os
from typing import Protocol

# Hard cap on translated body sentences. Goes to NewsItem.summary_translated.
MAX_TRANSLATED_SENTENCES: int = 4


class Translator(Protocol):
    """Translation interface."""

    def translate(self, text: str, src: str, tgt: str = "en") -> str:
        """Verbatim translation. No editorialising."""
        ...

    def gloss(self, *, title: str, summary: str, ticker: str, context: dict | None = None) -> str:
        """One-line analyst gloss. Format: 'Read-through: ...' or 'Implication: ...'"""
        ...


# ---------------------------------------------------------------------------
# Stub — used by tests and as a safe default when no API keys are configured.
# ---------------------------------------------------------------------------
class StubTranslator:
    """Identity translator with empty glosses. Lets pipeline run without API keys."""

    def translate(self, text: str, src: str, tgt: str = "en") -> str:
        return text

    def gloss(self, *, title: str, summary: str, ticker: str, context: dict | None = None) -> str:
        return ""


# ---------------------------------------------------------------------------
# DeepL (deterministic verbatim translation)
# ---------------------------------------------------------------------------
class DeepLTranslator:
    """DeepL-backed translation; gloss falls back to stub (use HybridTranslator for gloss)."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("DEEPL_API_KEY")
        if not self.api_key:
            raise RuntimeError("DEEPL_API_KEY not set")
        self._client = None  # lazy import in _client_or_init()

    def _client_or_init(self):
        if self._client is None:
            try:
                import deepl  # type: ignore
            except ImportError as e:
                raise RuntimeError(
                    "deepl package not installed. Add `news-core[deepl]` to dependencies."
                ) from e
            self._client = deepl.Translator(self.api_key)
        return self._client

    @staticmethod
    def _deepl_lang(code: str) -> str:
        """Map our locale codes to DeepL language codes."""
        return {
            "ja": "JA",
            "ko": "KO",
            "zh-CN": "ZH",
            "zh-HK": "ZH",
            "zh-TW": "ZH",
            "de": "DE",
            "fr": "FR",
            "en": "EN-US",
        }.get(code, code.upper())

    def translate(self, text: str, src: str, tgt: str = "en") -> str:
        if src == tgt or not text:
            return text
        client = self._client_or_init()
        result = client.translate_text(
            text,
            source_lang=self._deepl_lang(src),
            target_lang=self._deepl_lang(tgt),
        )
        return result.text if hasattr(result, "text") else str(result)

    def gloss(self, *, title: str, summary: str, ticker: str, context: dict | None = None) -> str:
        return ""  # DeepL doesn't gloss; HybridTranslator handles this.


# ---------------------------------------------------------------------------
# Claude (analytical gloss + fallback translation)
# ---------------------------------------------------------------------------
class ClaudeTranslator:
    """Claude-backed translation + gloss. Single SDK; higher quality, higher cost."""

    GLOSS_SYSTEM_PROMPT = (
        "You are an institutional equity-research analyst. Given a news headline and "
        "summary, write ONE sentence of analytical read-through for a buy-side PM "
        "tracking the named ticker.\n"
        "FORMAT: a single sentence beginning with 'Read-through:' or 'Implication:'.\n"
        "RULES:\n"
        "- No hedging filler ('could potentially', 'may be considered').\n"
        "- No restating the headline.\n"
        "- No invented numbers, market shares, or competitive dynamics.\n"
        "- No meta-commentary ('I cannot', 'the summary lacks', 'please resubmit').\n"
        "- If the item has no material read-through for the named ticker, "
        "or if the summary is too sparse to support one, output the empty string. "
        "Do not explain why — just output empty.\n"
        "Output the sentence only, or nothing."
    )

    TRANSLATE_SYSTEM_PROMPT = (
        "Translate the following text to English. Preserve names, numbers, and proper nouns "
        "verbatim. Do not editorialise, summarise, or omit. Output the translation only."
    )

    def __init__(self, api_key: str | None = None, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self.model = model
        self._client = None

    def _client_or_init(self):
        if self._client is None:
            try:
                import anthropic  # type: ignore
            except ImportError as e:
                raise RuntimeError("anthropic SDK not installed") from e
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def translate(self, text: str, src: str, tgt: str = "en") -> str:
        if src == tgt or not text:
            return text
        client = self._client_or_init()
        msg = client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=self.TRANSLATE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"[{src} → {tgt}]\n{text}"}],
        )
        return msg.content[0].text.strip()

    def gloss(self, *, title: str, summary: str, ticker: str, context: dict | None = None) -> str:
        client = self._client_or_init()
        company = (context or {}).get("company", "")
        header = f"Ticker: {ticker}"
        if company:
            header += f"\nCompany: {company}"
        extras = ""
        if context:
            other = {k: v for k, v in context.items() if k != "company"}
            if other:
                extras = "\n\nContext:\n" + "\n".join(f"{k}: {v}" for k, v in other.items())
        user = f"{header}\nHeadline: {title}\nSummary: {summary}{extras}"
        msg = client.messages.create(
            model=self.model,
            max_tokens=200,
            system=self.GLOSS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip()


# ---------------------------------------------------------------------------
# Hybrid (recommended default)
# ---------------------------------------------------------------------------
class HybridTranslator:
    """DeepL for translation, Claude for gloss. Falls back gracefully."""

    def __init__(
        self,
        translator: Translator | None = None,
        glosser: Translator | None = None,
    ):
        self.translator = translator
        self.glosser = glosser

    @classmethod
    def from_env(cls) -> "HybridTranslator":
        translator: Translator
        glosser: Translator
        try:
            translator = DeepLTranslator()
        except RuntimeError:
            try:
                translator = ClaudeTranslator()
            except RuntimeError:
                translator = StubTranslator()
        try:
            glosser = ClaudeTranslator()
        except RuntimeError:
            glosser = StubTranslator()
        return cls(translator=translator, glosser=glosser)

    def translate(self, text: str, src: str, tgt: str = "en") -> str:
        return self.translator.translate(text, src, tgt) if self.translator else text

    def gloss(self, *, title: str, summary: str, ticker: str, context: dict | None = None) -> str:
        return self.glosser.gloss(title=title, summary=summary, ticker=ticker, context=context) if self.glosser else ""


def truncate_to_sentences(text: str, max_sentences: int = MAX_TRANSLATED_SENTENCES) -> str:
    """Hard copyright cap. Splits on . ! ? 。 ! ? — covers EN/CJK/EU punctuation."""
    if not text:
        return text
    import re as _re
    parts = _re.split(r"(?<=[\.\!\?。\!\?])\s+", text.strip())
    return " ".join(parts[:max_sentences]).strip()
