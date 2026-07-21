import argparse
import asyncio
import sys
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from moa_engine.agents import AggregatorAgent, CriticAgent, ProposerAgent
from moa_engine.clients import CCSwitchClient
from moa_engine.engine import MoAOrchestrator
from moa_engine.verifiers import CommandVerifier, CompositeVerifier

console = Console()


def cli() -> None:
    """CLI entry point for running the MoA Engine with Rich UI."""
    parser = argparse.ArgumentParser(description="Autonomous MoA Engine")
    parser.add_argument("--task", required=True, help="Описание задачи")
    parser.add_argument("--verify", required=True, help="Команда верификации")
    parser.add_argument("--out", default="result.py", help="Файл для сохранения")
    args = parser.parse_args()

    console.print(
        Panel.fit(
            "[bold cyan]🚀 Mixture-of-Agents Autonomous Engine[/bold cyan]\n"
            f"[yellow]Task:[/yellow] {args.task}\n"
            f"[yellow]Target File:[/yellow] {args.out}",
            title="MoA Engine v0.2.0",
        )
    )

    # Инициализация клиентов через CC Switch proxy / direct providers
    claude_client = CCSwitchClient("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY")
    gpt_client = CCSwitchClient("openai", "https://api.openai.com/v1", "OPENAI_API_KEY")

    # Инициализация агентов
    proposers = [
        ProposerAgent(gpt_client, temperature=0.8),
        ProposerAgent(claude_client, temperature=0.3),
    ]
    critic = CriticAgent(claude_client)
    aggregator = AggregatorAgent(claude_client)
    verifier = CommandVerifier(args.verify)

    orchestrator = MoAOrchestrator(
        proposers=proposers,
        aggregator=aggregator,
        verifier=verifier,
        output_path=args.out,
        critic=critic,
    )

    success = asyncio.run(orchestrator.run_until_proven(args.task))
    if success:
        console.print("[bold green]✨ Orchestration completed successfully![/bold green]")
    else:
        console.print("[bold red]❌ Orchestration stopped: max iterations reached.[/bold red]")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    cli()
