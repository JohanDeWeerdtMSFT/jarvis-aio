"""Phase M→N — learned-trust autonomy damper (owner-gated, opt-in).

The closed learning loop (actuation.LEARNING_ENFORCE, 9.2.0) persists a
per-capability trust from real verified outcomes; this is its first consumer.
A granted convenience pattern whose capability has a PROVEN poor track record —
learned trust below a floor, over enough evidence — falls back to asking.
Downward-only (only ever withholds), owner-gated DEFAULT-OFF (behaviour-preserving;
shadow-logs always), kill-switched, fail-safe (any fault, or too little evidence,
→ act as today). Learning never overrides authority/safety: the damper runs after
the N ceiling and only returns False.
"""
import types

import pytest


# ── actuation.capability_reliability (the aggregation accessor) ───────────────
@pytest.fixture
def act(load):
    m = load("actuation")
    m._LEARN_STORE.clear()
    m._recent_outcomes.clear()
    yield m
    m._LEARN_STORE.clear()
    m._recent_outcomes.clear()


def _oc(cap):
    return types.SimpleNamespace(capability=cap)


def test_reliability_neutral_when_unseen(act):
    trust, samples = act.capability_reliability("light")
    assert trust == act._CAP_TRUST_PRIOR and samples == 0


def test_reliability_empty_class_is_neutral(act):
    assert act.capability_reliability("") == (act._CAP_TRUST_PRIOR, 0)


def test_reliability_takes_min_trust_and_counts_samples(act):
    # two fine capabilities in the "light" class; the damper uses the WORST.
    act._LEARN_STORE["light.turn_on"] = 0.80
    act._LEARN_STORE["light.turn_off"] = 0.20
    act._LEARN_STORE["lock.lock"] = 0.10          # different class, ignored
    for _ in range(3):
        act._recent_outcomes.append(_oc("light.turn_on"))
    act._recent_outcomes.append(_oc("lock.lock"))  # different class, not counted
    trust, samples = act.capability_reliability("light")
    assert trust == pytest.approx(0.20)            # min across the class
    assert samples == 3


def test_reliability_matches_exact_class_key(act):
    act._LEARN_STORE["light"] = 0.3
    act._recent_outcomes.append(_oc("light"))
    trust, samples = act.capability_reliability("light")
    assert trust == pytest.approx(0.3) and samples == 1


# ── the damper switch + decision (cognitive_core) ─────────────────────────────
@pytest.fixture
def cc(load):
    return load("cognitive_core")


@pytest.fixture
def cfg(load, monkeypatch):
    jc = load("jarvis_config")
    store = {}
    monkeypatch.setattr(jc, "get", lambda k, d=None: store.get(k, d))
    return store


@pytest.fixture
def modes_auto_on(load, monkeypatch):
    modes = load("modes")
    monkeypatch.setattr(modes, "mode_allows_auto_actions", lambda: True)
    return modes


def _reliability(cc, monkeypatch, trust, samples):
    from jc import actuation
    monkeypatch.setattr(actuation, "capability_reliability",
                        lambda cls: (trust, samples))


def _granted(am, key):
    am._grants[key] = {"granted": True, "approvals": 5}


def test_damper_off_by_default(cc):
    assert cc._autonomy_trust_damper_on() is False


def test_damper_on_via_config(cc, cfg):
    cfg["autonomy_trust_damper"] = True
    assert cc._autonomy_trust_damper_on() is True


def test_damper_on_via_flag(cc, monkeypatch):
    monkeypatch.setattr(cc, "AUTONOMY_TRUST_DAMPER", True)
    assert cc._autonomy_trust_damper_on() is True


def test_decision_unknown_pattern_has_no_capability(cc):
    damp, reason = cc._trust_damp_decision("totally_unknown_pattern:x")
    assert damp is False and reason == ""


def test_decision_insufficient_evidence_never_damps(cc, monkeypatch):
    _reliability(cc, monkeypatch, 0.05, cc.AUTONOMY_TRUST_MIN_SAMPLES - 1)
    damp, reason = cc._trust_damp_decision("lights_on_when_dark:den")
    assert damp is False and "evidence" in reason


def test_decision_low_trust_with_evidence_damps(cc, monkeypatch):
    _reliability(cc, monkeypatch, 0.20, cc.AUTONOMY_TRUST_MIN_SAMPLES + 3)
    damp, reason = cc._trust_damp_decision("lights_on_when_dark:den")
    assert damp is True and "DAMP" in reason


def test_decision_good_trust_does_not_damp(cc, monkeypatch):
    _reliability(cc, monkeypatch, 0.90, cc.AUTONOMY_TRUST_MIN_SAMPLES + 3)
    damp, reason = cc._trust_damp_decision("lights_on_when_dark:den")
    assert damp is False and "ok" in reason


# ── the live gate ────────────────────────────────────────────────────────────
def test_low_trust_holds_convenience_only_under_damper(cc, cfg, modes_auto_on, monkeypatch):
    _reliability(cc, monkeypatch, 0.20, 10)        # proven unreliable
    am = cc.AutonomyManager()
    _granted(am, "lights_on_when_dark:den")
    # Default OFF: behaviour-preserving — still autonomous.
    assert am.is_autonomous("lights_on_when_dark:den") is True
    # Opt-in ON: a proven-poor capability is held to ask-first.
    cfg["autonomy_trust_damper"] = True
    assert am.is_autonomous("lights_on_when_dark:den") is False


def test_good_trust_stays_autonomous_under_damper(cc, cfg, modes_auto_on, monkeypatch):
    _reliability(cc, monkeypatch, 0.90, 10)
    am = cc.AutonomyManager()
    _granted(am, "lights_on_when_dark:den")
    cfg["autonomy_trust_damper"] = True
    assert am.is_autonomous("lights_on_when_dark:den") is True


def test_insufficient_evidence_stays_autonomous_under_damper(cc, cfg, modes_auto_on, monkeypatch):
    _reliability(cc, monkeypatch, 0.05, 1)         # low but barely seen
    am = cc.AutonomyManager()
    _granted(am, "lights_on_when_dark:den")
    cfg["autonomy_trust_damper"] = True
    assert am.is_autonomous("lights_on_when_dark:den") is True


def test_damper_is_failsafe_on_error(cc, cfg, modes_auto_on, monkeypatch):
    from jc import actuation
    def _boom(cls):
        raise RuntimeError("learning store down")
    monkeypatch.setattr(actuation, "capability_reliability", _boom)
    am = cc.AutonomyManager()
    _granted(am, "lights_on_when_dark:den")
    cfg["autonomy_trust_damper"] = True
    # Any fault in the damper → act as today (never block on it).
    assert am.is_autonomous("lights_on_when_dark:den") is True


def test_damper_never_grants_to_ungranted(cc, cfg, modes_auto_on, monkeypatch):
    _reliability(cc, monkeypatch, 0.95, 50)        # great trust
    am = cc.AutonomyManager()                      # no grant
    cfg["autonomy_trust_damper"] = True
    # Downward-only: high trust can never promote an ungranted pattern.
    assert am.is_autonomous("lights_on_when_dark:den") is False
