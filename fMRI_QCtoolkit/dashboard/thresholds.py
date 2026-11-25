"""
Thresholds tab: edit the dashboard config, preview what it would hide, and save it to the --config file
"""

import time

import numpy as np
import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from .config import (ID_COLUMNS, ConfigError, Metric, backup_path, default_config_path, load_config,
                     parse_entry, resolve_metrics, save_config)
from ..utils.filter_components_utils import ACCENT, slider_bounds
from ..utils.status import assign_status, format_number, get_status_colors, get_status_mapping

THRESHOLDS_TAB = 'thresholds-tab'
FIELDS = ('label', 'other-op', 'other-value', 'bad-op', 'bad-value', 'step')
OPERATORS = ['>', '>=', '<', '<=', '==', '!=']
# An explicit 'none' choice instead of a clear button, which leaves no room for the value in a narrow column
OPERATOR_OPTIONS = [{'label': 'none', 'value': ''}] + [{'label': op, 'value': op} for op in OPERATORS]
TIERS = ('good', 'other', 'bad', 'NA')
TIER_COLORS = {tier: get_status_colors()[number] for tier, number in get_status_mapping().items()}
# Seconds of no typing before a box is sent, so the preview does not chase every keystroke
TYPING_PAUSE_S = 0.5
GRID = {'display': 'grid', 'gap': '6px', 'align-items': 'center',
        'grid-template-columns': '150px minmax(120px, 1fr) 84px 80px 84px 80px 130px 230px 90px',
        'font-size': '13px'}
_BOX = {'width': '100%', 'box-sizing': 'border-box', 'font-size': '13px'}
_NOTE_STYLE = {'font-size': '12px', 'color': '#666'}
_RANK = {'NA': 0, 'good': 1, 'other': 2, 'bad': 3}


def new_row(column):
    return {'key': column, 'label': column, 'other-op': None, 'other-value': None,
            'bad-op': None, 'bad-value': None, 'step': None}


def config_rows(config):
    rows = []
    for key, metric in config.items():
        row = new_row(key)
        row.update(label=metric.entry_label, step=metric.step)
        for tier, (op, value) in metric.rules.items():
            row[f'{tier}-op'], row[f'{tier}-value'] = op, value
        rows.append(row)
    return rows


def form_rows(keys, *fields):
    """Rows of the form from the per-field value lists that the pattern-matching callbacks receive."""
    return [dict(zip(('key',) + FIELDS, values)) for values in zip(keys, *fields)]


def row_entry(row):
    """A form row as a config entry; an operator or number left on its own is passed on for parse_entry to reject."""
    entry = {}
    label = (row.get('label') or '').strip()
    if label:
        entry['label'] = label
    for tier in ('other', 'bad'):
        op, value = row.get(f'{tier}-op'), row.get(f'{tier}-value')
        if op or value is not None:
            entry[tier] = f"{op or ''} {'' if value is None else format_number(value)}".strip()
    if row.get('step') is not None:
        entry['step'] = row['step']
    return entry


def form_raw(rows):
    return {'metrics': {row['key']: row_entry(row) for row in rows}}


def worst_status(statuses):
    """Per run, the worst status across several columns: bad, then other, then good; NA only if all are NA."""
    ranks = pd.concat([s.map(_RANK) for s in statuses], axis=1).max(axis=1)
    return ranks.map({rank: tier for tier, rank in _RANK.items()})


def _keys(items):
    return [item['id']['key'] for item in items]


def _note(text):
    return html.Span(text, style=_NOTE_STYLE)


def _count_chips(status, rules, n_columns=None):
    counts = status.value_counts()
    tiers = [t for t in TIERS if t in ('good', 'NA') or t in rules]
    chips = [html.Span(f"{tier} {int(counts.get(tier, 0))}",
                       style={'background-color': TIER_COLORS[tier], 'padding': '1px 6px',
                              'border-radius': '3px', 'margin-right': '4px', 'white-space': 'nowrap'})
             for tier in tiers]
    if n_columns is not None:
        chips.append(_note(f"worst of {n_columns} columns"))
    return html.Span(chips, style={'font-size': '12px'})


