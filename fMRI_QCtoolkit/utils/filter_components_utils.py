"""
Sidebar filter components for the dashboards
"""

import math
from decimal import Decimal

import dash
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
# Up from where the slider puts its marks: below the track before Dash 4, at it from Dash 4 on
THRESHOLD_LIFT = '-24px' if int(dash.__version__.split('.')[0]) >= 4 else '-34px'
_LIFTED = {'bottom': 'auto'}
# Dash 4 only: the tick it draws above a mark's label goes under a lifted label, pointing down to the track;
# and its wide gap after each inline tick box, which pushes NA onto a second line, gives way to labelStyle's
SIDEBAR_CSS = ('.dash-slider-mark[style*="bottom: auto"]::before '
               '{ bottom: auto; top: 100%; margin-bottom: 0; margin-top: 2px; } '
               '.dash-slider-mark[style*="translateX(-100%)"]::before { left: 100%; } '
               '.dash-slider-mark[style*="translateX(0%)"]::before { left: 0; } '
               '.dash-options-list-option.dash-checklist-inline { margin-right: 0; }')
# With two thresholds, the lower label ends at its tick and the higher one starts at its tick, so they never overlap
_OUTWARD = ('translateX(-100%)', 'translateX(0%)')
# The dashboard's blue, muted so the controls do not outshine the data
ACCENT = '#5289bd'
# Component types of the sidebar's per-metric filters; the column names the instance
RANGE = 'metric-range'
STATUS = 'metric-status'
_NOTE_STYLE = {'font-size': '14px', 'color': '#555'}


def _clean(x):
    return float(f"{x:.12g}")


def slider_bounds(values, metric):
    """(min, max, step) of a metric's slider: covers the finite values and the threshold lines."""
    values = pd.to_numeric(pd.Series(values), errors="coerce").replace([math.inf, -math.inf], math.nan).dropna()
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
    if not metric.rated:
        return [{'label': 'Include NA', 'value': 'NA'}]
    return [{'label': tier, 'value': tier} for tier in rated_tiers(metric.rules, metric.otherwise) + ['NA']]


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


def _mark(value, color=None, transform=None):
    """A slider mark; a threshold (coloured) is lifted above the track, clear of the value boxes below it."""
    label = f"{value:g}"
    if not color:
        return label
    # bottom: auto, or Dash 4's own bottom: 0 keeps the mark below the track
    style = {'color': color, 'top': THRESHOLD_LIFT, **_LIFTED}
    return {'label': label, 'style': {**style, 'transform': transform} if transform else style}


def create_metric_filter(metric, bounds):
    """Range slider plus a status checklist; 'bad' is unticked by default."""
    lo, hi, step = bounds
    marks = {mark_key(lo): _mark(lo), mark_key(hi): _mark(hi)}
    thresholds = sorted(((value, tier) for tier, (op, value) in metric.rules.items()
                         if op in UPWARD | DOWNWARD and lo <= value <= hi), key=lambda item: item[0])
    distinct = len({value for value, _ in thresholds}) == 2
    transforms = _OUTWARD if distinct else (None,) * len(thresholds)
    for (value, tier), transform in zip(thresholds, transforms):
        marks[mark_key(value)] = _mark(value, _MARK_COLORS[tier], transform)
    # Room above the track for the threshold labels, also when a threshold is an end of the slider
    lifted = any(isinstance(mark, dict) for mark in marks.values())
    return html.Div([
        html.Label(metric.label, style={'font-weight': 'bold', 'display': 'block',
                                        'margin-bottom': '26px' if lifted else '0'}),
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
            labelStyle={'margin-right': '8px', 'white-space': 'nowrap'},
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
        if metric.rated and metric.entry not in lines:
            tiers = [f"{tier} {format_rule(metric.rules[tier], symbols=True)}"
                     for tier in RULE_TIERS if tier in metric.rules]
            if metric.otherwise:
                tiers.append(f"otherwise {metric.otherwise}" if tiers else f"all {metric.otherwise}")
            lines[metric.entry] = f"{metric.entry_label}: {', '.join(tiers)}"
    if not lines:
        return html.P("No thresholds set, so no run is hidden.", style=_NOTE_STYLE)
    return html.Div([
        html.P("Runs rated bad are hidden at first; tick 'bad' to show them.",
               style=_NOTE_STYLE),
        html.Ul([html.Li(line) for line in lines.values()],
                style={**_NOTE_STYLE, 'padding-left': '18px', 'margin-top': '0'})
    ])
