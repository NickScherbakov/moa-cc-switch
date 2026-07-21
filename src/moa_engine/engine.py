import asyncio
import sys
from typing import List, Optional

from moa_engine.agents import AggregatorAgent, CriticAgent, ProposerAgent
from moa_engine.domain import Artifact, Task
from moa_engine.reporter import ExecutionReporter
from moa_engine.verifiers import VerifierStrategy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


class MoAOrchestrator:
    """Core autonomous Mixture-of-Agents orchestrator with async gather and trace reporting."""

    def __init__(
        self,
        proposers: List[ProposerAgent],
        aggregator: AggregatorAgent,
        verifier: VerifierStrategy,
        output_path: str,
        critic: Optional[CriticAgent] = None,
        reporter: Optional[ExecutionReporter] = None,
        max_iterations: int = 50,
    ):
        self._proposers = proposers
        self._aggregator = aggregator
        self._verifier = verifier
        self._output_path = output_path
        self._critic = critic
        self._reporter = reporter or ExecutionReporter()
        self._max_iterations = max_iterations

    async def run_until_proven(self, task_description: str) -> bool:
        """Run Mixture-of-Agents loop iteratively until verification succeeds or max iterations reached."""
        task = Task(description=task_description)

        for iteration in range(1, self._max_iterations + 1):
            print(f"\n--- Итерация {iteration}/{self._max_iterations} ---")

            # Concurrent execution of all proposer agents via asyncio.gather
            tasks = [agent.process(task) for agent in self._proposers]
            proposals_raw = await asyncio.gather(*tasks, return_exceptions=True)
            
            proposals: List[str] = []
            for p in proposals_raw:
                if isinstance(p, str) and p.strip():
                    proposals.append(p)
                elif isinstance(p, Exception):
                    print(f"⚠️ Proposer agent raised exception: {p}", file=sys.stderr)

            if not proposals:
                print("⚠️ Ни один агент не вернул результат. Ожидание...")
                await asyncio.sleep(1)
                continue

            critique = ""
            if self._critic:
                try:
                    critique = await self._critic.process(task)
                except Exception as e:
                    print(f"⚠️ Critic agent raised exception: {e}", file=sys.stderr)

            code = await self._aggregator.process_proposals(task, proposals, critique=critique)
            artifact = Artifact(path=self._output_path, content=code)

            result = self._verifier.verify(artifact)

            # Log to reporter
            self._reporter.log_iteration(
                iteration=iteration,
                proposals_count=len(proposals),
                proposals_snippets=[p[:100] for p in proposals],
                critique_snippet=critique[:200] if critique else "",
                aggregated_code=code,
                is_success=result.is_success,
                verification_log=result.output_log,
            )

            if result.is_success:
                print("\n✅ Задача успешно и доказуемо решена!")
                self._reporter.generate_html_report()
                self._reporter.generate_markdown_report()
                self._reporter.generate_json_trace()
                return True

            print("❌ Проверка не пройдена. Обновление истории ошибок...")
            task = Task(
                description=task_description,
                error_history=(
                    f"Итерация {iteration} завершилась ошибкой:\n{result.output_log}"
                ),
            )

        self._reporter.generate_html_report()
        self._reporter.generate_markdown_report()
        self._reporter.generate_json_trace()
        return False