def _message(text, ok=False):
    return html.Div(text, style={'color': '#1e7e34' if ok else '#C0392B', 'margin-top': '8px',
                                 'white-space': 'pre-wrap'})


class ThresholdsTab:
    """The Thresholds tab of a dashboard; it reads and replaces the dashboard's config."""

    def __init__(self, dashboard):
        self.dashboard = dashboard

    def _columns(self):
        return list(self.dashboard.processor.get_data().columns)

    def addable_columns(self, keys):
        """Numeric columns of the data that no row of the form covers yet."""
        df = self.dashboard.processor.get_data()
        covered = {m.column for m in resolve_metrics({k: Metric(k, k, {}) for k in keys}, list(df.columns))}
        skip = {*ID_COLUMNS, *self.dashboard.processor.checkbox_groups} | covered
        return [c for c in df.columns if c not in skip
                and pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])]

    def _auto_step(self, row):
        try:
            rules = parse_entry(row['key'], row_entry(row)).rules
        except ConfigError:
            rules = {}
        metrics = resolve_metrics({row['key']: Metric(row['key'], row['key'], rules)}, self._columns())
        if not metrics:
            return None
        return format_number(slider_bounds(self.dashboard.numeric(metrics[0].column), metrics[0])[2])

    def render_row(self, row):
        key = row['key']

        def ident(kind):
            return {'type': f'thr-{kind}', 'key': key}

        def operator(tier):
            return dcc.Dropdown(id=ident(f'{tier}-op'), options=OPERATOR_OPTIONS, value=row[f'{tier}-op'] or '',
                                clearable=False, searchable=False, style={'font-size': '13px'})

        def number(field, placeholder=None):
            return dcc.Input(id=ident(field), type='number', step='any', value=row[field], placeholder=placeholder,
                             debounce=TYPING_PAUSE_S, style=_BOX)

        def button(kind, text, title):
            return html.Button(text, id=ident(kind), n_clicks=0, title=title,
                               style={'padding': '2px 7px', 'margin-left': '2px', 'cursor': 'pointer'})

        return html.Div([
            html.Div([
                html.Code(key, style={'overflow-wrap': 'anywhere'}),
                dcc.Input(id=ident('label'), type='text', value=row['label'], debounce=TYPING_PAUSE_S, style=_BOX),
                operator('other'), number('other-value'),
                operator('bad'), number('bad-value'),
                number('step', self._auto_step(row)),
                html.Div(id=ident('counts')),
                html.Div([button('up', '↑', 'Move up'), button('down', '↓', 'Move down'),
                          button('delete', '✕', 'Remove this metric')], style={'white-space': 'nowrap'}),
            ], style=GRID),
            html.Div(id=ident('error'), style={'color': '#C0392B', 'font-size': '12px'}),
        ], style={'padding': '4px 0', 'border-bottom': '1px solid #e9ecef'})

    def _file_note(self):
        d = self.dashboard
        if d.save_path is None:
            return html.P(["These are the package's default thresholds and cannot be saved from here. "
                           "To save changes, start the dashboard again with ", html.Code("--config FILE"),
                           " added to the command; the file need not exist yet. Until then you can still "
                           "try thresholds here and see what they would hide."],
                          style={**_NOTE_STYLE, 'color': '#8a6d00'})
        lines = [html.Span(["Saving to ", html.Code(str(d.save_path)),
                            "" if d.save_path.exists() else " (not created yet; Save creates it)."])]
        if d.last_saved:
            saved_at, backed_up = d.last_saved
            lines.append(html.Br())
            lines.append(html.Span(f"Saved at {saved_at}." + (
                f" The previous version is in {backup_path(d.save_path).name}." if backed_up else "")))
        return html.P(lines, style=_NOTE_STYLE)

    def layout(self):
        rows = config_rows(self.dashboard.config)
        heading = [html.B("Metric"), html.B("Label"), html.B("Other", style={'grid-column': 'span 2'}),
                   html.B("Bad", style={'grid-column': 'span 2'}), html.B("Step"),
                   html.B("Runs with these thresholds"), html.Span()]
        button_style = {'border': 'none', 'padding': '8px 16px', 'border-radius': '4px', 'cursor': 'pointer',
                        'margin-right': '8px'}
        return html.Div([
            html.P("A run is bad if it meets the bad rule, otherwise other if it meets the other rule, "
                   "otherwise good; a missing value is NA. Leave an operator empty for no rule, and both "
                   "empty for a metric that is filtered but not rated. Runs rated bad on any metric are "
                   "hidden when the dashboard opens. Step is the slider's step; left empty, it is the one "
                   "shown in gray. The rows are listed in the order of the sidebar.",
                   style=_NOTE_STYLE),
            self._file_note(),
            html.Div(id='thr-summary', style={'font-weight': 'bold', 'margin': '10px 0'}),
            html.Div(heading, style={**GRID, 'font-size': '13px', 'padding-bottom': '4px',
                                     'border-bottom': '2px solid #dee2e6'}),
            html.Div([self.render_row(row) for row in rows], id='thr-rows'),
            dcc.Dropdown(id='thr-add', options=self.addable_columns([r['key'] for r in rows]), value=None,
                         placeholder="Add a metric from df_final.csv", style={'width': '340px', 'margin': '10px 0'}),
            html.Div([
                html.Button("Save", id='thr-save', n_clicks=0,
                            style={**button_style, 'background-color': ACCENT, 'color': 'white'}),
                html.Button("Discard changes", id='thr-discard', n_clicks=0,
                            style={**button_style, 'background-color': '#6c757d', 'color': 'white'}),
                html.Button("Use defaults", id='thr-defaults', n_clicks=0,
                            title="Fill in the package's default thresholds; nothing is saved until you press Save",
                            style={**button_style, 'background-color': '#6c757d', 'color': 'white'}),
                html.Span(id='thr-unsaved', style={'color': '#8a6d00'}),
            ], style={'margin-top': '10px'}),
            html.Div(id='thr-message'),
            dcc.Store(id='thr-saved'),
            html.Div(id='thr-reloading', style={'display': 'none'}),
        ], style={'padding': '15px', 'overflow-x': 'auto'})

    def preview(self, rows):
        """Per-row counts and errors, the summary line, whether Save is off, the unsaved note, and the add options."""
        d = self.dashboard
        df = d.processor.get_data()
        parsed, errors = {}, {}
        for row in rows:
            try:
                parsed[row['key']] = parse_entry(row['key'], row_entry(row))
            except ConfigError as e:
                errors[row['key']] = str(e)
        by_entry = {}
        for metric in resolve_metrics(parsed, list(df.columns)):
            by_entry.setdefault(metric.entry, []).append(metric)

        hidden = np.zeros(len(df), dtype=bool)
        cells = []
        for row in rows:
            key, metrics = row['key'], by_entry.get(row['key'], [])
            if key in errors:
                cells.append(None)
            elif not metrics:
                cells.append(_note("not in the data"))
            elif not parsed[key].rules:
                cells.append(_note("no thresholds"))
            else:
                status = worst_status([assign_status(d.numeric(m.column), m.rules) for m in metrics])
                hidden |= (status == 'bad').to_numpy()
                cells.append(_count_chips(status, parsed[key].rules, len(metrics) if '*' in key else None))

        changed = bool(errors) or list(parsed.items()) != list(d.config.items())
        if rows:
            now = len(df) - int(d.status.eq('bad').any(axis=1).sum())
            summary = (f"With these thresholds, {len(df) - int(hidden.sum())} of {len(df)} runs are shown "
                       f"when the dashboard opens (now {now}).")
            if errors:
                summary += " Rows with an error are left out until they are fixed."
        else:
            summary = "Add at least one metric."
        save_off = d.save_path is None or bool(errors) or not rows or not changed
        options = self.addable_columns([row['key'] for row in rows])
        return (cells, [errors.get(row['key']) for row in rows], summary, save_off,
                "Unsaved changes" if changed else "", options)

    def edit(self, rows, trigger, clicked, added):
        """The rows after an add, move, remove, discard or defaults action."""
        keys = [row['key'] for row in rows]
        if trigger == 'thr-add':
            if not added or added in keys:
                raise PreventUpdate
            return rows + [new_row(added)]
        if trigger == 'thr-discard':
            return config_rows(self.dashboard.config)
        if trigger == 'thr-defaults':
            return config_rows(load_config(default_config_path(self.dashboard.PIPELINE)))
        # Freshly drawn buttons report n_clicks 0, which is not a click
        if isinstance(trigger, dict) and clicked and trigger.get('key') in keys:
            i = keys.index(trigger['key'])
            if trigger['type'] == 'thr-delete':
                return rows[:i] + rows[i + 1:]
            j = i - 1 if trigger['type'] == 'thr-up' else i + 1
            if 0 <= j < len(rows):
                rows[i], rows[j] = rows[j], rows[i]
                return rows
        raise PreventUpdate

    def save(self, rows, version):
        """Write the form to the --config file and rate the runs with it; returns (message, saved)."""
        d = self.dashboard
        if d.save_path is None:
            return "Nothing was saved: start the dashboard with --config FILE to save thresholds.", False
        with d.save_lock:
            if version != d.config_version:
                return ("Nothing was saved: the thresholds were saved from another tab or window after this "
                        "page opened. Reload the page, then make your changes again."), False
            existed = d.save_path.exists()
            try:
                config = save_config(d.save_path, form_raw(rows))
            except ConfigError as e:
                return f"Nothing was saved: {e}", False
            except OSError as e:
                return f"Could not write {d.save_path}: {e}", False
            d.apply_config(config)
            d.config_path = d.save_path
            d.config_version += 1
            d.last_saved = (time.strftime('%H:%M:%S'), existed)
        return "Saved. Reloading the page…", True

    def register(self, app):
        field_states = [State({'type': f'thr-{f}', 'key': ALL}, 'value') for f in FIELDS]

        @app.callback(
            [Output('thr-rows', 'children'), Output('thr-add', 'value')],
            [Input('thr-add', 'value'),
             Input({'type': 'thr-up', 'key': ALL}, 'n_clicks'),
             Input({'type': 'thr-down', 'key': ALL}, 'n_clicks'),
             Input({'type': 'thr-delete', 'key': ALL}, 'n_clicks'),
             Input('thr-discard', 'n_clicks'),
             Input('thr-defaults', 'n_clicks')],
            field_states,
            prevent_initial_call=True
        )
        def edit_rows(added, _up, _down, _delete, _discard, _defaults, *fields):
            rows = form_rows(_keys(ctx.states_list[0]), *fields)
            clicked = ctx.triggered[0]['value'] if ctx.triggered else None
            rows = self.edit(rows, ctx.triggered_id, clicked, added)
            return [self.render_row(row) for row in rows], None

        @app.callback(
            [Output({'type': 'thr-counts', 'key': ALL}, 'children'),
             Output({'type': 'thr-error', 'key': ALL}, 'children'),
             Output('thr-summary', 'children'),
             Output('thr-save', 'disabled'),
             Output('thr-unsaved', 'children'),
             Output('thr-add', 'options')],
            [Input({'type': f'thr-{f}', 'key': ALL}, 'value') for f in FIELDS]
        )
        def update_preview(*fields):
            return self.preview(form_rows(_keys(ctx.inputs_list[0]), *fields))

        @app.callback(
            [Output('thr-message', 'children'), Output('thr-saved', 'data')],
            [Input('thr-save', 'n_clicks')],
            field_states + [State('config-version', 'data')],
            prevent_initial_call=True
        )
        def save(n_clicks, *args):
            if not n_clicks:
                raise PreventUpdate
            *fields, version = args
            message, saved = self.save(form_rows(_keys(ctx.states_list[0]), *fields), version)
            return _message(message, ok=saved), (self.dashboard.config_version if saved else no_update)

        # The page is rebuilt from the new thresholds; the tab it was on is kept by the tabs' persistence
        app.clientside_callback(
            "function(saved) { if (saved) { window.location.reload(); } return ''; }",
            Output('thr-reloading', 'children'),
            Input('thr-saved', 'data'),
            prevent_initial_call=True
        )
