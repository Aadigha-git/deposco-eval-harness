import http.client
import io
import json
import re
import urllib.error

import pytest
from fake_http import FakeHTTP, as_bytes, chat_reply

from deposco_evals.llm import LLMError, config_from_env, make_complete

KEY = "test-key-not-real"


def client(http, **environ):
    return make_complete(config_from_env({"GEMINI_API_KEY": KEY, **environ}), urlopen=http)


def test_complete_posts_a_chat_completion_and_returns_the_reply_text():
    http = FakeHTTP(chat_reply("There are 8 open orders.\nAnswer: 8"))

    reply = client(http)("system rules", "user question", "gemini-3.5-flash-lite")

    request, timeout = http.requests[0]
    assert reply == "There are 8 open orders.\nAnswer: 8"
    assert request.get_method() == "POST"
    assert request.full_url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    assert request.get_header("Content-type") == "application/json"
    assert json.loads(request.data) == {
        "model": "gemini-3.5-flash-lite",
        "messages": [
            {"role": "system", "content": "system rules"},
            {"role": "user", "content": "user question"},
        ],
        "temperature": 0,
    }
    assert timeout > 0


def http_error(code, body):
    return urllib.error.HTTPError("https://example.invalid", code, "Error", {}, io.BytesIO(as_bytes(body)))


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            http_error(400, [{"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT"}}]),
            "Gemini API returned HTTP 400: API key not valid.",
        ),
        (
            http_error(404, {"error": {"code": 404, "message": "models/gemini-x is not found", "status": "NOT_FOUND"}}),
            "Gemini API returned HTTP 404: models/gemini-x is not found",
        ),
        (http_error(503, b"<html>Service Unavailable</html>"), "Gemini API returned HTTP 503: <html>Service Unavailable</html>"),
        (urllib.error.URLError("nodename nor servname provided"), "could not reach the Gemini API"),
        (TimeoutError("timed out"), "Gemini API timed out"),
        (http.client.RemoteDisconnected("Remote end closed connection"), "connection to the Gemini API failed"),
        (ConnectionResetError("Connection reset by peer"), "connection to the Gemini API failed"),
        (http.client.IncompleteRead(b"partial"), "connection to the Gemini API failed"),
    ],
)
def test_complete_turns_transport_failures_into_clear_errors(error, message):
    with pytest.raises(LLMError, match=re.escape(message)):
        client(FakeHTTP(error=error))("s", "u", "m")


@pytest.mark.parametrize(
    "body",
    [b"not json", {"choices": []}, {"error": "nope"}, chat_reply(None), chat_reply("   ")],
)
def test_complete_rejects_a_response_without_reply_text(body):
    with pytest.raises(LLMError, match="Gemini API returned no reply text"):
        client(FakeHTTP(body))("s", "u", "m")


def test_errors_never_reveal_the_api_key():
    echoed = http_error(401, {"error": {"message": f"key {KEY} rejected"}})

    with pytest.raises(LLMError) as error:
        client(FakeHTTP(error=echoed))("s", "u", "m")

    assert KEY not in str(error.value)


def test_complete_joins_a_base_url_without_trailing_slash():
    http = FakeHTTP(chat_reply("ok"))

    client(http, LLM_BASE_URL="http://localhost:11434/v1")("s", "u", "m")

    assert http.requests[0][0].full_url == "http://localhost:11434/v1/chat/completions"


def test_config_defaults_to_gemini_endpoint_and_agreed_models():
    config = config_from_env({"GEMINI_API_KEY": KEY})

    assert (config.api_key, config.base_url, config.assistant_model, config.judge_model) == (
        KEY,
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3.5-flash-lite",
        "gemini-3.8-flash",
    )


def test_config_reads_overrides_from_the_environment():
    config = config_from_env({
        "GEMINI_API_KEY": KEY,
        "LLM_BASE_URL": "http://localhost:11434/v1",
        "ASSISTANT_MODEL": "small-model",
        "JUDGE_MODEL": "big-model",
    })

    assert (config.base_url, config.assistant_model, config.judge_model) == (
        "http://localhost:11434/v1", "small-model", "big-model",
    )


@pytest.mark.parametrize("environ", [{}, {"GEMINI_API_KEY": ""}, {"GEMINI_API_KEY": "   "}])
def test_config_requires_an_api_key(environ):
    with pytest.raises(LLMError, match="GEMINI_API_KEY is not set"):
        config_from_env(environ)


def test_config_never_shows_the_key():
    config = config_from_env({"GEMINI_API_KEY": KEY})

    assert KEY not in repr(config)
