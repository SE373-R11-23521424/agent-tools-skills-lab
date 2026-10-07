"""File tools: liệt kê/đọc/ghi đúng phạm vi, lỗi có cấu trúc, chặn traversal/absolute/symlink escape."""

import json

import pytest

from reset_workspace import WorkspaceError, ensure_workspace, reset_workspace
from tools import list_files, read_file, write_file
from tools.files import MAX_READ_BYTES, _list, _read, _write


@pytest.fixture
def ws(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "data").mkdir(parents=True)
    (workspace / "output").mkdir()
    (workspace / "data" / "note.md").write_text("Xin chào", encoding="utf-8")
    return workspace


def test_read_ok(ws):
    assert _read(ws, "data/note.md") == {"ok": True, "path": "data/note.md", "content": "Xin chào"}


def test_read_missing_file(ws):
    result = _read(ws, "data/khong-ton-tai.md")
    assert result["ok"] is False and result["error"]["code"] == "FILE_NOT_FOUND"


@pytest.mark.parametrize("path", ["../secret.txt", "data/../../secret.txt"])
def test_read_traversal_blocked(ws, path):
    (ws.parent / "secret.txt").write_text("secret")
    assert _read(ws, path)["error"]["code"] == "PATH_OUTSIDE_WORKSPACE"


def test_read_absolute_path_blocked(ws):
    assert _read(ws, str(ws / "data" / "note.md"))["error"]["code"] == "PATH_OUTSIDE_WORKSPACE"


def test_read_symlink_escape_blocked(ws):
    (ws.parent / "secret.txt").write_text("secret")
    (ws / "data" / "link.txt").symlink_to(ws.parent / "secret.txt")
    result = _read(ws, "data/link.txt")
    assert result["error"]["code"] == "PATH_OUTSIDE_WORKSPACE"
    assert "content" not in result


def test_read_too_large_and_non_utf8(ws):
    (ws / "data" / "big.txt").write_text("a" * (MAX_READ_BYTES + 1))
    (ws / "data" / "bin.dat").write_bytes(b"\xff\xfe\x00")
    assert _read(ws, "data/big.txt")["error"]["code"] == "FILE_TOO_LARGE"
    assert _read(ws, "data/bin.dat")["error"]["code"] == "NOT_UTF8_TEXT"
    assert _read(ws, "data")["error"]["code"] == "IS_A_DIRECTORY"


def test_list_direct_entries_sorted_not_recursive(ws):
    (ws / "data" / "b.md").write_text("B")
    (ws / "data" / "sub").mkdir()
    (ws / "data" / "sub" / "deep.md").write_text("D")
    assert _list(ws, "data") == {
        "ok": True,
        "path": "data",
        "entries": [
            {"name": "b.md", "path": "data/b.md", "type": "file"},
            {"name": "note.md", "path": "data/note.md", "type": "file"},
            {"name": "sub", "path": "data/sub", "type": "directory"},
        ],
    }


def test_list_workspace_root(ws):
    result = _list(ws, ".")
    assert result["path"] == "."
    assert result["entries"] == [
        {"name": "data", "path": "data", "type": "directory"},
        {"name": "output", "path": "output", "type": "directory"},
    ]


def test_list_empty_directory_is_ok(ws):
    assert _list(ws, "output") == {"ok": True, "path": "output", "entries": []}


def test_list_missing_or_file_is_error(ws):
    missing = _list(ws, "khong-co")
    assert missing["ok"] is False and missing["error"]["code"] == "DIRECTORY_NOT_FOUND"
    assert "entries" not in missing
    on_file = _list(ws, "data/note.md")
    assert on_file["ok"] is False and on_file["error"]["code"] == "NOT_A_DIRECTORY"
    assert _list(ws, "")["error"]["code"] == "INVALID_PATH"


@pytest.mark.parametrize("path", ["..", "data/../..", "../outside"])
def test_list_traversal_blocked(ws, path):
    (ws.parent / "outside").mkdir()
    assert _list(ws, path)["error"]["code"] == "PATH_OUTSIDE_WORKSPACE"


