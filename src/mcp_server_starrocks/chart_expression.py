"""A closed chart description language; caller text is never executed."""

import ast
import math
from inspect import signature

import plotly.express as px

_CHARTS = {
    "scatter": px.scatter,
    "line": px.line,
    "bar": px.bar,
    "histogram": px.histogram,
    "box": px.box,
    "pie": px.pie,
    "area": px.area,
    "density_heatmap": px.density_heatmap,
    "treemap": px.treemap,
    "funnel": px.funnel,
    "timeline": px.timeline,
    "imshow": px.imshow,
}
_COLUMN_OPTIONS = {
    "x",
    "y",
    "color",
    "size",
    "symbol",
    "line_dash",
    "line_group",
    "names",
    "values",
    "facet_row",
    "facet_col",
    "hover_name",
    "text",
    "error_x",
    "error_x_minus",
    "error_y",
    "error_y_minus",
    "animation_frame",
    "animation_group",
    "pattern_shape",
    "x_start",
    "x_end",
    "ids",
    "parents",
}
_COLUMN_LIST_OPTIONS = {"hover_data", "custom_data", "path"}
_STRING_OPTIONS = {
    "title",
    "template",
    "orientation",
    "barmode",
    "barnorm",
    "histnorm",
    "histfunc",
    "points",
    "boxmode",
    "marginal_x",
    "marginal_y",
    "trendline",
    "line_shape",
    "render_mode",
    "origin",
    "aspect",
    "branchvalues",
}
_BOOL_OPTIONS = {"log_x", "log_y", "markers", "notched", "cumulative"}
_INTEGER_OPTIONS = {"width", "height", "nbins", "facet_col_wrap"}
_NUMBER_OPTIONS = {
    "opacity",
    "size_max",
    "hole",
    "facet_row_spacing",
    "facet_col_spacing",
    "zmin",
    "zmax",
    "color_continuous_midpoint",
}
_STRING_LIST_OPTIONS = {
    "color_discrete_sequence",
    "symbol_sequence",
    "line_dash_sequence",
    "pattern_shape_sequence",
}

_OPTION_KINDS = {
    **dict.fromkeys(_COLUMN_OPTIONS, "column"),
    **dict.fromkeys({"x", "y"}, "column_or_columns"),
    **dict.fromkeys(_COLUMN_LIST_OPTIONS, "columns"),
    **dict.fromkeys(_STRING_OPTIONS, "string"),
    **dict.fromkeys(_BOOL_OPTIONS, "boolean"),
    **dict.fromkeys(_INTEGER_OPTIONS, "integer"),
    **dict.fromkeys(_NUMBER_OPTIONS, "number"),
    **dict.fromkeys(_STRING_LIST_OPTIONS, "strings"),
    **dict.fromkeys({"range_x", "range_y"}, "range"),
    **{name: name for name in (
        "text_auto", "color_continuous_scale", "category_orders",
        "color_discrete_map", "hover_data", "labels",
    )},
}
_CHART_SCHEMAS = {
    function: {name: kind for name, kind in _OPTION_KINDS.items()
               if name in signature(function).parameters}
    for function in _CHARTS.values()
}
_CHART_SCHEMAS[px.imshow].update(x="coordinates", y="coordinates")


class InvalidChartExpression(ValueError):
    def __init__(self, option=None):
        super().__init__(
            f"Invalid chart option: {option}." if option else "Invalid chart expression."
        )


def _literal(node):
    if isinstance(node, ast.Constant) and type(node.value) in (
        str,
        int,
        float,
        bool,
        type(None),
    ):
        if type(node.value) is float and not math.isfinite(node.value):
            raise InvalidChartExpression()
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.USub, ast.UAdd))
        and isinstance(node.operand, ast.Constant)
        and type(node.operand.value) in (int, float)
    ):
        value = _literal(node.operand)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(item) for item in node.elts]
    if isinstance(node, ast.Dict):
        result = {}
        for key_node, value_node in zip(node.keys, node.values):
            key = _literal(key_node)
            if type(key) is not str or key in result:
                raise InvalidChartExpression()
            result[key] = _literal(value_node)
        return result
    raise InvalidChartExpression()


def _valid_option(kind, value):
    if kind == "coordinates":
        return type(value) is list and bool(value) and all(
            type(item) in (str, int, float) for item in value
        )
    if kind == "text_auto":
        return type(value) in (bool, str)
    if kind == "color_continuous_scale":
        return type(value) is str or (
            type(value) is list
            and bool(value)
            and (
                all(type(item) is str for item in value)
                or all(
                    type(item) is list
                    and len(item) == 2
                    and type(item[0]) in (int, float)
                    and 0 <= item[0] <= 1
                    and type(item[1]) is str
                    for item in value
                )
            )
        )
    if kind == "category_orders":
        return type(value) is dict and all(
            type(items) is list
            and all(type(item) in (str, int, float, bool) for item in items)
            for items in value.values()
        )
    if kind == "color_discrete_map":
        return value == "identity" or (
            type(value) is dict
            and all(type(color) is str for color in value.values())
        )
    if kind == "hover_data" and type(value) is dict:
        return all(type(item) in (bool, str) for item in value.values())
    if kind in {"column", "column_or_columns"}:
        if kind == "column_or_columns" and type(value) is list:
            return bool(value) and all(type(item) is str for item in value)
        return type(value) is str
    if kind in {"columns", "strings", "hover_data"}:
        return type(value) is list and all(type(item) is str for item in value)
    if kind == "string":
        return type(value) is str
    if kind == "boolean":
        return type(value) is bool
    if kind == "integer":
        return type(value) is int and value > 0
    if kind == "number":
        return type(value) in (int, float)
    if kind == "range":
        return (
            type(value) is list
            and len(value) == 2
            and all(type(item) in (str, int, float) for item in value)
        )
    if kind == "labels":
        return type(value) is dict and all(
            type(label) is str for label in value.values()
        )
    return False


def parse_chart_expression(expression):
    """Return a fixed callable and literal options, without accessing caller objects."""
    if len(expression) > 10000:
        raise InvalidChartExpression()
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError, RecursionError):
        raise InvalidChartExpression() from None
    if sum(1 for _ in ast.walk(tree)) > 1000:
        raise InvalidChartExpression()
    call = tree.body
    if not (
        isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "px"
        and call.func.attr in _CHARTS
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id == "df"
    ):
        raise InvalidChartExpression()
    function = _CHARTS[call.func.attr]
    schema = _CHART_SCHEMAS[function]
    options = {}
    for keyword in call.keywords:
        name = keyword.arg
        if (
            name is None
            or name in options
            or name not in schema
        ):
            raise InvalidChartExpression(name)
        value = _literal(keyword.value)
        if not _valid_option(schema[name], value):
            raise InvalidChartExpression(name)
        options[name] = value
    return function, options


def validate_chart_columns(function, options, frame):
    """Validate data references and image coordinates for the selected function."""
    schema = _CHART_SCHEMAS[function]
    for name, value in options.items():
        kind = schema[name]
        if kind == "coordinates":
            dimension = 1 if name == "x" else 0
            if len(value) != frame.shape[dimension]:
                raise InvalidChartExpression(name)
        elif kind in {"column", "column_or_columns", "columns", "hover_data"}:
            references = [value] if type(value) is str else value
            if any(column not in frame.columns for column in references):
                raise InvalidChartExpression()
