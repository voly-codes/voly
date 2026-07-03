"""ContextAnalyzer — анализ, сжатие и оценка стоимости контекста."""

import math

MODEL_RATES: dict[str, float] = {
    "claude-sonnet-4-6": 0.003,
    "claude-opus-4-8": 0.015,
    "gpt-4o": 0.0025,
}

DEFAULT_RATE = 0.001
CHARS_PER_TOKEN = 4
WARN_TOKEN_LIMIT = 100_000


class ContextAnalyzer:
    """Анализирует текстовый контекст: токены, сжатие, стоимость."""

    def analyze(self, text: str) -> dict:
        """Возвращает статистику: tokens, chars, lines, warning."""
        chars = len(text)
        tokens = math.ceil(chars / CHARS_PER_TOKEN)
        lines = text.count("\n") + (1 if text else 0)
        result: dict = {
            "tokens": tokens,
            "chars": chars,
            "lines": lines,
        }
        if tokens > WARN_TOKEN_LIMIT:
            result["warning"] = (
                f"Context too large: ~{tokens} tokens "
                f"(exceeds {WARN_TOKEN_LIMIT} limit)"
            )
        return result

    def compress(self, text: str, target_tokens: int) -> str:
        """Обрезает текст до target_tokens: первые 60% + последние 40%."""
        target_chars = target_tokens * CHARS_PER_TOKEN
        if len(text) <= target_chars:
            return text

        head_ratio = 0.6
        head_chars = int(target_chars * head_ratio)
        tail_chars = target_chars - head_chars

        head = text[:head_chars]
        tail = text[-tail_chars:] if tail_chars > 0 else ""

        lines_skipped = text[head_chars:-tail_chars or len(text)].count("\n")
        marker = f"\n[...{lines_skipped} lines skipped...]\n"

        return head + marker + tail

    @staticmethod
    def estimate_cost(tokens: int, model: str = "default") -> float:
        """Стоимость в USD для модели."""
        rate = MODEL_RATES.get(model, DEFAULT_RATE)
        return round(tokens / 1000 * rate, 6)