def test_list_absolute_path_blocked(ws):
    assert _list(ws, str(ws / "data"))["error"]["code"] == "PATH_OUTSIDE_WORKSPACE"


def test_list_symlink_escape_blocked(ws):
    outside = ws.parent / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    (ws / "data" / "escape").symlink_to(outside, target_is_directory=True)
    (ws / "data" / "secret-link.txt").symlink_to(outside / "secret.txt")
    (ws / "data" / "broken").symlink_to(ws / "khong-co")
    (ws / "data" / "inside-link.md").symlink_to(ws / "data" / "note.md")
    assert _list(ws, "data/escape")["error"]["code"] == "PATH_OUTSIDE_WORKSPACE"
    names = [e["name"] for e in _list(ws, "data")["entries"]]
    assert names == ["inside-link.md", "note.md"]


def test_write_created_then_updated(ws):
    first = _write(ws, "output/reports/summary.md", "# Tóm tắt")
    assert first == {"ok": True, "path": "output/reports/summary.md", "bytes": len("# Tóm tắt".encode()), "status": "created"}
    second = _write(ws, "output/reports/summary.md", "v2")
    assert second["status"] == "updated" and second["bytes"] == 2
    assert (ws / "output" / "reports" / "summary.md").read_text(encoding="utf-8") == "v2"


@pytest.mark.parametrize("path", ["data/note.md", "summary.md", "output", "output/../data/x.md", "../output/x.md"])
def test_write_outside_output_rejected(ws, path):
    result = _write(ws, path, "x")
    assert result["ok"] is False
    assert result["error"]["code"] in {"PATH_OUTSIDE_OUTPUT", "PATH_OUTSIDE_WORKSPACE"}
    assert (ws / "data" / "note.md").read_text(encoding="utf-8") == "Xin chào"


def test_write_absolute_and_symlink_escape_rejected(ws, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (ws / "output" / "escape").symlink_to(outside, target_is_directory=True)
    assert _write(ws, str(ws / "output" / "a.md"), "x")["error"]["code"] == "PATH_OUTSIDE_WORKSPACE"
    assert _write(ws, "output/escape/a.md", "x")["ok"] is False
    assert list(outside.iterdir()) == []


def test_tools_return_json_against_project_workspace(lab_dirs):
    listed = json.loads(list_files.invoke({"path": "data"}))
    assert {"name": "weekly_notes.md", "path": "data/weekly_notes.md", "type": "file"} in listed["entries"]
    assert json.loads(read_file.invoke({"path": "data/weekly_notes.md"}))["ok"] is True
    written = json.loads(write_file.invoke({"path": "output/t.md", "content": "ok"}))
    assert written["status"] == "created"
    assert json.loads(read_file.invoke({"path": "output/t.md"}))["content"] == "ok"


def test_reset_restores_fixtures_and_requires_marker(tmp_path):
    fixtures = tmp_path / "fixtures"
    (fixtures / "data").mkdir(parents=True)
    (fixtures / "data" / "a.md").write_text("A")
    workspace = tmp_path / "workspace"
    ensure_workspace(workspace, fixtures)
    (workspace / "data" / "a.md").write_text("changed")
    (workspace / "output" / "r.md").write_text("R")
    ensure_workspace(workspace, fixtures)  # không ghi đè khi đã có workspace
    assert (workspace / "data" / "a.md").read_text() == "changed"
    reset_workspace(workspace, fixtures)
    assert (workspace / "data" / "a.md").read_text() == "A"
    assert list((workspace / "output").iterdir()) == []

    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("keep")
    with pytest.raises(WorkspaceError):
        reset_workspace(foreign, fixtures)
    with pytest.raises(WorkspaceError):
        ensure_workspace(foreign, fixtures)
    assert (foreign / "keep.txt").read_text() == "keep"
