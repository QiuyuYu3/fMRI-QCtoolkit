"""
Settings tab: the dashboard's metrics and their thresholds; preview what they would hide, save or download them
"""

import time

import numpy as np
import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

from .config import (ID_COLUMNS, ConfigError, Metric, backup_path, default_config_path, dump_config, load_config,
                     parse_config, parse_entry, parse_table_columns, resolve_metrics, save_config)
from ..utils.filter_components_utils import ACCENT, slider_bounds
from ..utils.status import (LEVELS, RULE_TIERS, assign_status, describe_levels, format_number, get_status_colors,
                            get_status_mapping, rated_tiers, rest_tier)

SETTINGS_TAB = 'settings-tab'
FIELDS = ('label', 'good-op', 'good-value', 'bad-op', 'bad-value', 'otherwise', 'step')
OPERATORS = ['>', '>=', '<', '<=', '==', '!=']
# A blank choice for "no rule" instead of a clear button, which leaves no room for the value in a narrow column
OPERATOR_OPTIONS = [{'label': '\u00a0', 'value': ''}] + [{'label': op, 'value': op} for op in OPERATORS]
LEVEL_OPTIONS = [{'label': level, 'value': level} for level in LEVELS]
TIER_COLORS = {tier: get_status_colors()[number] for tier, number in get_status_mapping().items()}
# Sent on Enter or on leaving the box, so that a button clicked right after typing gets the typed value
DEBOUNCE = True
GRID = {'display': 'grid', 'gap': '6px', 'align-items': 'center', 'font-size': '13px'}
_AREAS = ('metric', 'label', 'gop', 'gval', 'rest', 'bop', 'bval', 'step', 'runs', 'move')
# A row's ten cells, the header's too, are placed by area; below 1440 px a row takes two lines, which fit a laptop
SETTINGS_CSS = (
    ''.join(f'.thr-grid > :nth-child({i}) {{ grid-area: {area}; }} ' for i, area in enumerate(_AREAS, 1))
    + '.thr-grid { grid-template-columns: 116px minmax(140px, 260px) 80px 68px 94px 80px 68px 124px '
      'minmax(212px, 1fr) 90px; grid-template-areas: "' + ' '.join(_AREAS) + '"; } '
    + '@media (max-width: 1439px) { .thr-grid { grid-template-columns: 110px 80px 68px 94px 80px 68px '
      'minmax(124px, 1fr) 90px; grid-template-areas: "metric label label label label label step move" '
      '". gop gval rest bop bval runs runs"; } .thr-grid > :nth-child(8) { max-width: 124px; } }'
)
_BOX = {'width': '100%', 'box-sizing': 'border-box', 'font-size': '13px'}
_NOTE_STYLE = {'font-size': '12px', 'color': '#666'}
_TEXT_STYLE = {'font-size': '15px', 'color': '#555'}
_PANEL = {'background-color': '#f8f9fa', 'border': '1px solid #dee2e6', 'border-radius': '5px',
          'padding': '4px 15px', 'margin-bottom': '12px'}
_CHECK_GRID = {'display': 'grid', 'grid-template-columns': 'repeat(auto-fill, minmax(240px, 1fr))',
               'gap': '4px 16px', 'font-size': '15px'}
_SMALL_BUTTON = {'padding': '3px 10px', 'margin-right': '6px', 'cursor': 'pointer', 'font-size': '14px',
                 'border': '1px solid #6c757d', 'border-radius': '4px', 'background-color': 'white',
                 'color': '#495057'}
_BUTTON = {'border': 'none', 'padding': '8px 16px', 'border-radius': '4px', 'cursor': 'pointer', 'margin-right': '8px'}
SAVE_STYLE = {**_BUTTON, 'background-color': ACCENT, 'color': 'white'}
# Faded while there is nothing to save, yet it takes every click, which may bring a value typed just before
SAVE_IDLE_STYLE = {**SAVE_STYLE, 'opacity': 0.5}
NOTHING_TO_SAVE = "Nothing to save: no changes."
TABLE_BUTTONS = ('thr-table-all', 'thr-table-clear')
_RANK = {'NA': 0, 'good': 1, 'other': 2, 'bad': 3}


def new_row(column):
    return {'key': column, 'label': column, 'good-op': None, 'good-value': None,
            'bad-op': None, 'bad-value': None, 'otherwise': None, 'step': None}


