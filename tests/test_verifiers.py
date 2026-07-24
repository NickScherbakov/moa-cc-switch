import pytest
from moa_engine.domain import Artifact, VerificationResult
from moa_engine.verifiers import CommandVerifier, CompositeVerifier


def test_composite_verifier_all_pass():
    v1 = CommandVerifier("python -c \"assert True\"")
    v2 = CommandVerifier("python -c \"assert 1 == 1\"")
    composite = CompositeVerifier([v1, v2])

    art = Artifact(path="dummy.py", content="pass")
    res = composite.verify(art)
    assert res.is_success is True
    assert "Step 1" in res.output_log
    assert "Step 2" in res.output_log


def test_composite_verifier_short_circuit_on_failure():
    v1 = CommandVerifier("python -c \"assert False, 'v1 error'\"")
    v2 = CommandVerifier("python -c \"assert True\"")
    composite = CompositeVerifier([v1, v2])

    art = Artifact(path="dummy.py", content="pass")
    res = composite.verify(art)
    assert res.is_success is False
    assert "v1 error" in res.output_log
    assert "Step 2" not in res.output_log
