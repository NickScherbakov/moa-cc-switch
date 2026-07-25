import json
import asyncio
import re
import shlex
import subprocess
from abc import ABC, abstractmethod
from typing import List

from moa_engine.clients import LLMClient
from moa_engine.domain import Artifact, Message, VerificationResult


class VerifierStrategy(ABC):
    """Abstract Strategy interface for verifying generated artifacts."""

    @abstractmethod
    async def verify(self, artifact: Artifact, synergy_goal: str = "") -> VerificationResult:
        """Verify the artifact and return a deterministic verification result."""
        pass


class CommandVerifier(VerifierStrategy):
    """Verifier implementation that executes a command-line check (e.g. pytest, linters)."""

    def __init__(self, command: str, timeout: int = 120):
        self._command = command
        self._timeout = timeout

    async def verify(self, artifact: Artifact, synergy_goal: str = "") -> VerificationResult:
        artifact.save()
        try:
            cmd_args = shlex.split(self._command)
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._timeout,
            )
            is_success = process.returncode == 0
            log = (
                f"STDOUT:\n{stdout.decode('utf-8', errors='ignore')}"
                f"\nSTDERR:\n{stderr.decode('utf-8', errors='ignore')}"
            )
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

    async def verify(self, artifact: Artifact, synergy_goal: str = "") -> VerificationResult:
        combined_log = []
        for index, verifier in enumerate(self._verifiers, 1):
            result = await verifier.verify(artifact, synergy_goal)
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


class LLMVerifier(VerifierStrategy):
    """Verifier implementation that evaluates artifact contents via an LLM judge."""

    def __init__(self, client: LLMClient, evaluation_prompt: str):
        self._client = client
        self._evaluation_prompt = evaluation_prompt

    async def verify(self, artifact: Artifact, synergy_goal: str = "") -> VerificationResult:
        artifact.save()

        system_content = (
            f"{self._evaluation_prompt}\n\n"
            "Потребуется вернуть результат строго в формате JSON:\n"
            '{"is_success": true/false, "reason": "текст"}'
        )
        if synergy_goal:
            system_content += (
                f"\nПри оценке артефакта строго учитывай главную цель команды: {synergy_goal}. "
                "Артефакт должен способствовать ее достижению."
            )
        user_content = (
            f"Содержимое артефакта:\n\n{artifact.content}\n\n"
            'Оцени артефакт выше и верни ответ строго в JSON формате: {"is_success": true/false, "reason": "..."}'
        )
        messages = [
            Message(role="system", content=system_content),
            Message(role="user", content=user_content),
        ]

        try:
            raw_response = await self._client.generate(messages, temperature=0.0)
            cleaned_text = raw_response.strip()
            match = re.search(r"\{.*\}", cleaned_text, re.DOTALL)
            json_text = match.group(0) if match else cleaned_text

            data = json.loads(json_text)
            if not isinstance(data, dict):
                raise ValueError(f"Ожидался JSON объект dict, получено: {type(data)}")

            is_success = bool(data.get("is_success", False))
            reason = str(data.get("reason", ""))
            return VerificationResult(is_success=is_success, output_log=reason)
        except Exception as e:
            raise RuntimeError(f"Внутренняя ошибка LLM-верификатора: {e}")
