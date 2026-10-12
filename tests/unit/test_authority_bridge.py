"""Tests for the log-only authority↔gate parity bridge (kernel hardening H1)."""
import pytest

from fakes import FakeHass


@pytest.fixture
def ab(load):
    return load("authority_bridge")


def test_agreement_recorded_for_safe_allowed(ab):
    hass = FakeHass()
    # A safe action the gate allowed → engine ALLOW → agreement.
    d = ab.record_control_parity(hass, "light", "turn_on", allowed=True)
    assert d is not None and d.decision == "allow"
    summary = ab.parity_summary(hass)
    assert summary["agree"] == 1 and summary["disagree"] == 0


def test_mismatch_recorded_for_security_allowed(ab):
    hass = FakeHass()
    # The gate let an unlock through (allowed=True) but the engine would CONFIRM
    # (security-sensitive, no identity) → mismatch, logged not enforced.
    ab.record_control_parity(hass, "lock", "unlock", allowed=True)
    s = ab.parity_summary(hass)
    assert s["disagree"] == 1
    assert s["recent_mismatches"][0]["capability"] == "lock.unlock"


def test_gate_hold_matches_engine_confirm(ab):
    hass = FakeHass()
    # Gate held the action (allowed=False → actual CONFIRM); engine also CONFIRM.
    ab.record_control_parity(hass, "lock", "unlock", allowed=False, identity="Sam")
    s = ab.parity_summary(hass)
    assert s["agree"] == 1 and s["disagree"] == 0


def test_tally_accumulates_across_calls(ab):
    hass = FakeHass()
    ab.record_control_parity(hass, "light", "turn_on", allowed=True)
    ab.record_control_parity(hass, "switch", "toggle", allowed=True)
    s = ab.parity_summary(hass)
    assert s["agree"] == 2 and 0.0 <= s["agreement_rate"] <= 1.0


def test_summary_empty_when_nothing_recorded(ab):
    assert ab.parity_summary(FakeHass()) in ({}, {"agree": 0, "disagree": 0,
                                                 "agreement_rate": 1.0,
                                                 "by_capability": {},
                                                 "recent_mismatches": []})


def test_record_accepts_richer_inputs_and_stays_log_only(ab):
    # MCU A4: the bridge threads situation/scope/intent/token/context into the
    # engine request. Still log-only — recording never raises and the gate's
    # outcome is untouched.
    hass = FakeHass()
    d = ab.record_control_parity(
        hass, "light", "turn_on", allowed=True,
        intent="turn on", scope="light.kitchen",
        situation="normal", context={"room": "kitchen"})
    assert d is not None and d.decision == "allow"
    assert ab.parity_summary(hass)["agree"] == 1


def test_token_input_affects_engine_decision(ab, load):
    # Proof the token is actually fed into the decision (A4): a capability token
    # that does NOT grant this action makes the engine DENY (delegation can't
    # escalate) — even though the live gate let it through (allowed=True).
    auth = load("kernel.authority")
    tok = auth.CapabilityToken(holder="friday", capabilities=frozenset({"climate"}))
    hass = FakeHass()
    d = ab.record_control_parity(
        hass, "light", "turn_on", allowed=True, token=tok)
    assert d is not None and d.decision == auth.DENY
    # Still log-only: the mismatch is recorded, nothing is blocked.
    assert ab.parity_summary(hass)["disagree"] == 1


# ── persistence across restarts (Step A.5) ───────────────────────────────────

def test_authority_parity_to_from_dict(load):
    A = load("kernel.authority")
    # garbage in → empty-but-usable, never raises
    p = A.AuthorityParity.from_dict(
        {"agree": "x", "disagree": None, "by_capability": "nope",
         "recent_mismatches": 5})
    assert p.agree == 0 and p.disagree == 0
    assert p.by_capability == {} and p.recent_mismatches == []
    # a well-formed snapshot round-trips; agreement_rate is derived, not stored
    good = {"agree": 3, "disagree": 1,
            "by_capability": {"light.turn_on": [3, 1]},
            "recent_mismatches": [{"capability": "lock.unlock"}]}
    q = A.AuthorityParity.from_dict(good)
    assert q.agree == 3 and q.disagree == 1
    assert q.by_capability == {"light.turn_on": [3, 1]}
    d = q.to_dict()
    assert d["by_capability"] == {"light.turn_on": [3, 1]}
    assert "agreement_rate" not in d


def test_parity_persists_across_a_restart(ab, tmp_path, monkeypatch):
    path = str(tmp_path / "authority_parity.json")
    monkeypatch.setattr(ab, "_parity_path", lambda hass: path)

    hass = FakeHass()
    ab.record_control_parity(hass, "light", "turn_on", allowed=True)
    ab.record_control_parity(hass, "lock", "unlock", allowed=True)
    s1 = ab.parity_summary(hass)
    assert (s1["agree"] + s1["disagree"]) == 2
    assert ab.save_parity(hass) is True

    # a fresh "restart": new hass has an empty in-memory tally until it loads.
    hass2 = FakeHass()
    assert ab.parity_summary(hass2).get("agree", 0) == 0
    assert ab.load_parity(hass2) is True
    s2 = ab.parity_summary(hass2)
    assert s2["agree"] == s1["agree"] and s2["disagree"] == s1["disagree"]
    assert s2["by_capability"] == s1["by_capability"]


def test_save_and_load_are_best_effort(ab, tmp_path, monkeypatch):
    # nothing recorded → nothing to save; no file → nothing to load. Never raise.
    missing = str(tmp_path / "nope.json")
    monkeypatch.setattr(ab, "_parity_path", lambda hass: missing)
    assert ab.save_parity(FakeHass()) is False
    assert ab.load_parity(FakeHass()) is False
    # a corrupt file loads as "no restore", not a crash.
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    monkeypatch.setattr(ab, "_parity_path", lambda hass: str(bad))
    assert ab.load_parity(FakeHass()) is False
