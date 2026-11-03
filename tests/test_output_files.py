import os
import stat

import pandas as pd
import plotly.graph_objs
import pytest

from mcp_server_starrocks import server
from mcp_server_starrocks.db_client import ResultSet


@pytest.fixture
def exports(tmp_path, monkeypatch):
    root = tmp_path / "exports"
    root.mkdir(mode=0o755)
    monkeypatch.setattr(server, "output_dir", str(root))
    monkeypatch.setattr(server, "CHART_OUTPUT_DIR", str(root))
    monkeypatch.setenv("STARROCKS_MCP_RESTRICT_OUTPUT", "1")
    monkeypatch.setattr(server.db_client, "execute", lambda *a, **kw: ResultSet(
        success=True, execution_time=0, column_names=["amount"], rows=[[123]],
        pandas=pd.DataFrame({"amount": [123]}),
    ))
    previous = os.umask(0o077)
    try:
        yield root
    finally:
        os.umask(previous)


@pytest.mark.parametrize("escape", ["absolute", "parent", "directory_link", "file_link"])
def test_query_cannot_overwrite_private_pool_files(exports, tmp_path, escape):
    home = tmp_path / "home"
    home.mkdir()
    config = home / "config.json"
    config.write_text("private configuration")
    if escape == "absolute":
        output = str(config)
    elif escape == "parent":
        output = "../home/config.json"
    elif escape == "directory_link":
        (exports / "link").symlink_to(home, target_is_directory=True)
        output = "link/config.json"
    else:
        (exports / "config.json").symlink_to(config)
        output = "config.json"
    result = server.read_query("SELECT 123 AS amount", output_file=output)
    assert "output_file" not in result.structured_content
    assert config.read_text() == "private configuration"


@pytest.mark.parametrize("fmt,expected", [
    ("csv", "amount\n123\n"),
    ("tsv", "amount\n123\n"),
    ("json", '[{"amount": 123}]'),
    ("jsonl", '{"amount": 123}\n'),
])
def test_query_exports_remain_readable_under_private_umask(exports, fmt, expected):
    result = server.read_query("SELECT 123 AS amount", output_file=f"reports/result.{fmt}")
    path = exports / "reports" / f"result.{fmt}"
    assert result.structured_content["output_file"] == str(path)
    assert path.read_text() == expected
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o755


def test_html_chart_returns_a_readable_export(exports, monkeypatch):
    monkeypatch.setattr(server.time, "time", lambda: 1234567890)
    def no_preview(*args, **kwargs):
        raise ValueError("preview unavailable")
    monkeypatch.setattr(plotly.graph_objs.Figure, "to_image", no_preview)
    result = server.query_and_plotly_chart(
        "SELECT 123 AS amount", "px.bar(df, y='amount')", format="html",
    )
    path = exports / "starrocks_chart_1234567890000.html"
    assert result.structured_content["html_path"] == str(path)
    assert "Plotly.newPlot" in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_unrestricted_query_still_accepts_an_absolute_path(exports, tmp_path, monkeypatch):
    monkeypatch.delenv("STARROCKS_MCP_RESTRICT_OUTPUT")
    path = tmp_path / "unlocked.csv"
    result = server.read_query("SELECT 123 AS amount", output_file=str(path))
    assert result.structured_content["output_file"] == str(path)
    assert path.read_text() == "amount\n123\n"
