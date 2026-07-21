import os
from moa_engine.reporter import ExecutionReporter


def test_execution_reporter_html():
    reporter = ExecutionReporter()
    reporter.log_iteration(
        iteration=1,
        proposals_count=2,
        critique_snippet="Looks good",
        is_success=True,
        verification_log="All tests passed",
    )

    out = reporter.generate_html_report("test_report.html")
    assert os.path.exists("test_report.html")
    with open("test_report.html", "r", encoding="utf-8") as f:
        content = f.read()
        assert "MoA Engine Execution Report" in content
        assert "Iteration 1" in content
        assert "PASSED" in content

    os.remove("test_report.html")
