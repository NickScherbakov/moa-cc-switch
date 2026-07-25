import asyncio
import json
import re
import sys
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel

from moa_engine.agents import AggregatorAgent, CriticAgent, ProposerAgent
from moa_engine.clients import is_error_response
from moa_engine.domain import Action, Artifact, DiscoveryState, Message, Task
from moa_engine.reporter import ExecutionReporter
from moa_engine.tools import ToolRegistry
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
        tools: Optional[ToolRegistry] = None,
    ):
        self._proposers = proposers
        self._aggregator = aggregator
        self._verifier = verifier
        self._output_path = output_path
        self._critic = critic
        self._reporter = reporter or ExecutionReporter()
        self._max_iterations = max_iterations
        self._tools = tools or ToolRegistry()

        # Inject tool specifications into all agents if tools are registered
        tool_specs = self._tools.list_tools()
        if tool_specs:
            for agent in self._proposers:
                agent.set_tools(tool_specs)
            if self._critic:
                self._critic.set_tools(tool_specs)
            self._aggregator.set_tools(tool_specs)

    async def run_discovery_chat(self, initial_idea: str) -> str:
        """Run interactive Discovery Chat with continuous context compression (Rolling Summary)."""
        state = DiscoveryState(current_summary=initial_idea)
        provider_colors = ["cyan", "green", "magenta", "blue", "yellow", "bright_cyan", "bright_green"]

        while True:
            # Phase 1: Proposers
            tasks = [agent.process(state) for agent in self._proposers]
            proposals_raw = await asyncio.gather(*tasks, return_exceptions=True)

            proposals: List[str] = []
            for idx, (agent, p) in enumerate(zip(self._proposers, proposals_raw)):
                client_name = agent._client.__class__.__name__
                color = provider_colors[idx % len(provider_colors)]
                if isinstance(p, str) and p.strip() and not is_error_response(p):
                    console.print(Panel(p, title=f"Proposer ({client_name})", border_style=color))
                    proposals.append(f"### Вариант от {client_name}:\n{p}")
                elif isinstance(p, str) and is_error_response(p):
                    console.print(f"[{color}]⚠️ {client_name} вернул ошибку: {p.strip()}[/{color}]")
                elif isinstance(p, Exception):
                    console.print(f"[bold red]❌ {client_name} упал с исключением: {p}[/bold red]")

            # Phase 2: Critic
            critique = ""
            if self._critic:
                try:
                    crit_res = await self._critic.process(state)
                    if isinstance(crit_res, str) and not is_error_response(crit_res):
                        critique = crit_res
                        console.print(Panel(critique, title="Critic Review", border_style="yellow"))
                    else:
                        console.print("[yellow]⚠️ Critic agent returned error, skipping critique.[/yellow]")
                except Exception as e:
                    console.print(f"[bold red]⚠️ Critic agent raised exception: {e}[/bold red]")

            # Phase 3: Aggregator (Compression)
            agg_res = await self._aggregator.process_discovery(state, proposals, critique=critique)

            json_match = re.search(r"\{.*\}", agg_res, re.DOTALL)
            if json_match:
                try:
                    parsed = json.loads(json_match.group(0))
                    new_summary = parsed.get("summary", state.current_summary)
                    reply = parsed.get("reply", "")
                    state.current_summary = new_summary
                    state.chat_history.clear()
                    console.print(f"\n[cyan]{reply}[/cyan]")
                except Exception as e:
                    console.print(f"[bold red]⚠️ Ошибка парсинга JSON от Агрегатора: {e}[/bold red]")
                    console.print(f"[cyan]{agg_res}[/cyan]")
            else:
                console.print(f"[cyan]{agg_res}[/cyan]")

            # Phase 4: Customer / User (I/O)
            user_input = await asyncio.to_thread(input, "\n[Вы]: ")
            if user_input.strip() == "/execute":
                return state.current_summary

            state.chat_history.append(Message(role="user", content=user_input, name="User"))

    async def run_until_proven(self, task_description: str, synergy_goal: str = "") -> bool:

        """Run Mixture-of-Agents loop iteratively until verification succeeds or max iterations reached."""
        self._reporter.set_synergy_goal(synergy_goal)
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
            agg_raw = await self._aggregator.process_proposals(task, proposals, critique=critique)

            code = agg_raw
            actions_to_run: List[Action] = []

            if not is_error_response(agg_raw):
                # Try to parse JSON from Aggregator response if tools are available/actions requested
                json_match = re.search(r"\{.*\}", agg_raw, re.DOTALL)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group(0))
                        if isinstance(parsed, dict):
                            if "code" in parsed:
                                code = str(parsed["code"])
                            raw_actions = parsed.get("actions", [])
                            if isinstance(raw_actions, list):
                                for act in raw_actions:
                                    if isinstance(act, dict) and "tool_name" in act:
                                        actions_to_run.append(
                                            Action(
                                                tool_name=str(act["tool_name"]),
                                                arguments=dict(act.get("arguments", act.get("args", {}))),
                                            )
                                        )
                    except Exception as e:
                        console.print(f"[yellow]⚠️ Ошибка парсинга JSON от Агрегатора: {e}[/yellow]")
                console.print(f"[cyan]🧠 {agg_name} синтезировал итоговый код[/cyan]")
            else:
                print("⚠️ Aggregator returned error, falling back to longest valid proposal.", file=sys.stderr)
                code = max(proposals, key=len)

            # Phase 4: Execution Phase (Action Layer)
            tool_outputs: List[str] = []
            if actions_to_run:
                console.print(f"\n[bold blue]⚡ Фаза Исполнения: Запуск {len(actions_to_run)} действий через ToolRegistry...[/bold blue]")
                for action in actions_to_run:
                    console.print(Panel(
                        f"Инструмент: [bold]{action.tool_name}[/bold]\nАргументы: {action.arguments}",
                        title="Выполнение инструмента",
                        border_style="blue"
                    ))
                    tool_res = await self._tools.execute(action)
                    console.print(Panel(tool_res, title=f"Результат {action.tool_name}", border_style="cyan"))
                    tool_outputs.append(f"Инструмент '{action.tool_name}' (аргументы: {action.arguments}):\n{tool_res}")

            artifact = Artifact(path=self._output_path, content=code)

            try:
                result = await self._verifier.verify(artifact, task.synergy_goal)
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
            tool_history_chunk = ""
            if tool_outputs:
                tool_history_chunk = (
                    f"\n\n--- Результаты выполнения инструментов (Итерация {iteration}) ---\n"
                    + "\n".join(tool_outputs)
                )

            task = Task(
                description=task_description,
                synergy_goal=synergy_goal,
                error_history=(
                    task.error_history
                    + tool_history_chunk
                    + f"\n\n--- Ошибки Итерации {iteration} ---\n{result.output_log}"
                ),
            )

        self._reporter.generate_html_report()
        self._reporter.generate_markdown_report()
        self._reporter.generate_json_trace()
        return False