def config_rows(metrics):
    rows = []
    for key, metric in metrics.items():
        row = new_row(key)
        row.update(label=metric.entry_label, step=metric.step, otherwise=metric.otherwise)
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
    for tier in RULE_TIERS:
        op, value = row.get(f'{tier}-op'), row.get(f'{tier}-value')
        if op or value is not None:
            entry[tier] = f"{op or ''} {'' if value is None else format_number(value)}".strip()
    # Written only where it differs from what the rules give anyway, so default entries read as before
    otherwise = row.get('otherwise')
    if otherwise and otherwise != default_rest(row):
        entry['otherwise'] = otherwise
    if row.get('step') is not None:
        entry['step'] = row['step']
    return entry


def default_rest(row):
    """The level a row's rules give the values that meet neither, before Otherwise is picked."""
    given = [tier for tier in RULE_TIERS if row.get(f'{tier}-op') or row.get(f'{tier}-value') is not None]
    return rest_tier(dict.fromkeys(given))


def form_raw(rows, table=()):
    raw = {'metrics': {row['key']: row_entry(row) for row in rows}}
    if table:
        raw['table_columns'] = list(table)
    return raw


def worst_status(statuses):
    """Per run, the worst status across several columns: bad, then other, then good; NA only if all are NA."""
    ranks = pd.concat([s.map(_RANK) for s in statuses], axis=1).max(axis=1)
    return ranks.map({rank: tier for tier, rank in _RANK.items()})


def _keys(items):
    return [item['id']['key'] for item in items]


def _note(text):
    return html.Span(text, style=_NOTE_STYLE)


def _count_chips(status, metric, n_columns=None):
    """Per level, a coloured chip with its number of runs, followed by the values the level covers."""
    counts = status.value_counts()
    ranges = describe_levels(metric.rules, metric.otherwise)
    items = [html.Span([html.Span(f"{tier} {int(counts.get(tier, 0))}",
                                  style={'background-color': TIER_COLORS[tier], 'padding': '1px 6px',
                                         'border-radius': '3px', 'margin-right': '4px'}),
                        *([ranges[tier]] if tier in ranges else [])],
                       style={'margin-right': '12px', 'white-space': 'nowrap'})
             for tier in rated_tiers(metric.rules, metric.otherwise) + ['NA']]
    if n_columns is not None:
        items.append(_note(f"worst of {n_columns} columns"))
    # Wraps rather than running under the row's buttons on a narrow screen
    return html.Span(items, style={'font-size': '12px', 'color': '#333', 'display': 'flex', 'flex-wrap': 'wrap',
                                   'row-gap': '2px'})


def _message(text, ok=False):
    return html.Div(text, style={'color': '#1e7e34' if ok else '#C0392B', 'margin-top': '8px',
                                 'white-space': 'pre-wrap'})


