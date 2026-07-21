import os
import pytest
from moa_engine.reporter import ExecutionReporter


def test_execution_reporter_all_formats(tmp_path):
    reporter = ExecutionReporter()
    reporter.log_iteration(
        iteration=1,
        proposals_count=2,
        proposals_snippets=["def a(): pass", "def b(): pass"],
        critique_snippet="Code looks good",
        aggregated_code="def final(): pass",
        is_success=True,
        verification_log="All tests passed",
    )

    html_path = tmp_path / "report.html"
    md_path = tmp_path / "report.md"
    json_path = tmp_path / "trace.json"

    reporter.generate_html_report(str(html_path))
    reporter.generate_markdown_report(str(md_path))
    reporter.generate_json_trace(str(json_path))

    assert os.path.exists(html_path)
    assert os.path.exists(md_path)
    assert os.path.exists(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        import json
        data = json.load(f)
        assert data["total_iterations"] == 1
        assert data["final_success"] is True
        assert data["iterations"][0]["aggregated_code"] == "def final(): pass"
