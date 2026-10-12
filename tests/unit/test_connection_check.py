"""Tests for the config-flow LLM connection check (llm_provider.test_connection, v6.92.0)."""
import pytest


@pytest.fixture
def lp(load):
    return load("llm_provider")


class _OkClient:
    def chat(self, messages, tools=None, max_tokens=512, **k):
        return {"content": "pong"}


class _RaiseClient:
    def __init__(self, exc):
        self._exc = exc

    def chat(self, *a, **k):
        raise self._exc


# ── error classification ─────────────────────────────────────────────────────

def test_classify_auth(lp):
    assert lp._classify_conn_error(Exception("401 Unauthorized: invalid api key")) == "invalid_auth"
    assert lp._classify_conn_error(Exception("Authentication failed")) == "invalid_auth"


def test_classify_connect(lp):
    assert lp._classify_conn_error(Exception("Connection refused")) == "cannot_connect"
    assert lp._classify_conn_error(Exception("Cannot connect to host: timed out")) == "cannot_connect"
    assert lp._classify_conn_error(OSError("getaddrinfo failed")) == "cannot_connect"


def test_classify_unknown(lp):
    assert lp._classify_conn_error(Exception("something entirely unexpected")) == "unknown"


# ── test_connection ──────────────────────────────────────────────────────────

async def test_connection_success(lp, fake_hass, monkeypatch):
    monkeypatch.setattr(lp, "create_provider", lambda p, k, m, b=None: _OkClient())
    assert await lp.test_connection(fake_hass, "ollama", "", "gemma4:26b",
                                    "http://x:11434/v1") is None


async def test_connection_no_client(lp, fake_hass, monkeypatch):
    monkeypatch.setattr(lp, "create_provider", lambda p, k, m, b=None: None)
    assert await lp.test_connection(fake_hass, "ollama", "", "m", "http://x") == "cannot_connect"


async def test_connection_auth_error(lp, fake_hass, monkeypatch):
    monkeypatch.setattr(lp, "create_provider",
                        lambda p, k, m, b=None: _RaiseClient(Exception("401 invalid api key")))
    assert await lp.test_connection(fake_hass, "groq", "bad", "m", None) == "invalid_auth"


async def test_connection_conn_error(lp, fake_hass, monkeypatch):
    monkeypatch.setattr(lp, "create_provider",
                        lambda p, k, m, b=None: _RaiseClient(OSError("Connection refused")))
    assert await lp.test_connection(fake_hass, "ollama", "", "m",
                                    "http://down:11434") == "cannot_connect"


async def test_connection_build_failure(lp, fake_hass, monkeypatch):
    def _boom(*a, **k):
        raise Exception("could not connect to endpoint")
    monkeypatch.setattr(lp, "create_provider", _boom)
    assert await lp.test_connection(fake_hass, "ollama", "", "m", "http://x") == "cannot_connect"


# ── model-not-found: a valid key probed with a placeholder model must not
# be mistaken for a bad key/endpoint (regression: OpenAI/Anthropic/Gemini all
# failed setup because the config-flow probe uses a Groq-style model id) ────

def test_classify_model_not_found_is_not_auth_or_connect(lp):
    # these must NOT be misrouted to invalid_auth/cannot_connect by the
    # generic classifier — test_connection intercepts them before that
    assert lp._is_model_not_found(Exception("The model `openai/gpt-oss-120b` does not exist"))
    assert lp._is_model_not_found(Exception("404 model_not_found: no such model"))
    assert lp._is_model_not_found(Exception("models/gpt-oss-120b is not found for API version"))
    assert not lp._is_model_not_found(Exception("401 Unauthorized: invalid api key"))
    assert not lp._is_model_not_found(Exception("Connection refused"))


async def test_connection_succeeds_when_probe_model_is_unknown_to_provider(lp, fake_hass, monkeypatch):
    monkeypatch.setattr(lp, "create_provider",
                        lambda p, k, m, b=None: _RaiseClient(
                            Exception("The model `openai/gpt-oss-120b` does not exist")))
    # a real key against the wrong provider's model proves the key/endpoint work
    assert await lp.test_connection(fake_hass, "openai", "sk-real", "openai/gpt-oss-120b", None) is None


async def test_connection_still_fails_on_real_auth_error_with_model_in_message(lp, fake_hass, monkeypatch):
    monkeypatch.setattr(lp, "create_provider",
                        lambda p, k, m, b=None: _RaiseClient(
                            Exception("401 Unauthorized: invalid api key for model access")))
    assert await lp.test_connection(fake_hass, "openai", "bad", "m", None) == "invalid_auth"


