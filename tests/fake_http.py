"""A stand-in for urllib.request.urlopen, so tests never touch the network or need an API key."""

import io
import json


def as_bytes(body):
    return body if isinstance(body, bytes) else json.dumps(body).encode()


class FakeHTTP:
    """Records each request and replays one canned response body or raises one error."""

    def __init__(self, body=None, error=None):
        self.body = body
        self.error = error
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return io.BytesIO(as_bytes(self.body))

    def sent_payload(self):
        return json.loads(self.requests[-1][0].data)


def chat_reply(content):
    return {
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}
        ]
    }
