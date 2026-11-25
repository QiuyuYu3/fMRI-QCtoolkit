"""
Sidebar filter components for the dashboards
"""

import math
from decimal import Decimal

from dash import dcc, html
import pandas as pd

from .status import DOWNWARD, RULE_TIERS, UPWARD, format_rule, rated_tiers

RATING_OPTIONS = [
    {'label': 'Good', 'value': 'good'},
    {'label': 'Other', 'value': 'other'},
    {'label': 'Bad', 'value': 'bad'},
    {'label': 'NA', 'value': 'NA'},
]
_MARK_COLORS = {'good': '#3B7D23', 'bad': '#C0392B'}
# The dashboard's blue, muted so the controls do not outshine the data
ACCENT = '#5289bd'
# Component types of the sidebar's per-metric filters; the column names the instance
RANGE = 'metric-range'
STATUS = 'metric-status'
_NOTE_STYLE = {'font-size': '14px', 'color': '#555'}


def _clean(x):
    return float(f"{x:.12g}")


def slider_bounds(values, metric):
    """(min, max, step) of a metric's slider: covers the data and the threshold lines."""
    values = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    points = [value for op, value in metric.rules.values() if op in UPWARD | DOWNWARD]
    if not values.empty:
        points += [float(values.min()), float(values.max())]
    lo, hi = (min(points), max(points)) if points else (0.0, 1.0)
    if hi <= lo:
        hi = lo + 1
    step = metric.step or 10 ** (math.floor(math.log10(hi - lo)) - 2)
    # _clean first, or 0.2 / 0.001 = 200.00000000000003 would round up a whole step
    return (_clean(math.floor(_clean(lo / step)) * step),
            _clean(math.ceil(_clean(hi / step)) * step), step)


def status_options(metric):
    if not metric.rules:
        return [{'label': 'Include NA', 'value': 'NA'}]
    return [{'label': tier, 'value': tier} for tier in rated_tiers(metric.rules) + ['NA']]


def default_statuses(metric):
    return [o['value'] for o in status_options(metric) if o['value'] != 'bad']


def mark_key(value):
    """A number as JavaScript prints it (15, not 15.0); Dash 2 drops slider marks keyed any other way."""
    value = float(value)
    if value == 0:
        return "0"
    if 1e-6 <= abs(value) < 1e21:
        text = format(Decimal(repr(value)), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    mantissa, exponent = repr(value).split("e")
    return f"{mantissa.removesuffix('.0')}e{int(exponent):+d}"


def _mark(value, color=None):
    label = f"{value:g}"
    return {'label': label, 'style': {'color': color}} if color else label


def create_metric_filter(metric, bounds):
    """Range slider plus a status checklist; 'bad' is unticked by default."""
    lo, hi, step = bounds
    marks = {mark_key(lo): _mark(lo), mark_key(hi): _mark(hi)}
    for tier, (op, value) in metric.rules.items():
        if op in UPWARD | DOWNWARD and lo <= value <= hi:
            marks[mark_key(value)] = _mark(value, _MARK_COLORS[tier])
    return html.Div([
        html.Label(metric.label, style={'font-weight': 'bold'}),
        dcc.RangeSlider(
            id={'type': RANGE, 'column': metric.column},
            min=lo,
            max=hi,
            value=[lo, hi],
            step=step,
            marks=marks,
            tooltip={'placement': 'bottom', 'always_visible': True}
        ),
        dcc.Checklist(
            id={'type': STATUS, 'column': metric.column},
            options=status_options(metric),
            value=default_statuses(metric),
            inline=True,
            inputStyle={'margin-right': '3px'},
            labelStyle={'margin-right': '10px'},
            # Clears the slider's value boxes, which hang below the track (taller from Dash 4 on)
            style={'margin-top': '25px', 'font-size': '12px'}
        )
    ], style={'margin-bottom': '15px'})


def create_qualitative_dropdown(group):
    """Create a qualitative variable dropdown component."""
    return html.Div([
        html.Label(group.replace('_', ' ').title(), style={'font-weight': 'bold'}),
        dcc.Dropdown(
            id=f'{group}_dropdown',
            options=RATING_OPTIONS,
            value=[o['value'] for o in RATING_OPTIONS],
            multi=True,
            style={'font-size': '12px'}
        )
    ], style={'margin-bottom': '10px'})


def create_rules_summary(metrics):
    """The thresholds in force, one line per config entry, shown above the filters."""
    lines = {}
    for metric in metrics:
        if metric.rules and metric.entry not in lines:
            tiers = [f"{tier} {format_rule(metric.rules[tier], symbols=True)}"
                     for tier in RULE_TIERS if tier in metric.rules]
            lines[metric.entry] = f"{metric.entry_label}: {', '.join(tiers)}"
    if not lines:
        return html.P("No thresholds are set, so no run is hidden by default.", style=_NOTE_STYLE)
    return html.Div([
        html.P("Runs rated bad on any of these are hidden by default; tick 'bad' under a metric to show them.",
               style=_NOTE_STYLE),
        html.Ul([html.Li(line) for line in lines.values()],
                style={**_NOTE_STYLE, 'padding-left': '18px', 'margin-top': '0'})
    ])
