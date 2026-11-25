"""
Base dashboard class for MRI QC applications
"""

import logging
from pathlib import Path

import dash
import numpy as np
import pandas as pd
from dash import ctx, dcc, html, no_update, Input, Output, State, dash_table
from dash.dash_table.Format import Format, Scheme, Trim
from dash.exceptions import PreventUpdate

from .config import default_config_path, load_config, resolve_metrics
from ..utils.access import AccessGate, url_host
from ..utils.filter_components_utils import (create_metric_filter, create_qualitative_dropdown,
                                             create_rules_summary, slider_bounds)
from ..utils.plots import create_lollipop_plot, create_heatmap
from ..utils.status import assign_status, get_status_mapping

HEATMAP_COLUMNS = ['ID', 'Variables', 'Value', 'Status', 'StatusStr', 'session', 'run']
PLOTS_TAB = 'plots-tab'
SPINNER_DELAY_MS = 300


class BaseDashboard:
    """Base class for QC dashboards; subclasses set PIPELINE, RATING_LABELS and GROUP_BY."""

    PIPELINE = None
    RATING_LABELS = {}
    GROUP_BY = None
    STATUS_TO_NUM = get_status_mapping()
    # Display only: the table data and downloads keep full precision
    TABLE_NUMBER_FORMAT = Format(precision=3, scheme=Scheme.fixed, trim=Trim.yes)

    def __init__(self, data_processor, task=None, token=None, config_path=None):
        self.processor = data_processor
        self.task = task or "unknown"
        self.config_path = Path(config_path) if config_path else default_config_path(self.PIPELINE)
        self._prepare_metrics(load_config(self.config_path))
        self.app = dash.Dash(__name__)
        self.gate = AccessGate(self.app.server, token)
        self.setup_layout()
        self.setup_callbacks()

    def _prepare_metrics(self, config):
        df = self.processor.get_data()
        self.metrics = resolve_metrics(config, list(df.columns))
        self.unmatched = [key for key in config if '*' not in key and key not in df.columns]
        self.values = {m.column: pd.to_numeric(df[m.column], errors='coerce') for m in self.metrics}
        self.status = pd.DataFrame(
            {m.column: assign_status(self.values[m.column], m.rules) for m in self.metrics}, index=df.index)
        self.bounds = {m.column: slider_bounds(self.values[m.column], m) for m in self.metrics}

    def get_filter_components(self):
        components = [create_metric_filter(m, self.bounds[m.column]) for m in self.metrics]
        return components + [create_qualitative_dropdown(g) for g in self.processor.checkbox_groups]

    def get_variable_labels(self):
        return {m.column: m.label for m in self.metrics}, self.RATING_LABELS

    def _table_columns(self):
        df = self.processor.get_data()
        return [
            {"name": c, "id": c, "type": "numeric", "format": self.TABLE_NUMBER_FORMAT}
            if pd.api.types.is_numeric_dtype(df[c]) else {"name": c, "id": c}
            for c in df.columns
        ]

    def setup_layout(self):
        """Setup the dashboard layout."""
        self.app.layout = html.Div([
            # Positions in the full table of the rows that pass the filters
            dcc.Store(id='filtered-rows'),
            # What the Plots tab currently shows, so it is not redrawn for nothing
            dcc.Store(id='heatmap-rows'),
            dcc.Store(id='lollipop-drawn'),

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
                    dcc.Tabs(id='main-tabs', value='table-tab', children=[

                        # Table tab
                        dcc.Tab(label='Table', value='table-tab', children=[
                            html.Div([
                                # Page size selector
                                html.Div([
                                    html.Label("Rows per page: ", style={'margin-right': '10px', 'font-weight': 'bold'}),
                                    dcc.Dropdown(
                                        id='page-size-dropdown',
                                        options=[
                                            {'label': '10', 'value': 10},
                                            {'label': '25', 'value': 25},
                                            {'label': '50', 'value': 50},
                                            {'label': '100', 'value': 100},
                                            {'label': 'All', 'value': 99999}
                                        ],
                                        value=10,
                                        style={'width': '100px', 'display': 'inline-block'}
                                    )
                                ], style={'margin-bottom': '10px', 'display': 'flex', 'align-items': 'center'}),

                                # Selection toolbar
                                html.Div([
                                    html.Button("Select All (filtered)",
                                              id="select-all-button",
                                              n_clicks=0,
                                              style={
                                                  'background-color': '#6c757d',
                                                  'color': 'white',
                                                  'border': 'none',
                                                  'padding': '6px 12px',
                                                  'border-radius': '4px',
                                                  'cursor': 'pointer',
                                                  'margin-right': '8px'
                                              }),
                                    html.Button("Clear",
                                              id="clear-selection-button",
                                              n_clicks=0,
                                              style={
                                                  'background-color': '#6c757d',
                                                  'color': 'white',
                                                  'border': 'none',
                                                  'padding': '6px 12px',
                                                  'border-radius': '4px',
                                                  'cursor': 'pointer'
                                              })
                                ], style={'margin-bottom': '10px'}),

                                # Data table
                                dash_table.DataTable(
                                    id='datatable',
                                    columns=self._table_columns(),
                                    page_size=10,
                                    sort_action='native',
                                    style_table={'height': 'auto', 'overflowY': 'auto', 'overflowX': 'auto'},
                                    style_cell={'textAlign': 'left', 'fontSize': '12px', 'padding': '8px'},
                                    style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold'},
                                    row_selectable='multi',
                                    selected_rows=[]
                                ),

                                # Selected rows display
                                html.Div([
                                    html.Div([
                                        html.H4("Selected Rows"),
                                        html.Div(id='selected-rows-display')
                                    ], style={
                                        'max-height': '400px',
                                        'overflow-y': 'auto',
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
                                                  'background-color': '#007bff',
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
                                html.Div([
                                    html.H4("Quality Control Heatmaps"),
                                    html.Div([
                                        html.H5("Quantitative Metrics"),
                                        self._loading(html.Div(
                                            dcc.Graph(id='quantitative-heatmap'),
                                            style={'overflowX': 'auto', 'width': '100%'}
                                        )),

                                        html.H5("Qualitative Ratings"),
                                        self._loading(html.Div(
                                            dcc.Graph(id='qualitative-heatmap'),
                                            style={'overflowX': 'auto', 'width': '100%'}
                                        ))
                                    ])
                                ], style={
                                    'background-color': '#f8f9fa',
                                    'padding': '15px',
                                    'border-radius': '5px',
                                    'border': '1px solid #dee2e6',
                                    'margin': '20px 0'
                                }),

                                # Lollipop chart section
                                html.Div([
                                    html.H4("Standardized Metrics Overview"),
                                    self._loading(dcc.Graph(id='lollipop-chart'))
                                ], style={
                                    'background-color': '#f8f9fa',
                                    'padding': '15px',
                                    'border-radius': '5px',
                                    'border': '1px solid #dee2e6',
                                    'margin': '20px 0'
                                })
                            ])
                        ])
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
        """Positions in the full table of the rows that pass every filter."""
        df = self.processor.get_data()
        keep = np.ones(len(df), dtype=bool)
        for metric, value_range, selected in zip(self.metrics, ranges, statuses):
            allowed = set(selected or []) | (set() if metric.rules else {'good'})
            keep &= self.status[metric.column].isin(allowed).to_numpy()
            keep &= self._in_range(metric.column, value_range)
        for group, selected in zip(self.processor.checkbox_groups, ratings):
            if group in df.columns:
                selected = selected or []
                passed = df[group].isin([v for v in selected if v != 'NA'])
                if 'NA' in selected:
                    passed |= df[group].isna()
                keep &= passed.to_numpy()
        return np.flatnonzero(keep).tolist()

    def _in_range(self, column, value_range):
        """A handle left at the end of its slider sets no bound; missing values are left to the status filter."""
        values = self.values[column].to_numpy(dtype=float)
        passed = np.ones(len(values), dtype=bool)
        if not isinstance(value_range, (list, tuple)) or len(value_range) != 2:
            return passed
        (lo, hi), (slider_min, slider_max, _) = value_range, self.bounds[column]
        if lo > slider_min:
            passed &= values >= lo
        if hi < slider_max:
            passed &= values <= hi
        return passed | np.isnan(values)

    def _setup_table_callback(self):
        groups = self.processor.checkbox_groups
        n_metrics = len(self.metrics)

        @self.app.callback(
            [
                Output('datatable', 'data'),
                Output('filtered-rows', 'data'),
                Output('datatable', 'selected_rows')
            ],
            [Input(f'{m.column}_slider', 'value') for m in self.metrics]
            + [Input(f'{m.column}_status', 'value') for m in self.metrics]
            + [Input(f'{g}_dropdown', 'value') for g in groups]
            + [Input('select-all-button', 'n_clicks'), Input('clear-selection-button', 'n_clicks')],
            [
                State('datatable', 'selected_rows'),
                State('filtered-rows', 'data')
            ]
        )
        def update_table(*args):
            prev_selected_rows, prev_positions = args[-2], args[-1]
            # The buttons change the selection only; the filtered rows stay as they are
            if ctx.triggered_id == 'select-all-button':
                return no_update, no_update, list(range(len(prev_positions or [])))
            if ctx.triggered_id == 'clear-selection-button':
                return no_update, no_update, []

            ranges, statuses = args[:n_metrics], args[n_metrics:2 * n_metrics]
            ratings = args[2 * n_metrics:2 * n_metrics + len(groups)]
            positions = self.filtered_positions(ranges, statuses, ratings)
            records = self.processor.get_data().iloc[positions].to_dict('records')
            return records, positions, self._carry_selection(prev_positions, prev_selected_rows, positions)

    @staticmethod
    def _carry_selection(prev_positions, prev_selected_rows, positions):
        """Indices in the new table of the rows that were selected in the previous one."""
        if not prev_positions or not prev_selected_rows:
            return []
        selected = {prev_positions[i] for i in prev_selected_rows if i < len(prev_positions)}
        return [i for i, position in enumerate(positions) if position in selected]

    def selected_data(self, positions, selected_rows):
        """Full-precision rows behind the table's selection; `selected_rows` index the filtered table."""
        positions = positions or []
        picked = [positions[i] for i in selected_rows or [] if i < len(positions)]
        return self.processor.get_data().iloc[picked]

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
        metrics = [m for m in self.metrics if m.rules]
        if df.empty or not metrics:
            return pd.DataFrame(columns=HEATMAP_COLUMNS)
        index = self._heatmap_index(df)
        long = pd.concat([pd.DataFrame({
            'ID': df['ID'].astype(str),
            'Variables': m.column,
            'Value': self.values[m.column].loc[df.index],
            'StatusStr': self.status.loc[df.index, m.column],
            **index,
        }) for m in metrics], ignore_index=True)
        long['Status'] = long['StatusStr'].map(self.STATUS_TO_NUM).astype(int)
        return long[HEATMAP_COLUMNS]

    def qualitative_heatmap_rows(self, df):
        """Long table for the qualitative heatmap: one row per run and rated section."""
        groups = [g for g in self.processor.checkbox_groups if g in df.columns]
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
            [Input('datatable', 'selected_rows'),
            Input('filtered-rows', 'data')]
        )
        def display_selected_rows(selected_rows, positions):
            selected = self.selected_data(positions, selected_rows)
            if selected.empty:
                return html.Div("No row selected.", style={'padding': '10px', 'text-align': 'center'})

            return dash_table.DataTable(
                data=selected.to_dict('records'),
                columns=self._table_columns(),
                style_table={'height': '300px', 'overflowY': 'auto', 'overflowX': 'auto'},
                style_cell={'textAlign': 'left', 'fontSize': '11px', 'padding': '6px'},
                style_header={'backgroundColor': '#e9ecef', 'fontWeight': 'bold'},
                page_size=50
            )

        # Callback for download
        @self.app.callback(
            Output("download-dataframe-csv", "data"),
            [Input("download-button", "n_clicks")],
            [State('datatable', 'selected_rows'),
            State('filtered-rows', 'data')]
        )
        def download_selected_data(n_clicks, selected_rows, positions):
            if not n_clicks:
                return no_update
            selected = self.selected_data(positions, selected_rows)
            if selected.empty:
                selected = pd.DataFrame({"Message": ["No row selected."]})
            return dcc.send_data_frame(selected.to_csv, f"{self.task}_MRI_QC_subj.csv", index=False)

        @self.app.callback(
            Output('datatable', 'page_size'),
            [Input('page-size-dropdown', 'value')]
        )
        def update_page_size(page_size):
            return page_size

    def run(self, host='127.0.0.1', port=8050, debug=False):
        """Run the dashboard."""
        self.gate.bind_host = host
        print(f"Thresholds and filters: {self.config_path}")
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
