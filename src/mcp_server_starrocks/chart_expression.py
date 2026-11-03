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
}
_COLUMN_LIST_OPTIONS = {"hover_data", "custom_data"}
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
}
_BOOL_OPTIONS = {"log_x", "log_y", "markers", "notched", "cumulative"}
_INTEGER_OPTIONS = {"width", "height", "nbins", "facet_col_wrap"}
_NUMBER_OPTIONS = {
    "opacity",
    "size_max",
    "hole",
    "facet_row_spacing",
    "facet_col_spacing",
}
_STRING_LIST_OPTIONS = {
    "color_discrete_sequence",
    "symbol_sequence",
    "line_dash_sequence",
    "pattern_shape_sequence",
}


class InvalidChartExpression(ValueError):
    def __init__(self):
        super().__init__("Invalid chart expression.")


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


def _valid_option(name, value):
    if name in _COLUMN_OPTIONS:
        if name in {"x", "y"} and type(value) is list:
            return bool(value) and all(type(item) is str for item in value)
        return type(value) is str
    if name in _COLUMN_LIST_OPTIONS | _STRING_LIST_OPTIONS:
        return type(value) is list and all(type(item) is str for item in value)
    if name in _STRING_OPTIONS:
        return type(value) is str
    if name in _BOOL_OPTIONS:
        return type(value) is bool
    if name in _INTEGER_OPTIONS:
        return type(value) is int and value > 0
    if name in _NUMBER_OPTIONS:
        return type(value) in (int, float)
    if name in {"range_x", "range_y"}:
        return (
            type(value) is list
            and len(value) == 2
            and all(type(item) in (str, int, float) for item in value)
        )
    if name == "labels":
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
    options = {}
    for keyword in call.keywords:
        name = keyword.arg
        if (
            name is None
            or name in options
            or name not in signature(function).parameters
        ):
            raise InvalidChartExpression()
        value = _literal(keyword.value)
        if not _valid_option(name, value):
            raise InvalidChartExpression()
        options[name] = value
    return function, options


def validate_chart_columns(options, columns):
    """All data references must name columns in this query's result."""
    for name, value in options.items():
        if name in _COLUMN_OPTIONS | _COLUMN_LIST_OPTIONS | {"labels"}:
            references = [value] if type(value) is str else value
            if any(column not in columns for column in references):
                raise InvalidChartExpression()
