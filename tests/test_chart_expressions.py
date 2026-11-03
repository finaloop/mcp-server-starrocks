import pandas as pd
import plotly.express as px
import pytest

from mcp_server_starrocks import server
from mcp_server_starrocks.db_client import ResultSet


@pytest.fixture
def chart_data(monkeypatch):
    frame = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": ["first", "second"]})
    monkeypatch.setattr(
        server.db_client,
        "execute",
        lambda *args, **kwargs: ResultSet(
            success=True,
            execution_time=0,
            column_names=list(frame.columns),
            rows=frame.values.tolist(),
            pandas=frame,
        ),
    )


def chart(expression):
    return server.query_and_plotly_chart(
        "SELECT a, b, c FROM chart_data", expression, format="json"
    ).structured_content


def test_chart_requests_cannot_change_bindings_or_interpret_text(chart_data):
    scatter = px.scatter
    try:
        first = chart("px.__setattr__('scatter', __builtins__['eval'])")
        unchanged = px.scatter is scatter
        second = chart('px.scatter("(_ for _ in ()).throw(Exception(6 * 7))")')
    finally:
        px.scatter = scatter

    assert unchanged, "a chart request changed the shared Plotly binding"
    assert first["success"] is False
    assert second["success"] is False
    assert second["error_message"] != "42"
    assert chart("px.scatter(df, x='a', y='b')")["success"] is True


@pytest.mark.parametrize(
    "expression",
    [
        "px.__setattr__('scatter', __builtins__['eval'])",
        "px.scatter(df, title=__builtins__)",
        "px.scatter(df, title=__builtins__['eval'])",
        "px.scatter(df, x=df.__class__)",
        "px.scatter.__call__(df, x='a')",
        "px.scatter(df, x=df['a'])",
        "px.scatter(df, title=str(42))",
        "px.unknown(df, x='a')",
        "px.scatter(df, title=df)",
        "px.scatter(df, title='a' + 'b')",
        "px.scatter(df, **{'x': 'a'})",
        "px.scatter(df, __class__='a')",
        "px.scatter(df, unknown='a')",
        "px.scatter(df, x='missing')",
        "px.scatter(df, labels={'missing': 'Amount'})",
        "px.scatter(df, hover_data=['missing'])",
        "px.scatter(df, opacity=True)",
        "px.scatter(df, log_x='yes')",
        "px.scatter(df, width='wide')",
        "px.scatter(df, x='a', x='b')",
        "px.scatter(df); px.bar(df)",
        "px.scatter(",
    ],
)
def test_refuses_expressions_outside_the_chart_language(chart_data, expression):
    result = chart(expression)
    assert result["success"] is False
    assert result["error_message"] == "Invalid chart expression."


@pytest.mark.parametrize(
    "expression,trace_type",
    [
        ("px.scatter(df, x='a', y='b')", "scatter"),
        ("px.line(df, x='a', y='b', markers=True)", "scatter"),
        ("px.bar(df, x='c', y='b', orientation='v')", "bar"),
        ("px.histogram(df, x='a', nbins=2)", "histogram"),
        ("px.box(df, x='c', y='b', points='all')", "box"),
        ("px.pie(df, names='c', values='b', hole=0.3)", "pie"),
        ("px.area(df, x='a', y='b')", "scatter"),
        ("px.scatter(df, x='a', y=['a', 'b'])", "scatter"),
    ],
)
def test_supported_charts_render(chart_data, expression, trace_type):
    result = chart(expression)
    assert result["success"] is True
    assert result["data"][0]["type"] == trace_type


def test_titles_labels_and_literal_options_render(chart_data):
    result = chart(
        "px.scatter(df, x='a', y='b', color='c', title='Amounts', "
        "labels={'a': 'Quantity', 'b': 'Amount', 'c': 'Category'}, "
        "hover_data=['b'], opacity=0.5, log_x=False, width=640, "
        "range_y=[-1, 10], template='simple_white')"
    )
    assert result["success"] is True
    assert [trace["name"] for trace in result["data"]] == ["first", "second"]
    assert result["layout"]["title"]["text"] == "Amounts"
    assert result["layout"]["xaxis"]["title"]["text"] == "Quantity"
    assert result["layout"]["yaxis"]["title"]["text"] == "Amount"
    assert result["layout"]["yaxis"]["range"] == [-1, 10]
    assert result["layout"]["width"] == 640


def test_chart_errors_do_not_return_exception_details(chart_data):
    result = chart("px.scatter(df, x='a', template='not-a-template')")
    assert result == {"success": False, "error_message": "Unable to generate chart."}
