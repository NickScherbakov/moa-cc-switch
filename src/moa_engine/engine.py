import asyncio
import sys
from typing import List, Optional

from rich.console import Console

from moa_engine.agents import AggregatorAgent, CriticAgent, ProposerAgent
from moa_engine.clients import is_error_response
from moa_engine.domain import Artifact, Task
from moa_engine.reporter import ExecutionReporter
from moa_engine.verifiers import VerifierStrategy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

console = Console()


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

    async def run_until_proven(self, task_description: str, synergy_goal: str = "") -> bool:
        """Run Mixture-of-Agents loop iteratively until verification succeeds or max iterations reached."""
        task = Task(description=task_description, synergy_goal=synergy_goal)

        for iteration in range(1, self._max_iterations + 1):
            print(f"\n--- Итерация {iteration}/{self._max_iterations} ---")

            # Concurrent execution of all proposer agents via asyncio.gather
            tasks = [agent.process(task) for agent in self._proposers]
            proposals_raw = await asyncio.gather(*tasks, return_exceptions=True)
            
            proposals: List[str] = []
            for agent, p in zip(self._proposers, proposals_raw):
                client_name = agent._client.__class__.__name__
                if isinstance(p, str) and p.strip() and not is_error_response(p):
                    console.print(f"[green]✅ {client_name} успешно сгенерировал вариант ({len(p)} симв.)[/green]")
                    proposals.append(f"### Вариант от {client_name}:\n{p}")
                elif isinstance(p, str) and is_error_response(p):
                    first_err_line = p.strip().splitlines()[0] if p.strip() else p
                    console.print(f"[yellow]⚠️ {client_name} вернул ошибку: {first_err_line}[/yellow]")
                elif isinstance(p, Exception):
                    console.print(f"[bold red]❌ {client_name} упал с исключением: {p}[/bold red]")

            if not proposals:
                print("⚠️ Ни один агент не вернул валидный результат. Ожидание...", file=sys.stderr)
                await asyncio.sleep(1)
                continue

            critique = ""
            if self._critic:
                try:
                    critic_name = self._critic._client.__class__.__name__
                    crit_res = await self._critic.process(task)
                    if isinstance(crit_res, str) and not is_error_response(crit_res):
                        critique = crit_res
                        console.print(f"[magenta]🕵️ {critic_name} провел ревью[/magenta]")
                    else:
                        print("⚠️ Critic agent returned error, skipping critique.", file=sys.stderr)
                except Exception as e:
                    print(f"⚠️ Critic agent raised exception: {e}", file=sys.stderr)

            agg_name = self._aggregator._client.__class__.__name__
            code = await self._aggregator.process_proposals(task, proposals, critique=critique)
            if is_error_response(code):
                print("⚠️ Aggregator returned error, falling back to longest valid proposal.", file=sys.stderr)
                code = max(proposals, key=len)
            else:
                console.print(f"[cyan]🧠 {agg_name} синтезировал итоговый код[/cyan]")

            artifact = Artifact(path=self._output_path, content=code)

            try:
                result = await self._verifier.verify(artifact)
            except Exception as e:
                console.print(f"[bold red]Ошибка верификации (инфраструктура): {e}[/bold red]")
                continue

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
                if synergy_goal:
                    console.print(
                        f"\n[bold green]🏆 В результате синергического мышления команды была достигнута цель:[/bold green]\n[italic green]{synergy_goal}[/italic green]"
                    )
                else:
                    print("\n✅ Задача успешно и доказуемо решена!")
                self._reporter.generate_html_report()
                self._reporter.generate_markdown_report()
                self._reporter.generate_json_trace()
                return True

            print("❌ Проверка не пройдена. Обновление истории ошибок...")
            task = Task(
                description=task_description,
                synergy_goal=synergy_goal,
                error_history=(
                    task.error_history + f"\n\n--- Ошибки Итерации {iteration} ---\n{result.output_log}"
                ),
            )

        self._reporter.generate_html_report()
        self._reporter.generate_markdown_report()
        self._reporter.generate_json_trace()
        return False
