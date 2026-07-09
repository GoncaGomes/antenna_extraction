from __future__ import annotations

from antenna_ingest.cli import main
from tests.test_retrieval_index import make_retrieval_run


def test_cli_build_index_and_search(tmp_path, capsys) -> None:
    run_dir = make_retrieval_run(tmp_path)

    build_exit_code = main(["retrieval", "build-index", str(run_dir)])
    search_exit_code = main(
        [
            "retrieval",
            "search",
            str(run_dir),
            "S1 S2 P1 P2 L1 dimensions mm",
            "--top-k",
            "3",
        ]
    )

    output = capsys.readouterr().out
    assert build_exit_code == 0
    assert search_exit_code == 0
    assert "Evidence index:" in output
    assert "table_001" in output
    assert "Reasons:" in output
