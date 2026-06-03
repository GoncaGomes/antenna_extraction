from __future__ import annotations

import json

import pytest

from antenna_ingest.utils.json_io import read_json, write_json


def test_write_json_writes_a_file(tmp_path) -> None:
    path = tmp_path / "data.json"

    write_json(path, {"value": 1})

    assert path.exists()


def test_read_json_reads_same_content(tmp_path) -> None:
    path = tmp_path / "data.json"
    content = {"value": 1, "name": "antenna"}

    write_json(path, content)

    assert read_json(path) == content


def test_write_json_creates_parent_folders(tmp_path) -> None:
    path = tmp_path / "nested" / "data.json"

    write_json(path, {"value": 1})

    assert path.exists()


def test_read_json_raises_value_error_for_list_root(tmp_path) -> None:
    path = tmp_path / "data.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ValueError):
        read_json(path)


def test_utf8_content_is_preserved(tmp_path) -> None:
    path = tmp_path / "data.json"
    content = {"title": "Medição de antena"}

    write_json(path, content)

    assert read_json(path) == content
    assert "Medição de antena" in path.read_text(encoding="utf-8")
