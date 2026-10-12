"""Authority / capability engine (kernel Phase 4, docs/KERNEL_PLAN.md).

The safety keystone: one place that answers "may this capability be exercised,
by this actor, in this context?" with **allow / deny / confirm**. Today that
judgement is spread across `voice_confirm` (is this action protected?),
`output_gate` (may we interrupt?) and the autonomy grants; this module gives them
a single, testable check to delegate to, and a capability-**token** model so a
delegated sub-agent (FRIDAY / HOMER) can never exercise more than it was granted.

Design invariants (from the kernel plan):
  * **No escalation by delegation.** A token-bearing actor is denied any
    capability its token does not grant, and a derived token can only *narrow*
    its parent's capabilities, never widen them.
  * **Security-sensitive capabilities require explicit authority** — they resolve
    to CONFIRM (or DENY without an identified requester), never a silent allow.
  * **Fail closed.** Any error in a policy resolves to DENY.

Pure: no Home Assistant import, no I/O — trivially testable. **Phase 4 ships this
additively, to run log-only / allow-as-before first**: callers compute the
engine's decision alongside their existing behaviour and record parity before any
actuator is actually routed through it.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, Iterable, Optional

_LOGGER = logging.getLogger(__name__)

# ── decisions ─────────────────────────────────────────────────────────────────
ALLOW = "allow"
DENY = "deny"
CONFIRM = "confirm"  # permitted only with explicit (human) confirmation

# ── capability sensitivity tiers ──────────────────────────────────────────────
SAFE = "safe"            # read / announce — no special authority
SENSITIVE = "sensitive"  # actuation that matters (lights, covers, modes, lock)
SECURITY = "security"    # safety/security-critical (unlock, disarm, lockdown off)

# Capability → sensitivity. Keyed by exact capability or a "domain." prefix; the
# longest matching key wins. Unknown capabilities are treated as SENSITIVE
# (conservative: an unrecognised actuation is never silently "safe").
_SENSITIVITY: Dict[str, str] = {
    "announce": SAFE,
    "read": SAFE,
    "query": SAFE,
    "camera.analyze": SAFE,
    "media_player": SAFE,
    "light": SENSITIVE,
    "switch": SENSITIVE,
    "fan": SENSITIVE,
    "climate": SENSITIVE,
    "cover": SENSITIVE,
    "scene": SENSITIVE,
    "script": SENSITIVE,
    "mode": SENSITIVE,
    "lock.lock": SENSITIVE,
    "lock.unlock": SECURITY,
    "alarm_control_panel.alarm_disarm": SECURITY,
    "alarm.disarm": SECURITY,
    "lockdown.clear": SECURITY,
    "intrusion.dismiss": SECURITY,
    "delete": SECURITY,
}


def sensitivity(capability: str) -> str:
    """The sensitivity tier for a capability (longest-prefix match; unknown →
    SENSITIVE so an unrecognised actuation is never treated as safe)."""
    cap = (capability or "").strip()
    best_key = ""
    best_sev = None
    for key, sev in _SENSITIVITY.items():
        if cap == key or cap.startswith(key + "."):
            if len(key) > len(best_key):
                best_key, best_sev = key, sev
    return best_sev if best_sev is not None else SENSITIVE


@dataclass(frozen=True)
class CapabilityToken:
    """A grant a (sub-)agent carries. ``*`` means "all capabilities" (the root)."""

    holder: str
    capabilities: FrozenSet[str] = frozenset()
    issuer: Optional[str] = None
    scope: Optional[str] = None
    expires_at: Optional[float] = None       # epoch seconds; None = no expiry
    token_id: str = field(default_factory=lambda: "cap_" + uuid.uuid4().hex)

    def grants(self, capability: str) -> bool:
        return "*" in self.capabilities or capability in self.capabilities

    def expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        return (time.time() if now is None else now) >= self.expires_at

    def derive(self, holder: str, capabilities: Iterable[str],
               *, scope: Optional[str] = None,
               ttl: Optional[float] = None,
               now: Optional[float] = None) -> "CapabilityToken":
        """A child token for ``holder``. Its capabilities are the requested set
        **intersected** with this token's — delegation narrows, never escalates.
        Its expiry is the earlier of the parent's and any ``ttl`` (seconds from
        ``now``), so a child never outlives its issuer.
        """
        requested = frozenset(capabilities)
        granted = requested if "*" in self.capabilities else (requested & self.capabilities)
        child_expiry = self.expires_at
        if ttl is not None:
            base = time.time() if now is None else now
            cand = base + ttl
            child_expiry = cand if child_expiry is None else min(child_expiry, cand)
        return CapabilityToken(holder=holder, capabilities=granted,
                               issuer=self.holder, scope=scope or self.scope,
                               expires_at=child_expiry)


@dataclass(frozen=True)
class AuthorityRequest:
    capability: str
    identity: Optional[str] = None      # human on whose behalf / who is present
    actor: str = "jarvis"               # agent making the request
    token: Optional[CapabilityToken] = None
    context: dict = field(default_factory=dict)
    situation: Optional[str] = None
    confidence: float = 1.0
    intent: Optional[str] = None
    scope: Optional[str] = None
    ts: float = field(default_factory=time.time)
    now: Optional[float] = None                 # eval time for token expiry
    revoked: FrozenSet[str] = frozenset()       # revoked token_ids


@dataclass(frozen=True)
class AuthorityDecision:
    decision: str
    reason: str
    capability: str
    sensitivity: str

    @property
    def allowed(self) -> bool:
        return self.decision == ALLOW

    @property
    def denied(self) -> bool:
        return self.decision == DENY

    @property
    def needs_confirmation(self) -> bool:
        return self.decision == CONFIRM


Policy = Callable[[AuthorityRequest], AuthorityDecision]


def default_policy(req: AuthorityRequest) -> AuthorityDecision:
    """The baseline capability policy (see module invariants)."""
    cap = req.capability
    sev = sensitivity(cap)

    # 1. Delegation can't escalate: a token-bearing actor must hold the capability,
    #    and the token must be live (not expired, not revoked).
    if req.token is not None:
        if not req.token.grants(cap):
            return AuthorityDecision(
                DENY, f"{req.actor}'s token does not grant '{cap}'", cap, sev)
        if req.token.token_id in req.revoked:
            return AuthorityDecision(
                DENY, f"{req.actor}'s token has been revoked", cap, sev)
        if req.token.expired(req.now):
            return AuthorityDecision(
                DENY, f"{req.actor}'s token has expired", cap, sev)

    # 2. Security-sensitive capabilities require explicit authority.
    if sev == SECURITY:
        if not req.identity:
            return AuthorityDecision(
                DENY, "security-sensitive capability requires an identified requester",
                cap, sev)
        return AuthorityDecision(
            CONFIRM, "security-sensitive capability requires explicit confirmation",
            cap, sev)

    # 3. Sensitive actuation: confirm when unsure, else allow.
    if sev == SENSITIVE:
        if req.confidence < 0.5:
            return AuthorityDecision(
                CONFIRM, "low confidence on a sensitive action", cap, sev)
        return AuthorityDecision(ALLOW, "sensitive action within policy", cap, sev)

    # 4. Safe capabilities.
    return AuthorityDecision(ALLOW, "safe capability", cap, sev)


@dataclass
class AuthorityParity:
    """Log-only parity tracker for the enforcement rollout.

    Callers compute ``authorize()`` alongside their existing behaviour and
    ``record`` the engine decision against what actually happened (one of ALLOW /
    DENY / CONFIRM). Enforcement is flipped on only once agreement is high on real
    traffic — this is how the safety keystone is proven before it can block.
    """

    agree: int = 0
    disagree: int = 0
    by_capability: Dict[str, list] = field(default_factory=dict)
    recent_mismatches: list = field(default_factory=list)
    _max_mismatches: int = 50

    def record(self, decision: "AuthorityDecision", actual: str) -> bool:
        """Record one engine-vs-actual comparison; returns True on agreement."""
        ok = decision.decision == actual
        cap = decision.capability
        bucket = self.by_capability.setdefault(cap, [0, 0])
        if ok:
            self.agree += 1
            bucket[0] += 1
        else:
            self.disagree += 1
            bucket[1] += 1
            self.recent_mismatches.append(
                {"capability": cap, "engine": decision.decision,
                 "actual": actual, "reason": decision.reason})
            if len(self.recent_mismatches) > self._max_mismatches:
                del self.recent_mismatches[:-self._max_mismatches]
        return ok

    @property
    def total(self) -> int:
        return self.agree + self.disagree

    @property
    def agreement_rate(self) -> float:
        return (self.agree / self.total) if self.total else 1.0

    def summary(self) -> dict:
        return {
            "agree": self.agree, "disagree": self.disagree,
            "agreement_rate": self.agreement_rate,
            "by_capability": dict(self.by_capability),
            "recent_mismatches": list(self.recent_mismatches),
        }

    # ── persistence (plain dict; the HA-aware bridge does the file I/O) ──────
    def to_dict(self) -> dict:
        """A JSON-friendly snapshot for durable storage (counts + recent
        mismatches). ``agreement_rate`` is derived, so it is not stored."""
        return {
            "agree": self.agree, "disagree": self.disagree,
            "by_capability": {k: list(v) for k, v in self.by_capability.items()},
            "recent_mismatches": list(self.recent_mismatches),
        }

    @classmethod
    def from_dict(cls, d) -> "AuthorityParity":
        """Rebuild from :meth:`to_dict`, tolerating partial/garbage input (a
        corrupt file just yields an empty-but-usable tally — never raises)."""
        p = cls()
        try:
            p.agree = int((d or {}).get("agree", 0) or 0)
            p.disagree = int((d or {}).get("disagree", 0) or 0)
            bc = (d or {}).get("by_capability") or {}
            p.by_capability = {
                str(k): [int(v[0]), int(v[1])]
                for k, v in bc.items()
                if isinstance(v, (list, tuple)) and len(v) == 2
            }
            rm = (d or {}).get("recent_mismatches") or []
            p.recent_mismatches = [m for m in rm if isinstance(m, dict)][-p._max_mismatches:]
        except Exception:
            pass
        return p


def authorize(request: AuthorityRequest, *, policy: Optional[Policy] = None) -> AuthorityDecision:
    """Resolve an authority request to ALLOW / DENY / CONFIRM. Fails closed (DENY)
    if the policy raises — this is the safety keystone, so an error is never an
    accidental allow."""
    policy = policy or default_policy
    try:
        return policy(request)
    except Exception as exc:  # fail closed
        _LOGGER.debug("authority: policy error, denying: %s", exc)
        return AuthorityDecision(
            DENY, f"policy error: {exc}", request.capability,
            sensitivity(request.capability))
