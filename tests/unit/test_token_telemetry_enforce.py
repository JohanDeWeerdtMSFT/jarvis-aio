"""TC4 enforce — the status panel reads measured token telemetry.

There is no independent legacy cost estimate to run a TC3 agreement-parity
against (the panel showed a literal "—"), and a measured usage record *is* the
ground truth for a pure measurement primitive, so this advances shadow →
enforce directly. These tests cover the three moving parts:

  * the kernel's default (operator-overridable) price book — pure;
  * llm_provider's priced retention ring + the enforce kill-switch;
  * websocket's fail-safe ``est_cost`` helper (never regresses the panel).
"""
import pytest


# ── kernel: default price book (pure) ────────────────────────────────────────
@pytest.fixture
def tt(load):
    return load("kernel.token_telemetry")


def test_default_price_book_prices_known_families(tt):
    book = tt.default_price_book()
    # output billed higher than input; a known family costs > 0
    assert book.estimate_cost(
        "gpt-5-mini-2026", input_tokens=1_000_000, output_tokens=1_000_000
    ) == pytest.approx(0.25 + 2.0)
    # most-specific key wins (gpt-5-mini is listed before gpt-5)
    assert book.estimate_cost(
        "gpt-5-mini", input_tokens=1_000_000, output_tokens=0
    ) == pytest.approx(0.25)
    assert book.estimate_cost(
        "gpt-5", input_tokens=1_000_000, output_tokens=0
    ) == pytest.approx(1.25)
    # anthropic / gemini / groq families resolve by substring
    assert book.estimate_cost(
        "claude-sonnet-4-5", input_tokens=1_000_000, output_tokens=0
    ) == pytest.approx(3.0)
    assert book.estimate_cost(
        "gemini-2.5-flash", input_tokens=1_000_000, output_tokens=0
    ) == pytest.approx(0.10)
    assert book.estimate_cost(
        "llama-3.3-70b-versatile", input_tokens=1_000_000, output_tokens=0
    ) == pytest.approx(0.10)


def test_default_price_book_unknown_model_is_zero_not_error(tt):
    book = tt.default_price_book()
    assert book.estimate_cost(
        "nonesuch-model", input_tokens=1_000_000, output_tokens=1_000_000
    ) == 0.0


def test_default_price_book_is_fresh_each_call(tt):
    # pure: no shared mutable state handed out
    assert tt.default_price_book() is not tt.default_price_book()


# ── llm_provider: priced retention + enforce gate ────────────────────────────
class _Usage:
    def __init__(self, prompt_tokens=0, completion_tokens=0):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _Resp:
    def __init__(self, usage):
        self.usage = usage


@pytest.fixture
def llm(load):
    m = load("llm_provider")
    m._USAGE_RECORDS.clear()
    yield m
    m._USAGE_RECORDS.clear()


def test_record_usage_retains_priced_record(llm):
    llm._record_usage_shadow(_Resp(_Usage(1000, 500)), "openai", "gpt-5-mini")
    recs = llm.usage_records()
    assert len(recs) == 1
    r = recs[0]
    assert r.input_tokens == 1000
    assert r.output_tokens == 500
    assert r.estimated_cost_usd > 0  # priced via the default book


def test_record_usage_shadow_killswitch_skips(llm, monkeypatch):
    monkeypatch.setattr(llm, "TOKEN_TELEMETRY_SHADOW", False)
    llm._record_usage_shadow(_Resp(_Usage(1000, 500)), "openai", "gpt-5-mini")
    assert llm.usage_records() == ()


def test_record_usage_never_raises_on_bad_resp(llm):
    # no usage attribute at all → silently skipped, no record, no raise
    llm._record_usage_shadow(object(), "openai", "gpt-5-mini")
    assert llm.usage_records() == ()


def test_record_usage_ring_is_bounded(llm):
    assert llm._USAGE_RECORDS.maxlen and llm._USAGE_RECORDS.maxlen > 0


def test_enforce_enabled_default_on(llm):
    assert llm.telemetry_enforce_enabled() is True


def test_enforce_enabled_module_flag(llm, monkeypatch):
    monkeypatch.setattr(llm, "TOKEN_TELEMETRY_ENFORCE", False)
    assert llm.telemetry_enforce_enabled() is False


def test_enforce_enabled_config_key(llm, monkeypatch):
    import jc.jarvis_config as cfg
    monkeypatch.setattr(
        cfg, "get",
        lambda key, default=None: False if key == "token_telemetry_enforce" else default)
    assert llm.telemetry_enforce_enabled() is False


# ── llm_provider.telemetry_est_cost — the panel figure (fail-safe) ───────────
# (websocket's _telemetry_est_cost is a one-line delegate to this; the test
# harness pre-stubs jc.websocket, so the real logic is exercised here.)
def test_est_cost_placeholder_when_no_records(llm):
    assert llm.telemetry_est_cost() == "—"


def test_est_cost_reads_measured_cost(llm):
    llm._record_usage_shadow(_Resp(_Usage(100_000, 50_000)), "openai", "gpt-5-mini")
    out = llm.telemetry_est_cost()
    assert out.startswith("$")
    assert out != "—"
    # (100000*0.25 + 50000*2.0) / 1e6 = $0.1250
    assert out == "$0.1250"


def test_est_cost_placeholder_when_enforce_off(llm, monkeypatch):
    llm._record_usage_shadow(_Resp(_Usage(100_000, 50_000)), "openai", "gpt-5-mini")
    monkeypatch.setattr(llm, "TOKEN_TELEMETRY_ENFORCE", False)
    assert llm.telemetry_est_cost() == "—"


def test_est_cost_placeholder_when_only_unpriced(llm):
    # a recorded call whose model has no price → cost 0 → the panel keeps the
    # placeholder rather than implying a misleading "$0.0000" (free).
    llm._record_usage_shadow(_Resp(_Usage(100_000, 50_000)), "local", "nonesuch-model")
    assert llm.telemetry_est_cost() == "—"
