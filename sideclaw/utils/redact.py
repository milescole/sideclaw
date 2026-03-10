"""Regex-based secret redaction for log output."""

import re
import sys

from loguru import logger

# Known API key prefixes
_PREFIX_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{10,}",  # OpenAI / OpenRouter
]

_PREFIX_RE = re.compile(r"(?<![A-Za-z0-9_-])(" + "|".join(_PREFIX_PATTERNS) + r")(?![A-Za-z0-9_-])")

# ENV assignments: OPENROUTER_API_KEY=sk-abc...
_ENV_RE = re.compile(
    r"([A-Z_]*(?:API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH)[A-Z_]*)\s*=\s*(['\"]?)(\S+)\2",
    re.IGNORECASE,
)

# JSON fields: "apiKey": "value", "token": "value"
_JSON_RE = re.compile(
    r'("(?:api_?key|token|secret|password|access_token|auth_token|bearer)")\s*:\s*"([^"]+)"',
    re.IGNORECASE,
)

# Authorization headers
_AUTH_HEADER_RE = re.compile(
    r"(Authorization:\s*(?:Bearer|Token)\s+)(\S+)",
    re.IGNORECASE,
)

# Telegram bot tokens: [bot]<digits>:<alphanum>
_TELEGRAM_RE = re.compile(r"(bot)?(\d{8,}):([-A-Za-z0-9_]{30,})")


def _mask(token: str) -> str:
    """Mask a token. Short tokens are fully hidden; long ones keep a prefix."""
    if len(token) < 18:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


def redact(text: str) -> str:
    """Redact secrets from a string. Safe to call on any text."""
    if not text:
        return text

    text = _PREFIX_RE.sub(lambda m: _mask(m.group(1)), text)

    def _env(m: re.Match) -> str:
        name, quote, value = m.group(1), m.group(2), m.group(3)
        return f"{name}={quote}{_mask(value)}{quote}"

    text = _ENV_RE.sub(_env, text)

    text = _JSON_RE.sub(lambda m: f'{m.group(1)}: "{_mask(m.group(2))}"', text)

    text = _AUTH_HEADER_RE.sub(lambda m: m.group(1) + _mask(m.group(2)), text)

    return _TELEGRAM_RE.sub(lambda m: f"{m.group(1) or ''}{m.group(2)}:***", text)


def _redact_record(record: dict) -> bool:
    """Loguru filter that redacts secrets from log messages in place."""
    record["message"] = redact(record["message"])
    return True


def configure_logging() -> None:
    """Install a redacting loguru sink, replacing the default handler."""
    logger.remove()
    logger.add(sys.stderr, filter=_redact_record, colorize=True)
