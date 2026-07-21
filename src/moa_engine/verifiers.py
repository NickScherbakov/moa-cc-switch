import subprocess
from abc import ABC, abstractmethod
from typing import List

from moa_engine.domain import Artifact, VerificationResult


class VerifierStrategy(ABC):
    """Abstract Strategy interface for verifying generated artifacts."""

    @abstractmethod
    def verify(self, artifact: Artifact) -> VerificationResult:
        """Verify the artifact and return a deterministic verification result."""
        pass


class CommandVerifier(VerifierStrategy):
    """Verifier implementation that executes a command-line check (e.g. pytest, linters)."""

    def __init__(self, command: str, timeout: int = 120):
        self._command = command
        self._timeout = timeout

    def verify(self, artifact: Artifact) -> VerificationResult:
        artifact.save()
        try:
            res = subprocess.run(
                self._command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            is_success = res.returncode == 0
            log = f"STDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
            return VerificationResult(is_success=is_success, output_log=log)
        except Exception as e:
            return VerificationResult(
                is_success=False,
                output_log=f"Ошибка верификатора: {e}",
            )


class CompositeVerifier(VerifierStrategy):
    """Chain of verifiers executed in sequence. Short-circuits on first failure."""

    def __init__(self, verifiers: List[VerifierStrategy]):
        self._verifiers = verifiers

    def verify(self, artifact: Artifact) -> VerificationResult:
        combined_log = []
        for index, verifier in enumerate(self._verifiers, 1):
            result = verifier.verify(artifact)
            combined_log.append(f"--- Step {index} ({verifier.__class__.__name__}) ---\n{result.output_log}")
            if not result.is_success:
                return VerificationResult(
                    is_success=False,
                    output_log="\n".join(combined_log),
                )
        return VerificationResult(
            is_success=True,
            output_log="\n".join(combined_log),
        )
