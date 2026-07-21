import asyncio
import sys
from typing import List

from moa_engine.agents import AggregatorAgent, ProposerAgent
from moa_engine.domain import Artifact, Task
from moa_engine.verifiers import VerifierStrategy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class MoAOrchestrator:
    """Core autonomous Mixture-of-Agents orchestrator."""

    def __init__(
        self,
        proposers: List[ProposerAgent],
        aggregator: AggregatorAgent,
        verifier: VerifierStrategy,
        output_path: str,
        max_iterations: int = 50,
    ):
        self._proposers = proposers
        self._aggregator = aggregator
        self._verifier = verifier
        self._output_path = output_path
        self._max_iterations = max_iterations

    async def run_until_proven(self, task_description: str) -> bool:
        """Run Mixture-of-Agents loop iteratively until verification succeeds or max iterations reached."""
        task = Task(description=task_description)

        for iteration in range(1, self._max_iterations + 1):
            print(f"\n--- Итерация {iteration}/{self._max_iterations} ---")

            tasks = [agent.process(task) for agent in self._proposers]
            proposals = [p for p in await asyncio.gather(*tasks) if p]

            if not proposals:
                print("⚠️ Ни один агент не вернул результат. Ожидание...")
                await asyncio.sleep(1)
                continue

            code = await self._aggregator.process_proposals(task, proposals)
            artifact = Artifact(path=self._output_path, content=code)

            result = self._verifier.verify(artifact)

            if result.is_success:
                print("\n✅ Задача успешно и доказуемо решена!")
                return True

            print("❌ Проверка не пройдена. Обновление истории ошибок...")
            task = Task(
                description=task_description,
                error_history=(
                    f"Итерация {iteration} завершилась ошибкой:\n{result.output_log}"
                ),
            )

        return False
