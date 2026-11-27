"""
Base dashboard class for MRI QC applications
"""

import json
import logging
import threading
from pathlib import Path
from typing import NamedTuple

import dash
import dash_ag_grid as dag
import numpy as np
import pandas as pd
from dash import ALL, ctx, dcc, html, no_update, Input, Output, State
from dash.exceptions import PreventUpdate

from .config import ID_COLUMNS, Config, default_config_path, load_config, resolve_metrics
from .settings import SETTINGS_CSS, SETTINGS_TAB, SettingsTab
from ..utils.access import AccessGate, url_host
from ..utils.filter_components_utils import (ACCENT, RANGE, SIDEBAR_CSS, STATUS, create_metric_filter,
                                             create_qualitative_dropdown, create_rules_summary, default_statuses,
                                             slider_bounds)
from ..utils.plots import create_lollipop_plot, create_heatmap
from ..utils.status import assign_status, get_status_mapping

HEATMAP_COLUMNS = ['ID', 'Variables', 'Value', 'Status', 'StatusStr', 'session', 'run']
PLOTS_TAB = 'plots-tab'
# Dash 4 draws its controls in purple; html:root outranks the :root rule it adds, older Dash ignores it
# Dash 4's tab box clips what is wider than it; older Dash lets a narrow window scroll sideways to it instead
TAB_OVERFLOW_CSS = ".tab-parent { overflow: visible; }"
# AG Grid keeps room for a "no rows" message, which Selected Rows never shows
SELECTED_ROWS_CSS = "#selected-rows-table .ag-center-cols-viewport { min-height: 0; }"
ACCENT_STYLE = (f"<style>html:root {{ --Dash-Fill-Interactive-Strong: {ACCENT}; }} "
                f"{SIDEBAR_CSS} {TAB_OVERFLOW_CSS} {SETTINGS_CSS} {SELECTED_ROWS_CSS}</style>")
SPINNER_DELAY_MS = 300
# Each table row carries its position in the full table, which the grid uses as the row's id
ROW_ID = '_row'
# Display only: the table data and downloads keep full precision
NUMBER_FORMAT = {"function": "params.value == null ? '' : d3.format('.3~f')(params.value)"}
ROW_HEIGHT = 32
HEADER_HEIGHT = 36


def _shown(visible):
    return {} if visible else {'display': 'none'}


class ConfigState(NamedTuple):
    """What apply_config derives from a config, replaced whole so that no request sees half of a save."""
    config: Config
    metrics: list
    values: dict
    status: pd.DataFrame
    bounds: dict
    unmatched: list


