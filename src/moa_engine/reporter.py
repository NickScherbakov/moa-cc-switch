import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class IterationLog:
    iteration: int
    proposals_count: int
    critique_snippet: str
    is_success: bool
    verification_log: str


class ExecutionReporter:
    """Generates structured HTML and Markdown execution reports for MoA runs."""

    def __init__(self):
        self.logs: List[IterationLog] = []

    def log_iteration(
        self,
        iteration: int,
        proposals_count: int,
        critique_snippet: str,
        is_success: bool,
        verification_log: str,
    ) -> None:
        self.logs.append(
            IterationLog(
                iteration=iteration,
                proposals_count=proposals_count,
                critique_snippet=critique_snippet,
                is_success=is_success,
                verification_log=verification_log,
            )
        )

    def generate_html_report(self, output_file: str = "moa_report.html") -> str:
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>MoA Engine Execution Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 2rem; background: #0f172a; color: #f8fafc; }}
        h1 {{ color: #38bdf8; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; border-left: 5px solid #64748b; }}
        .success {{ border-left-color: #22c55e; }}
        .failure {{ border-left-color: #ef4444; }}
        pre {{ background: #090d16; padding: 1rem; border-radius: 4px; overflow-x: auto; color: #cbd5e1; }}
        .badge {{ display: inline-block; padding: 0.25rem 0.5rem; border-radius: 4px; font-weight: bold; font-size: 0.85rem; }}
        .badge-success {{ background: #166534; color: #86efac; }}
        .badge-failure {{ background: #991b1b; color: #fca5a5; }}
    </style>
</head>
<body>
    <h1>🚀 MoA Engine Execution Report</h1>
    <p>Total Iterations: <strong>{len(self.logs)}</strong></p>
"""
        for log in self.logs:
            badge = '<span class="badge badge-success">PASSED</span>' if log.is_success else '<span class="badge badge-failure">FAILED</span>'
            card_class = "success" if log.is_success else "failure"
            html_content += f"""
    <div class="card {card_class}">
        <h2>Iteration {log.iteration} {badge}</h2>
        <p>Proposals Evaluated: {log.proposals_count}</p>
        <details>
            <summary>Verification Logs</summary>
            <pre>{log.verification_log}</pre>
        </details>
    </div>
"""
        html_content += "</body></html>"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(html_content)
        return output_file
