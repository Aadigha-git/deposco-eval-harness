"""Minimal client for the Gemini API's OpenAI-compatible Chat Completions endpoint."""

import http.client
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_ASSISTANT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_JUDGE_MODEL = "gemini-3.8-flash"
TIMEOUT_SECONDS = 120

Complete = Callable[[str, str, str], str]
"""complete(system, user, model) -> reply text"""


class LLMError(RuntimeError):
    """The LLM could not be configured or called; the message never contains the API key."""


@dataclass(frozen=True)
class LLMConfig:
    api_key: str = field(repr=False)
    base_url: str
    assistant_model: str
    judge_model: str


def config_from_env(environ: Mapping[str, str] = os.environ) -> LLMConfig:
    api_key = environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise LLMError("GEMINI_API_KEY is not set; export it before running the assistant")
    return LLMConfig(
        api_key=api_key,
        base_url=environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL,
        assistant_model=environ.get("ASSISTANT_MODEL") or DEFAULT_ASSISTANT_MODEL,
        judge_model=environ.get("JUDGE_MODEL") or DEFAULT_JUDGE_MODEL,
    )


def make_complete(config: LLMConfig, urlopen: Callable = urllib.request.urlopen) -> Complete:
    url = config.base_url.rstrip("/") + "/chat/completions"

    def complete(system: str, user: str, model: str) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = _api_error_message(error.read())
            raise LLMError(_redact(f"Gemini API returned HTTP {error.code}: {detail}", config)) from None
        except urllib.error.URLError as error:
            raise LLMError(_redact(f"could not reach the Gemini API at {url}: {error.reason}", config)) from None
        except TimeoutError:
            raise LLMError(f"Gemini API timed out after {TIMEOUT_SECONDS}s") from None
        except (OSError, http.client.HTTPException) as error:
            raise LLMError(_redact(f"connection to the Gemini API failed: {error!r}", config)) from None
        return _reply_text(raw)

    return complete


def _api_error_message(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        body = json.loads(text)
        if isinstance(body, list):
            body = body[0]
        return body["error"]["message"]
    except (ValueError, LookupError, TypeError):
        return text[:500] or "no error details"


def _reply_text(raw: bytes) -> str:
    try:
        choice = json.loads(raw)["choices"][0]
        content = choice["message"]["content"]
    except (ValueError, LookupError, TypeError):
        raise LLMError("Gemini API returned no reply text (unexpected response shape)") from None
    if not isinstance(content, str) or not content.strip():
        finish_reason = choice.get("finish_reason", "unknown")
        raise LLMError(f"Gemini API returned no reply text (finish_reason: {finish_reason})")
    return content


def _redact(message: str, config: LLMConfig) -> str:
    return message.replace(config.api_key, "[redacted]")
