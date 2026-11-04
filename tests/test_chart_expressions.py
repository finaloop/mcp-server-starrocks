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
        comprehension = chart("px.scatter(df, x=[[0 for px.defaults.__class__.__getitem__ in [px.defaults.__class__.__init__.__globals__['__builtins__']['__import__']]],[0 for px.defaults.__class__.__getitem__ in [px.defaults['os'].system]],px.defaults['touch marker']] and 'a', y='b')")
        unchanged = px.scatter is scatter
        second = chart('px.scatter("(_ for _ in ()).throw(Exception(6 * 7))")')
    finally:
        px.scatter = scatter

    assert unchanged, "a chart request changed the shared Plotly binding"
    assert comprehension["success"] is False
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
        "px.scatter(df, hover_data=['missing'])",
        "px.scatter(df, opacity=True)",
        "px.scatter(df, log_x='yes')",
        "px.scatter(df, width='wide')",
        "px.scatter(df, x=['North', 'South'])",
        "px.scatter(df, x=[10, 20])",
        "px.scatter(df, hover_data={'a': print})",
        "px.scatter(df, hover_data={'a': [1, 2]})",
        "px.scatter(df, hover_data={'missing': True})",
        "px.scatter(df, text_auto=df.x)",
        "px.scatter(df, color_continuous_scale=px.colors)",
        "px.scatter(df, color_continuous_scale=[x for x in df])",
        "px.scatter(df, color_discrete_map={'first': (value := 'red')})",
        "px.scatter(df, trendline_options={'log_x': True})",
        "px.imshow(df, img=df)",
        "px.imshow(df, x=df.columns)",
        "px.imshow(df, x=['North'])",
        "px.imshow(df, y=['Q1'])",
        "px.data.iris()",
        "px.get_trendline_results(df)",
        "px.treemap(df, path=['missing'], values='b')",
        "px.scatter(df, x='a', x='b')",
        "px.scatter(df); px.bar(df)",
        "px.scatter(",
    ],
)
def test_refuses_expressions_outside_the_chart_language(chart_data, expression):
    result = chart(expression)
    assert result["success"] is False


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


@pytest.mark.parametrize("kind", ["line", "bar", "area"])
def test_wide_form_generated_labels_render(chart_data, kind):
    result = chart(
        f"px.{kind}(df, x='c', y=['a', 'b'], "
        "labels={'variable': 'Series', 'value': 'Amount', 'c': 'Category'})"
    )
    assert result["success"] is True
    assert len(result["data"]) == 2
    assert result["layout"]["legend"]["title"]["text"] == "Series"
    assert result["layout"]["yaxis"]["title"]["text"] == "Amount"
    assert result["layout"]["xaxis"]["title"]["text"] == "Category"


def test_common_literal_presentation_options_render(chart_data):
    bars = chart(
        "px.bar(df, x='c', y='b', color='c', text_auto='.2f', "
        "category_orders={'c': ['second', 'first']}, "
        "color_discrete_map={'first': 'red', 'second': 'blue'}, "
        "hover_data={'a': False, 'b': ':.2f'})"
    )
    assert bars["success"] is True
    assert [trace["name"] for trace in bars["data"]] == ["second", "first"]
    assert [trace["marker"]["color"] for trace in bars["data"]] == ["blue", "red"]
    assert bars["data"][0]["texttemplate"] == "%{y:.2f}"
    assert "b=%{y:.2f}" in bars["data"][0]["hovertemplate"]
    scatter = chart("px.scatter(df, x='a', y='b', color='a', color_continuous_scale='Viridis')")
    assert scatter["success"] is True
    assert scatter["layout"]["coloraxis"]["colorscale"][0] == [0.0, "#440154"]


@pytest.mark.parametrize("expression,trace", [
    ("px.density_heatmap(df, x='a', y='b', text_auto=True)", "histogram2d"),
    ("px.treemap(df, path=['c'], values='b')", "treemap"),
    ("px.funnel(df, x='b', y='c')", "funnel"),
    ("px.timeline(df, x_start='a', x_end='b', y='c')", "bar"),
])
def test_additional_closed_chart_functions_render(chart_data, expression, trace):
    result = chart(expression)
    assert result["success"] is True
    assert result["data"][0]["type"] == trace


@pytest.mark.parametrize("axes", [
    {},
    {"x": ["North", "South"]},
    {"y": ["Q1", "Q2"]},
    {"x": [10, 20], "y": [-2.5, 0.5]},
    {"x": ["North", "South"], "y": ["Q1", "Q2"]},
])
def test_image_chart_renders_numeric_query_results(monkeypatch, axes):
    frame = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
    monkeypatch.setattr(server.db_client, "execute", lambda *args, **kwargs: ResultSet(
        success=True, execution_time=0, column_names=list(frame.columns),
        rows=frame.values.tolist(), pandas=frame,
    ))
    options = ", ".join(f"{name}={value!r}" for name, value in axes.items())
    result = chart(f"px.imshow(df, color_continuous_scale='Viridis', {options})")
    assert result["success"] is True
    assert result["data"][0]["type"] == "heatmap"
    for name, value in axes.items():
        assert result["data"][0][name] == value