# ── Ollama is validated for reachability, not for a specific model (issue #383)
# A self-hosted server almost never has the placeholder cloud model id pulled, so
# a "model not found" from a REACHABLE server must count as success, and the
# primary probe lists models instead of pinging a model that can't exist. ──────

class _OllamaLikeClient:
    """Mimics the Ollama provider: an openai-style ``._client.models.list()`` for
    the reachability probe, and a ``chat()`` that 404s on the placeholder model
    exactly as a real server without that model pulled would."""

    def __init__(self, list_ok=True):
        list_ok_flag = list_ok

        class _Models:
            def list(self_inner):
                if not list_ok_flag:
                    raise OSError("Connection refused")
                return {"data": []}   # reachable, even with no models pulled

        class _Inner:
            models = _Models()

        self._client = _Inner()
        self.chat_called = False

    def chat(self, *a, **k):
        self.chat_called = True
        raise Exception('404 model "openai/gpt-oss-120b" not found, try pulling it first')


async def test_connection_ollama_reachable_via_model_list(lp, fake_hass, monkeypatch):
    # A reachable server whose models.list() answers validates — without ever
    # pinging a chat model that may not be pulled.
    client = _OllamaLikeClient(list_ok=True)
    monkeypatch.setattr(lp, "create_provider", lambda p, k, m, b=None: client)
    assert await lp.test_connection(fake_hass, "ollama", "", "openai/gpt-oss-120b",
                                    "http://x:11434/v1") is None
    assert client.chat_called is False   # reachability probe, not a generation


async def test_connection_ollama_unreachable_still_fails(lp, fake_hass, monkeypatch):
    # A genuinely unreachable server still fails fast with cannot_connect.
    monkeypatch.setattr(lp, "create_provider",
                        lambda p, k, m, b=None: _OllamaLikeClient(list_ok=False))
    assert await lp.test_connection(fake_hass, "ollama", "", "m",
                                    "http://down:11434/v1") == "cannot_connect"


async def test_connection_ollama_model_not_found_counts_as_reachable(lp, fake_hass, monkeypatch):
    # Backstop: if the chat fallback runs (no model-list accessor), a reachable
    # server reporting "model not found" is a success, not a failure. This is the
    # exact case that blocked Ollama setup before issue #383.
    monkeypatch.setattr(lp, "create_provider",
                        lambda p, k, m, b=None: _RaiseClient(
                            Exception("404 model_not_found: no such model")))
    assert await lp.test_connection(fake_hass, "ollama", "", "m", "http://x") is None


async def test_connection_provider_is_case_insensitive(lp, fake_hass, monkeypatch):
    # A capitalised provider name must still take the Ollama reachability path
    # (list models), not fall through to a chat ping.
    client = _OllamaLikeClient(list_ok=True)
    monkeypatch.setattr(lp, "create_provider", lambda p, k, m, b=None: client)
    assert await lp.test_connection(fake_hass, "Ollama", "", "m", "http://x:11434") is None
    assert client.chat_called is False


# ── Ollama base-URL normalization: the OpenAI-compatible API lives under /v1 ─────
# A bare host:port, or a reverse-proxy origin with no path, must gain /v1; a URL
# that already carries a path (…/v1 or a custom proxy subpath) is left alone.
def test_ollama_normalize_url_appends_v1_when_pathless(lp):
    n = lp.OllamaProvider._normalize_url
    # bare host:port and trailing-slash forms -> /v1
    assert n("http://10.0.5.9:11434") == "http://10.0.5.9:11434/v1"
    assert n("http://10.0.5.9:11434/") == "http://10.0.5.9:11434/v1"
    # reverse proxy on a non-11434 port / no port, no path -> /v1 (the gap #383 left)
    assert n("https://ollama.example.com") == "https://ollama.example.com/v1"
    assert n("http://ip:8080") == "http://ip:8080/v1"


def test_ollama_normalize_url_leaves_explicit_paths_untouched(lp):
    n = lp.OllamaProvider._normalize_url
    assert n("http://10.0.5.9:11434/v1") == "http://10.0.5.9:11434/v1"       # already /v1
    assert n("https://host.tld/ollama") == "https://host.tld/ollama"         # custom subpath
    assert n("") == "" and n(None) is None                                    # empty/None pass through
