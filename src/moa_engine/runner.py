import argparse
import asyncio
import sys

from moa_engine.agents import AggregatorAgent, ProposerAgent
from moa_engine.clients import CCSwitchClient
from moa_engine.engine import MoAOrchestrator
from moa_engine.verifiers import CommandVerifier

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def cli() -> None:
    """CLI entry point for running the MoA Engine."""
    parser = argparse.ArgumentParser(description="Autonomous MoA Engine")
    parser.add_argument("--task", required=True, help="Описание задачи")
    parser.add_argument("--verify", required=True, help="Команда верификации")
    parser.add_argument("--out", default="result.py", help="Файл для сохранения")
    args = parser.parse_args()

    # Инициализация клиентов через CC Switch proxy
    claude_client = CCSwitchClient("anthropic", "https://api.anthropic.com", "ANTHROPIC_API_KEY")
    gpt_client = CCSwitchClient("openai", "https://api.openai.com/v1", "OPENAI_API_KEY")

    # Инициализация агентов
    proposers = [ProposerAgent(gpt_client), ProposerAgent(claude_client)]
    aggregator = AggregatorAgent(claude_client)
    verifier = CommandVerifier(args.verify)

    orchestrator = MoAOrchestrator(
        proposers=proposers,
        aggregator=aggregator,
        verifier=verifier,
        output_path=args.out,
    )

    success = asyncio.run(orchestrator.run_until_proven(args.task))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    cli()