class SettingsTab:
    """The Settings tab of a dashboard; it reads and replaces the dashboard's config."""

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

    def table_options(self, keys):
        """Columns of the data that the table could show besides the IDs, the ratings and the form's metrics."""
        df = self.dashboard.processor.get_data()
        covered = {m.column for m in resolve_metrics({k: Metric(k, k, {}) for k in keys}, list(df.columns))}
        skip = {*ID_COLUMNS, *self.dashboard.processor.checkbox_groups} | covered
        return [c for c in df.columns if c not in skip]

    def in_data_order(self, table):
        """The table-only columns in df_final.csv order; any not in the data keep their order at the end."""
        columns, picked = self._columns(), set(table)
        return [c for c in columns if c in picked] + [c for c in table if c not in columns]

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
                             debounce=DEBOUNCE, style=_BOX)

        def button(kind, text, title):
            return html.Button(text, id=ident(kind), n_clicks=0, title=title,
                               style={'padding': '2px 7px', 'margin-left': '2px', 'cursor': 'pointer'})

        return html.Div([
            html.Div([
                html.Code(key, style={'overflow-wrap': 'anywhere'}),
                dcc.Input(id=ident('label'), type='text', value=row['label'], debounce=DEBOUNCE, style=_BOX),
                operator('good'), number('good-value'),
                # Empty follows the rules, shown in gray like the automatic step
                dcc.Dropdown(id=ident('otherwise'), options=LEVEL_OPTIONS, value=row['otherwise'],
                             placeholder=default_rest(row), clearable=False, searchable=False,
                             style={'font-size': '13px'}),
                operator('bad'), number('bad-value'),
                number('step', self._auto_step(row)),
                html.Div(id=ident('counts')),
                html.Div([button('up', '↑', 'Move up'), button('down', '↓', 'Move down'),
                          button('delete', '✕', 'Remove this metric')], style={'white-space': 'nowrap'}),
            ], className='thr-grid', style=GRID),
            html.Div(id=ident('error'), style={'color': '#C0392B', 'font-size': '12px'}),
        ], style={'padding': '4px 0', 'border-bottom': '1px solid #e9ecef'})

    def _file_note(self):
        d = self.dashboard
        if d.save_path is None:
            return html.P(["Save needs ", html.Code("--config FILE"), "; Download config works without it."],
                          style={**_TEXT_STYLE, 'color': '#8a6d00'})
        lines = [html.Span(["Saving to ", html.Code(str(d.save_path)),
                            "." if d.save_path.exists() else " (created on the first save)."])]
        if d.last_saved:
            saved_at, backed_up = d.last_saved
            lines.append(html.Br())
            lines.append(html.Span(f"Saved at {saved_at}." + (
                f" The previous version is in {backup_path(d.save_path).name}." if backed_up else "")))
        return html.P(lines, style=_TEXT_STYLE)

    def layout(self):
        config = self.dashboard.config
        rows = config_rows(config.metrics)
        keys = [r['key'] for r in rows]
        # Ten cells like a row's, so that both are laid out alike on any screen
        heading = [html.B("Metric"), html.B("Label"), html.B("Good"), html.Span(),
                   html.B("Otherwise", title="The level of a value that meets neither rule; gray is what the "
                                             "rules give"),
                   html.B("Bad"), html.Span(),
                   html.B("Step", title="The slider's step; left empty, the one shown in gray"),
                   html.B("Runs and values per level"), html.Span()]
        return html.Div([
            html.Div([
                html.P("Metrics appear in the sidebar and table in this order. A run that meets neither rule gets "
                       "the Otherwise level; leave an operator empty for no rule.", style=_TEXT_STYLE),
                self._file_note(),
            ], style=_PANEL),
            html.Div(id='thr-summary', style={'font-weight': 'bold', 'margin': '10px 0'}),
            html.Div(heading, className='thr-grid', style={**GRID, 'padding-bottom': '4px',
                                     'border-bottom': '2px solid #dee2e6'}),
            html.Div([self.render_row(row) for row in rows], id='thr-rows'),
            dcc.Dropdown(id='thr-add', options=self.addable_columns(keys), value=None,
                         placeholder="Add a metric from df_final.csv", style={'width': '340px', 'margin': '10px 0'}),
            html.Div([
                html.P([html.B("Table only: "), "extra table columns, without a slider or heatmap row."],
                       style={**_TEXT_STYLE, 'font-size': '16px', 'color': '#333', 'margin-bottom': '8px'}),
                html.Div([html.Button("Select all", id='thr-table-all', n_clicks=0, style=_SMALL_BUTTON),
                          html.Button("Clear", id='thr-table-clear', n_clicks=0, style=_SMALL_BUTTON)],
                         style={'margin-bottom': '8px'}),
                dcc.Checklist(id='thr-table', options=self.table_options(keys), value=list(config.table_columns),
                              style=_CHECK_GRID, inputStyle={'margin-right': '6px'},
                              labelStyle={'overflow-wrap': 'anywhere'}),
                html.Div(id='thr-table-error', style={'color': '#C0392B', 'font-size': '12px'}),
            ], style={'margin': '18px 0'}),
            html.Div([
                html.Button("Save", id='thr-save', n_clicks=0, style=SAVE_IDLE_STYLE),
                html.Button("Discard changes", id='thr-discard', n_clicks=0,
                            style={**_BUTTON, 'background-color': '#6c757d', 'color': 'white'}),
                html.Button("Use defaults", id='thr-defaults', n_clicks=0,
                            title="The package's defaults; saved only when you press Save",
                            style={**_BUTTON, 'background-color': '#6c757d', 'color': 'white'}),
                html.Button("Download config", id='thr-download-button', n_clicks=0,
                            title="Save these settings as a file on this computer",
                            style={**_BUTTON, 'background-color': 'white', 'color': ACCENT,
                                   'border': f'1px solid {ACCENT}'}),
                html.Span(id='thr-unsaved', style={'color': '#8a6d00'}),
            ], style={'margin-top': '10px'}),
            html.Div(id='thr-message'),
            dcc.Store(id='thr-saved'),
            dcc.Download(id='thr-download'),
            html.Div(id='thr-reloading', style={'display': 'none'}),
        ], style={'padding': '15px'})

    def preview(self, rows, table=()):
        """What the form's settings would do: counts and errors, the summary, button states, list options."""
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
            elif not parsed[key].rated:
                cells.append(_note("no thresholds"))
            else:
                status = worst_status([assign_status(d.numeric(m.column), m.rules, m.otherwise) for m in metrics])
                hidden |= (status == 'bad').to_numpy()
                cells.append(_count_chips(status, parsed[key], len(metrics) if '*' in key else None))

        keys = [row['key'] for row in rows]
        try:
            table_error = None
            parse_table_columns(list(table), keys)
        except ConfigError as e:
            table_error = str(e)
        state = d.state
        changed = (bool(errors) or bool(table_error) or list(parsed.items()) != list(state.config.metrics.items())
                   or set(table) != set(state.config.table_columns))
        invalid = bool(errors) or bool(table_error) or not rows
        if rows:
            now = len(df) - int(state.status.eq('bad').any(axis=1).sum())
            summary = f"Runs shown when the dashboard opens: {len(df) - int(hidden.sum())} of {len(df)} (now {now})."
            if errors:
                summary += " Rows with errors are left out."
        else:
            summary = "Add at least one metric."
        return {
            'counts': cells,
            'rest_defaults': [default_rest(row) for row in rows],
            'errors': [errors.get(row['key']) for row in rows],
            'summary': summary,
            'save_off': d.save_path is None,
            'save_style': SAVE_IDLE_STYLE if invalid or not changed else SAVE_STYLE,
            'download_off': invalid,
            'unsaved': "Unsaved changes" if changed else "",
            'options': self.addable_columns(keys),
            'table_options': self.table_options(keys),
            'table_error': table_error,
        }

    def config_file(self, rows, table=()):
        """(file name, text) of the form's settings as a config file; raises ConfigError if they are invalid."""
        raw = form_raw(rows, self.in_data_order(table))
        parse_config(raw)
        d = self.dashboard
        name = d.save_path.name if d.save_path else f"{d.PIPELINE}_config.json"
        return name, dump_config(raw)

    def edit(self, rows, trigger, clicked, added):
        """The rows after an add, move, remove, discard or defaults action."""
        keys = [row['key'] for row in rows]
        if trigger == 'thr-add':
            if not added or added in keys:
                raise PreventUpdate
            return rows + [new_row(added)]
        if trigger == 'thr-discard':
            return config_rows(self.dashboard.config.metrics)
        if trigger == 'thr-defaults':
            return config_rows(load_config(default_config_path(self.dashboard.PIPELINE)).metrics)
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

    def edit_table(self, table, trigger, added, keys):
        """The table-only columns after a button or row action; a column added as a metric leaves them."""
        if trigger == 'thr-table-all':
            return self.table_options(keys)
        if trigger == 'thr-table-clear':
            return []
        if trigger == 'thr-add':
            return [c for c in table if c != added]
        if trigger == 'thr-discard':
            return list(self.dashboard.config.table_columns)
        if trigger == 'thr-defaults':
            return list(load_config(default_config_path(self.dashboard.PIPELINE)).table_columns)
        return no_update

    def save(self, rows, version, table=()):
        """Write the form to the --config file and rate the runs with it; returns (message, saved)."""
        d = self.dashboard
        if d.save_path is None:
            return "Not saved: start the dashboard with --config FILE, or use Download config.", False
        with d.save_lock:
            if version != d.config_version:
                return "Not saved: settings were changed in another tab. Reload the page and try again.", False
            existed = d.save_path.exists()
            raw = form_raw(rows, self.in_data_order(table))
            try:
                # Writing the same settings again would replace the backup of the version before them
                if existed and parse_config(raw, source=str(d.save_path)) == d.config:
                    return NOTHING_TO_SAVE, False
                config = save_config(d.save_path, raw)
            except ConfigError as e:
                return f"Not saved: {e}", False
            except OSError as e:
                return (f"Could not write {d.save_path}: {e}. Use --config FILE in a folder you can write to, "
                        f"or Download config."), False
            d.apply_config(config)
            d.config_path = d.save_path
            d.config_version += 1
            d.last_saved = (time.strftime('%H:%M:%S'), existed)
        return "Saved. Reloading the page…", True

    def register(self, app):
        field_states = [State({'type': f'thr-{f}', 'key': ALL}, 'value') for f in FIELDS]

        table_state = State('thr-table', 'value')

        @app.callback(
            [Output('thr-rows', 'children'), Output('thr-add', 'value'), Output('thr-table', 'value')],
            [Input('thr-add', 'value'),
             Input({'type': 'thr-up', 'key': ALL}, 'n_clicks'),
             Input({'type': 'thr-down', 'key': ALL}, 'n_clicks'),
             Input({'type': 'thr-delete', 'key': ALL}, 'n_clicks'),
             Input('thr-discard', 'n_clicks'),
             Input('thr-defaults', 'n_clicks'),
             Input('thr-table-all', 'n_clicks'),
             Input('thr-table-clear', 'n_clicks')],
            field_states + [table_state],
            prevent_initial_call=True
        )
        def edit_rows(added, _up, _down, _delete, _discard, _defaults, _all, _clear, *args):
            *fields, table = args
            trigger, keys = ctx.triggered_id, _keys(ctx.states_list[0])
            if trigger in TABLE_BUTTONS:
                return no_update, no_update, self.edit_table(table or [], trigger, added, keys)
            rows = form_rows(keys, *fields)
            clicked = ctx.triggered[0]['value'] if ctx.triggered else None
            rows = self.edit(rows, trigger, clicked, added)
            new_keys = [row['key'] for row in rows]
            return ([self.render_row(row) for row in rows], None,
                    self.edit_table(table or [], trigger, added, new_keys))

        @app.callback(
            [Output({'type': 'thr-counts', 'key': ALL}, 'children'),
             Output({'type': 'thr-otherwise', 'key': ALL}, 'placeholder'),
             Output({'type': 'thr-error', 'key': ALL}, 'children'),
             Output('thr-summary', 'children'),
             Output('thr-save', 'disabled'),
             Output('thr-save', 'style'),
             Output('thr-download-button', 'disabled'),
             Output('thr-unsaved', 'children'),
             Output('thr-add', 'options'),
             Output('thr-table', 'options'),
             Output('thr-table-error', 'children')],
            [Input({'type': f'thr-{f}', 'key': ALL}, 'value') for f in FIELDS] + [Input('thr-table', 'value')]
        )
        def update_preview(*args):
            *fields, table = args
            shown = self.preview(form_rows(_keys(ctx.inputs_list[0]), *fields), table or [])
            return [shown[k] for k in ('counts', 'rest_defaults', 'errors', 'summary', 'save_off', 'save_style',
                                       'download_off', 'unsaved', 'options', 'table_options', 'table_error')]

        @app.callback(
            Output('thr-download', 'data'),
            [Input('thr-download-button', 'n_clicks')],
            field_states + [table_state],
            prevent_initial_call=True
        )
        def download(n_clicks, *args):
            *fields, table = args
            try:
                name, text = self.config_file(form_rows(_keys(ctx.states_list[0]), *fields), table or [])
            except ConfigError:
                raise PreventUpdate
            return dcc.send_string(text, name)

        @app.callback(
            [Output('thr-message', 'children'), Output('thr-saved', 'data')],
            [Input('thr-save', 'n_clicks')],
            field_states + [table_state, State('config-version', 'data')],
            prevent_initial_call=True
        )
        def save(n_clicks, *args):
            if not n_clicks:
                raise PreventUpdate
            *fields, table, version = args
            message, saved = self.save(form_rows(_keys(ctx.states_list[0]), *fields), version, table or [])
            return (_message(message, ok=saved or message == NOTHING_TO_SAVE),
                    self.dashboard.config_version if saved else no_update)

        # The page is rebuilt from the new thresholds; the tab it was on is kept by the tabs' persistence
        app.clientside_callback(
            "function(saved) { if (saved) { window.location.reload(); } return ''; }",
            Output('thr-reloading', 'children'),
            Input('thr-saved', 'data'),
            prevent_initial_call=True
        )
