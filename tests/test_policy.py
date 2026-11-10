"""The safety gate. These tests are the reason it is safe to pass --execute."""

import pytest

from agentic_curator.core import PolicyViolation, Proposal, SafetyPolicy


def _delete(targets: list[str], confidence: float = 1.0, keeping: str | None = "keep.txt") -> Proposal:
    evidence = {"keeping": keeping} if keeping else {}
    return Proposal(action="delete", targets=targets, reason="t", evidence=evidence, confidence=confidence)


def test_low_confidence_is_rejected() -> None:
    allowed, rejected = SafetyPolicy().vet([_delete(["a.txt"], confidence=0.5)])
    assert not allowed and "confidence" in rejected[0]["reason"]


def test_protected_paths_are_rejected() -> None:
    allowed, rejected = SafetyPolicy().vet([_delete(["secrets/id.pem"])])
    assert not allowed and rejected[0]["reason"] == "protected path"


def test_delete_without_survivor_is_rejected() -> None:
    allowed, rejected = SafetyPolicy().vet([_delete(["a.txt"], keeping=None)])
    assert not allowed and "survivor" in rejected[0]["reason"]


def test_batch_limit() -> None:
    policy = SafetyPolicy(max_deletes_per_run=2)
    allowed, rejected = policy.vet([_delete(["a", "b"]), _delete(["c"])])
    assert len(allowed) == 1 and len(rejected) == 1


def test_dry_run_blocks_execution() -> None:
    policy = SafetyPolicy(dry_run=True)
    plan = [_delete(["a.txt"])]
    with pytest.raises(PolicyViolation, match="dry-run"):
        policy.authorise(plan, policy.plan_token(plan))


def test_token_is_order_independent_but_content_sensitive() -> None:
    a, b = _delete(["a.txt"]), _delete(["b.txt"])
    assert SafetyPolicy.plan_token([a, b]) == SafetyPolicy.plan_token([b, a])
    assert SafetyPolicy.plan_token([a, b]) != SafetyPolicy.plan_token([a, _delete(["c.txt"])])


def test_changed_plan_invalidates_approval() -> None:
    policy = SafetyPolicy(dry_run=False)
    approved = [_delete(["a.txt"])]
    token = policy.plan_token(approved)
    policy.authorise(approved, token)  # the approved plan passes
    widened = approved + [_delete(["family_photos/original.jpg"])]
    with pytest.raises(PolicyViolation, match="token mismatch"):
        policy.authorise(widened, token)  # one extra file and the token is void
