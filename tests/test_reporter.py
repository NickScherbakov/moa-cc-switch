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


def test_reporter_synergy_goal(tmp_path):
    reporter = ExecutionReporter()
    reporter.set_synergy_goal("Test Goal")
    reporter.log_iteration(
        iteration=1,
        proposals_count=1,
        proposals_snippets=["pass"],
        critique_snippet="",
        aggregated_code="pass",
        is_success=True,
        verification_log="ok",
    )

    json_path = tmp_path / "trace.json"
    reporter.generate_json_trace(str(json_path))
    import json
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["synergy_goal"] == "Test Goal"

    html_path = tmp_path / "report.html"
    reporter.generate_html_report(str(html_path))
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    assert "Test Goal" in html
    assert "Synergy Goal" in html

    md_path = tmp_path / "report.md"
    reporter.generate_markdown_report(str(md_path))
    with open(md_path, "r", encoding="utf-8") as f:
        md = f.read()
    assert "Test Goal" in md
    assert "Synergy Goal" in md