class BaseDashboard:
    """Base class for QC dashboards; subclasses set PIPELINE, RATING_LABELS and GROUP_BY."""

    PIPELINE = None
    RATING_LABELS = {}
    GROUP_BY = None
    # What Use defaults in the Settings tab brings back
    DEFAULTS_NOTE = "The package's defaults"
    STATUS_TO_NUM = get_status_mapping()
    # The state in force; a method that reads several parts of it takes self.state once
    config = property(lambda self: self.state.config)
    metrics = property(lambda self: self.state.metrics)
    values = property(lambda self: self.state.values)
    status = property(lambda self: self.state.status)
    bounds = property(lambda self: self.state.bounds)
    unmatched = property(lambda self: self.state.unmatched)

    def __init__(self, data_processor, task=None, token=None, config_path=None):
        self.processor = data_processor
        self.task = task
        # Saving needs --config; a --config file that does not exist yet starts from the default
        self.save_path = Path(config_path) if config_path else None
        self.config_path = (self.save_path if self.save_path and self.save_path.exists()
                            else self.packaged_config())
        self.config_version = 0
        self.last_saved = None
        self.save_lock = threading.Lock()
        self._numeric = {}
        self.apply_config(load_config(self.config_path) if self.config_path else self.default_config())
        self.settings = SettingsTab(self)
        self.app = dash.Dash(__name__)
        self.app.index_string = self.app.index_string.replace("{%css%}", "{%css%}" + ACCENT_STYLE)
        self.gate = AccessGate(self.app.server, token)
        # A function, so every page load builds the sidebar from the thresholds in force
        self.app.layout = self.build_layout
        self.setup_callbacks()

    def packaged_config(self):
        """The package's config file for this pipeline; None where the defaults come from the data."""
        return default_config_path(self.PIPELINE)

    def default_config(self):
        """The settings used until a config file is saved, and by Use defaults."""
        return load_config(self.packaged_config())

    def numeric(self, column):
        if column not in self._numeric:
            self._numeric[column] = pd.to_numeric(self.processor.get_data()[column], errors='coerce')
        return self._numeric[column]

    def apply_config(self, config):
        """Rate every run with `config` and swap the result in as one object."""
        df = self.processor.get_data()
        metrics = resolve_metrics(config.metrics, list(df.columns))
        values = {m.column: self.numeric(m.column) for m in metrics}
        status = pd.DataFrame({m.column: assign_status(values[m.column], m.rules, m.otherwise) for m in metrics},
                              index=df.index)
        bounds = {m.column: slider_bounds(values[m.column], m) for m in metrics}
        unmatched = [key for key in [*config.metrics, *config.table_columns]
                     if '*' not in key and key not in df.columns]
        self.state = ConfigState(config, metrics, values, status, bounds, unmatched)

    def get_filter_components(self):
        state = self.state
        components = [create_metric_filter(m, state.bounds[m.column]) for m in state.metrics]
        df = self.processor.get_data()
        return components + [create_qualitative_dropdown(g, self.rating_label(g), df[g]) for g in self.rating_columns()]

    def rating_label(self, group):
        return group.replace('_', ' ').title()

    def rating_columns(self):
        columns = self.processor.get_data().columns
        return [g for g in self.processor.checkbox_groups if g in columns]

    def get_variable_labels(self):
        return {m.column: m.label for m in self.metrics}, self.RATING_LABELS

    def table_column_ids(self):
        """The table's columns: the IDs, the config's metrics in config order, its table-only columns in data
        order, then the ratings."""
        df = self.processor.get_data()
        state = self.state
        picked = set(state.config.table_columns)
        columns = ([c for c in ID_COLUMNS if c in df.columns] + [m.column for m in state.metrics]
                   + [c for c in df.columns if c in picked]
                   + self.rating_columns())
        return list(dict.fromkeys(columns))

    def _table_columns(self):
        df = self.processor.get_data()
        return [{"field": c, "headerName": c,
                 **({"valueFormatter": NUMBER_FORMAT} if pd.api.types.is_numeric_dtype(df[c]) else {}),
                 **({"pinned": "left"} if c in ID_COLUMNS else {})}
                for c in self.table_column_ids()]

    def table_records(self, positions):
        rows = self.processor.get_data().iloc[positions][self.table_column_ids()]
        return rows.assign(**{ROW_ID: [str(p) for p in positions]}).to_dict('records')

    def _grid(self, font_size, header_color, options, **props):
        """An AG Grid with the table's columns, styled like the rest of the page."""
        theme = json.dumps({'fontSize': font_size, 'headerBackgroundColor': header_color,
                            'headerFontWeight': 'bold', 'accentColor': ACCENT})
        return dag.AgGrid(
            columnDefs=self._table_columns(),
            columnSize='autoSize',
            # Values are shown as they are, without the grid guessing a type per column
            defaultColDef={'cellDataType': False, 'suppressMovable': True},
            dashGridOptions={'theme': {'function': f'themeQuartz.withParams({theme})'},
                             'rowHeight': ROW_HEIGHT, 'headerHeight': HEADER_HEIGHT,
                             # Column names may contain dots
                             'suppressFieldDotNotation': True, **options},
            **props)

    def plot_sections(self):
        """Which parts of the Plots tab have something to show; the others are hidden."""
        return {'quantitative': any(m.rated for m in self.metrics),
                'qualitative': bool(self.rating_columns()),
                'lollipop': not self.processor.get_lollipop_data().empty}

    def build_layout(self):
        shown = self.plot_sections()
        return html.Div([
            # Positions in the full table of the rows that pass the filters
            dcc.Store(id='filtered-rows'),
            # What the Plots tab currently shows, so it is not redrawn for nothing
            dcc.Store(id='heatmap-rows'),
            dcc.Store(id='lollipop-drawn'),
            # Which saved thresholds this page was built from
            dcc.Store(id='config-version', data=self.config_version),

            html.Div([
                # Sidebar
                html.Div([
                    html.Div([
                        html.H3("Filters"),
                        create_rules_summary(self.metrics),

                        # Filter components
                        html.Div(self.get_filter_components())

                    ], style={
                        'background-color': '#f8f9fa',
                        'padding': '15px',
                        'border-radius': '5px',
                        'border': '1px solid #dee2e6'
                    })
                ], style={'width': '18%', 'display': 'inline-block', 'vertical-align': 'top', 'margin-right': '2%'}),

                # Main content
                html.Div([
                    html.Div(id='stale-banner'),
                    # Persisted, so the page reloaded after a save stays on its tab
                    dcc.Tabs(id='main-tabs', value='table-tab', persistence=True, persistence_type='session',
                             children=[

                        # Table tab
                        dcc.Tab(label='Table', value='table-tab', children=[
                            html.Div([
                                # The header checkbox selects every row that passes the filters, on all pages
                                self._grid(12, '#f8f9fa', {
                                    'rowSelection': {'mode': 'multiRow'},
                                    'selectionColumnDef': {'pinned': 'left'},
                                    'pagination': True,
                                    'paginationPageSize': 10,
                                    'paginationPageSizeSelector': [10, 25, 50, 100],
                                    'domLayout': 'autoHeight',
                                }, id='datatable', rowData=[], getRowId=f'params.data.{ROW_ID}',
                                    style={'height': None, 'margin-top': '10px'}),

                                # Selected rows display
                                html.Div([
                                    html.Div([
                                        html.H4("Selected Rows"),
                                        html.Div(id='selected-rows-display')
                                    ], style={
                                        'border': '1px solid #ddd',
                                        'background-color': '#f8f9fa',
                                        'padding': '10px',
                                        'margin': '20px 0'
                                    })
                                ]),

                                # Download button
                                html.Div([
                                    html.Button("Download Selected Data",
                                              id="download-button",
                                              n_clicks=0,
                                              style={
                                                  'background-color': ACCENT,
                                                  'color': 'white',
                                                  'border': 'none',
                                                  'padding': '8px 16px',
                                                  'border-radius': '4px',
                                                  'cursor': 'pointer'
                                              }),
                                    dcc.Download(id="download-dataframe-csv")
                                ], style={'text-align': 'right', 'margin': '10px 0'})
                            ])
                        ]),

                        # Plots tab
                        dcc.Tab(label='Plots', value=PLOTS_TAB, children=[
                            html.Div([
                                # Heatmap section
                                # A part with nothing to show is hidden, yet stays in the page as its callback's output
                                html.Div([
                                    html.H4("Quality Control Heatmaps"),
                                    html.Div([
                                        html.Div([
                                            html.H5("Quantitative Metrics"),
                                            self._loading(html.Div(
                                                dcc.Graph(id='quantitative-heatmap'),
                                                style={'overflowX': 'auto', 'width': '100%'}
                                            )),
                                        ], id='quantitative-section', style=_shown(shown['quantitative'])),

                                        html.Div([
                                            html.H5("Qualitative Ratings"),
                                            self._loading(html.Div(
                                                dcc.Graph(id='qualitative-heatmap'),
                                                style={'overflowX': 'auto', 'width': '100%'}
                                            ))
                                        ], id='qualitative-section', style=_shown(shown['qualitative'])),
                                    ])
                                ], id='heatmap-section', style={
                                    'background-color': '#f8f9fa',
                                    'padding': '15px',
                                    'border-radius': '5px',
                                    'border': '1px solid #dee2e6',
                                    'margin': '20px 0',
                                    **_shown(shown['quantitative'] or shown['qualitative'])
                                }),

                                # Lollipop chart section
                                html.Div([
                                    html.H4("Standardized Metrics Overview"),
                                    self._loading(dcc.Graph(id='lollipop-chart'))
                                ], id='lollipop-section', style={
                                    'background-color': '#f8f9fa',
                                    'padding': '15px',
                                    'border-radius': '5px',
                                    'border': '1px solid #dee2e6',
                                    'margin': '20px 0',
                                    **_shown(shown['lollipop'])
                                })
                            ])
                        ]),

                        dcc.Tab(label='Settings', value=SETTINGS_TAB, children=[self.settings.layout()])
                    ])
                ], style={'width': '80%', 'display': 'inline-block', 'vertical-align': 'top'})
            ])
        ])

    @staticmethod
    def _loading(child):
        """Spinner over a plot while it is redrawn; it waits a moment so quick replies do not flash it."""
        # Not shown on mount, since every switch to the Plots tab mounts the plots again
        return dcc.Loading(child, delay_show=SPINNER_DELAY_MS, show_initially=False)

    def setup_callbacks(self):
        """Setup dashboard callbacks."""
        self._setup_table_callback()
        self._setup_plot_callbacks()
        self._setup_common_callbacks()
        self._setup_stale_page_warning()
        self.settings.register(self.app)

    def _setup_stale_page_warning(self):
        @self.app.callback(
            Output('stale-banner', 'children'),
            [Input('main-tabs', 'value'), Input('filtered-rows', 'data')],
            [State('config-version', 'data')]
        )
        def warn_if_stale(_tab, _positions, version):
            if version == self.config_version:
                return None
            return html.Div("Settings were changed in another tab. Reload the page to use them.",
                            style={'background-color': '#fff3cd', 'border': '1px solid #ffe08a',
                                   'padding': '8px 12px', 'border-radius': '4px', 'margin-bottom': '8px'})

    def _setup_plot_callbacks(self):
        """Draw the plots only while the Plots tab is open; its figures persist while it is hidden."""
        @self.app.callback(
            [
                Output('quantitative-heatmap', 'figure'),
                Output('qualitative-heatmap', 'figure'),
                Output('heatmap-rows', 'data')
            ],
            [Input('filtered-rows', 'data'), Input('main-tabs', 'value')],
            [State('heatmap-rows', 'data')]
        )
        def update_heatmaps(positions, tab, drawn_positions):
            if tab != PLOTS_TAB or positions is None or positions == drawn_positions:
                raise PreventUpdate
            return *self.heatmap_figures(self.processor.get_data().iloc[positions]), positions

        @self.app.callback(
            [Output('lollipop-chart', 'figure'), Output('lollipop-drawn', 'data')],
            [Input('main-tabs', 'value')],
            [State('lollipop-drawn', 'data')]
        )
        def draw_lollipop(tab, drawn):
            # It shows every run whatever the filters, so one drawing per page is enough
            if tab != PLOTS_TAB or drawn:
                raise PreventUpdate
            return create_lollipop_plot(self.processor.get_lollipop_data(), group_by=self.GROUP_BY), True

    def filtered_positions(self, ranges, statuses, ratings):
        """Positions in the full table of the rows that pass every filter; `ranges` and `statuses` are keyed by column."""
        df = self.processor.get_data()
        state = self.state
        keep = np.ones(len(df), dtype=bool)
        for metric in state.metrics:
            # A page built before a save may lack a metric; it then gets the default filter
            selected = statuses.get(metric.column, default_statuses(metric))
            allowed = set(selected or []) | (set() if metric.rated else {'good'})
            keep &= state.status[metric.column].isin(allowed).to_numpy()
            keep &= self._in_range(state, metric.column, ranges.get(metric.column))
        for group, selected in zip(self.rating_columns(), ratings):
            selected = selected or []
            passed = df[group].isin([v for v in selected if v != 'NA'])
            if 'NA' in selected:
                passed |= df[group].isna()
            keep &= passed.to_numpy()
        return np.flatnonzero(keep).tolist()

    @staticmethod
    def _in_range(state, column, value_range):
        """A handle left at the end of its slider sets no bound; missing values are left to the status filter."""
        values = state.values[column].to_numpy(dtype=float)
        passed = np.ones(len(values), dtype=bool)
        if not isinstance(value_range, (list, tuple)) or len(value_range) != 2:
            return passed
        (lo, hi), (slider_min, slider_max, _) = value_range, state.bounds[column]
        if lo > slider_min:
            passed &= values >= lo
        if hi < slider_max:
            passed &= values <= hi
        return passed | np.isnan(values)

    def _setup_table_callback(self):
        groups = self.rating_columns()

        # The grid keeps the selection of the rows that are still shown, since their row ids stay the same
        @self.app.callback(
            [Output('datatable', 'rowData'), Output('filtered-rows', 'data')],
            [Input({'type': RANGE, 'column': ALL}, 'value'), Input({'type': STATUS, 'column': ALL}, 'value')]
            + [Input(f'{g}_dropdown', 'value') for g in groups]
        )
        def update_table(*args):
            ranges, statuses = ({item['id']['column']: item.get('value') for item in items}
                                for items in ctx.inputs_list[:2])
            positions = self.filtered_positions(ranges, statuses, args[2:])
            return self.table_records(positions), positions

    def selected_data(self, selected_rows, positions=None):
        """Full-precision rows behind the table's selection that pass the filters, in the order of the full table."""
        picked = {int(row[ROW_ID]) for row in selected_rows or []}
        # The grid keeps rows a filter hid in selectedRows when none of the selected rows stays shown
        if positions is not None:
            picked &= set(positions)
        return self.processor.get_data().iloc[sorted(picked)]

    def selected_grid(self, selected):
        """Selected Rows shows every selected row, as tall as they need."""
        return self._grid(11, '#e9ecef', {'domLayout': 'autoHeight'}, id='selected-rows-table',
                          rowData=selected[self.table_column_ids()].to_dict('records'), style={'height': None})

    def heatmap_figures(self, df):
        quant_labels, qual_labels = self.get_variable_labels()
        group_by = self.GROUP_BY if self.GROUP_BY is not None else 'run'
        return (create_heatmap(self.quantitative_heatmap_rows(df), quant_labels, group_by=group_by),
                create_heatmap(self.qualitative_heatmap_rows(df), qual_labels, group_by=group_by))

    @staticmethod
    def _heatmap_index(df):
        """Session and run per row; absent or missing values fall back to '1' and 1."""
        session = df['session'] if 'session' in df else pd.Series(np.nan, index=df.index)
        run = df['run'] if 'run' in df else pd.Series(np.nan, index=df.index)
        return {
            'session': session.astype(object).where(session.notna(), '1').astype(str),
            'run': pd.to_numeric(run, errors='coerce').fillna(1).astype(int),
        }

    def quantitative_heatmap_rows(self, df):
        """Long table for the quantitative heatmap: one row per run and thresholded metric."""
        state = self.state
        metrics = [m for m in state.metrics if m.rated]
        if df.empty or not metrics:
            return pd.DataFrame(columns=HEATMAP_COLUMNS)
        index = self._heatmap_index(df)
        long = pd.concat([pd.DataFrame({
            'ID': df['ID'].astype(str),
            'Variables': m.column,
            'Value': state.values[m.column].loc[df.index],
            'StatusStr': state.status.loc[df.index, m.column],
            **index,
        }) for m in metrics], ignore_index=True)
        long['Status'] = long['StatusStr'].map(self.STATUS_TO_NUM).astype(int)
        return long[HEATMAP_COLUMNS]

    def qualitative_heatmap_rows(self, df):
        """Long table for the qualitative heatmap: one row per run and rated section."""
        groups = self.rating_columns()
        columns = [c for c in HEATMAP_COLUMNS if c != 'Value']
        if df.empty or not groups:
            return pd.DataFrame(columns=columns)
        index = self._heatmap_index(df)
        long = pd.concat([pd.DataFrame({
            'ID': df['ID'].astype(str),
            'Variables': g,
            'StatusStr': df[g].where(df[g].notna(), 'NA').astype(str),
            **index,
        }) for g in groups], ignore_index=True)
        long['Status'] = long['StatusStr'].map(self.STATUS_TO_NUM).fillna(0).astype(int)
        return long[columns]

    def _setup_common_callbacks(self):
        """Setup common callbacks for table interactions."""

        # Callback for selected rows display
        @self.app.callback(
            Output('selected-rows-display', 'children'),
            [Input('datatable', 'selectedRows'), Input('filtered-rows', 'data')]
        )
        def display_selected_rows(selected_rows, positions):
            selected = self.selected_data(selected_rows, positions)
            if selected.empty:
                return html.Div("No row selected.", style={'padding': '10px', 'text-align': 'center'})
            return self.selected_grid(selected)

        # Callback for download
        @self.app.callback(
            Output("download-dataframe-csv", "data"),
            [Input("download-button", "n_clicks")],
            [State('datatable', 'selectedRows'), State('filtered-rows', 'data')]
        )
        def download_selected_data(n_clicks, selected_rows, positions):
            if not n_clicks:
                return no_update
            selected = self.selected_data(selected_rows, positions)
            if selected.empty:
                selected = pd.DataFrame({"Message": ["No row selected."]})
            name = f"{self.task}_MRI_QC_subj.csv" if self.task else "MRI_QC_subj.csv"
            return dcc.send_data_frame(selected.to_csv, name, index=False)

    def config_source(self):
        if self.save_path is None:
            default = f"{self.config_path} (the package default" if self.config_path else "the defaults (no file"
            return f"{default}; to save changes made in the Settings tab, start the dashboard with --config FILE)"
        if self.save_path != self.config_path:
            return f"{self.save_path} (not created yet: starting from the default; the first save creates it)"
        return str(self.save_path)

    def run(self, host='127.0.0.1', port=8050, debug=False):
        """Run the dashboard."""
        self.gate.bind_host = host
        print(f"Thresholds and filters: {self.config_source()}")
        if self.unmatched:
            print(f"In the config but not in the data, so not shown: {', '.join(self.unmatched)}")
        print("Open the dashboard (the token is valid for this session only):")
        print(f"  {self.gate.link(f'http://{url_host(host)}:{port}')}")
        # Dash and werkzeug would print their own links without the token
        self.app.logger.setLevel(logging.WARNING)
        if not debug:
            logging.getLogger('werkzeug').setLevel(logging.WARNING)
        # The reloader re-runs the CLI in a child process, which would mint a second token
        self.app.run(host=host, port=port, debug=debug, use_reloader=False)
