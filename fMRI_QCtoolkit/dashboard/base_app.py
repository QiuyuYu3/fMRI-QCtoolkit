"""
Base dashboard class for MRI QC applications
"""

import dash
from dash import dcc, html, Input, Output, State, dash_table
import pandas as pd
import json
import os
from abc import ABC, abstractmethod
from ..utils.plots import create_lollipop_plot, create_heatmap

class BaseDashboard(ABC):
    """Base class for QC dashboards."""

    STATUS_TO_NUM = {'NA': 0, 'bad': 1, 'other': 2, 'good': 3}

    def __init__(self, data_processor, task=None):
        self.processor = data_processor
        self.task = task or "unknown"
        self.config = self._load_config()
        self.app = dash.Dash(__name__)
        self.setup_layout()
        self.setup_callbacks()

    def _load_config(self):
        """Load configuration from JSON file."""
        config_filename = self._get_config_filename()
        config_path = os.path.join(os.path.dirname(__file__), config_filename)
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file {config_filename} not found at {config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing {config_filename}: {e}")
    
    @abstractmethod
    def _get_config_filename(self):
        """Return the config filename for this dashboard type."""
        pass
    
    
    @abstractmethod
    def get_filter_components(self):
        """Return list of filter components for sidebar."""
        pass
    
    @abstractmethod
    def get_variable_labels(self):
        """Return dictionaries for quantitative and qualitative variable labels."""
        pass
    
    @abstractmethod
    def assign_status(self, value, variable_name):
        """Assign status based on value and variable name."""
        pass

    def setup_layout(self):
        """Setup the dashboard layout."""
        self.app.layout = html.Div([
            dcc.Store(id='filtered-data-store'),
            
            html.Div([
                # Sidebar
                html.Div([
                    html.Div([
                        html.H3("Filters"),
                        html.P(["Final DF fraction > 0.7, Censor fraction < 0.15, Average censored motion < 0.1, ",
                    "Max censored displacement < 6, Global correlation (GCOR) < 0.15, Flip guess, ",
                    "TSNR > 150(resting state), fraction TRs censored < 0.2"], style={'font-size': '12px', 'color': '#666'}),
                        
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
                                    columns=[{"name": i, "id": i} for i in self.processor.get_data().columns],
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
                        dcc.Tab(label='Plots', value='plots-tab', children=[
                            html.Div([
                                # Heatmap section
                                html.Div([
                                    html.H4("Quality Control Heatmaps"),
                                    html.Div([
                                        html.H5("Quantitative Metrics"),
                                        html.Div(
                                            dcc.Graph(id='quantitative-heatmap'),
                                            style={'overflowX': 'auto', 'width': '100%'}
                                        ),

                                        html.H5("Qualitative Ratings"),
                                        html.Div(
                                            dcc.Graph(id='qualitative-heatmap'),
                                            style={'overflowX': 'auto', 'width': '100%'}
                                        )
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
                                    dcc.Graph(id='lollipop-chart')
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
    
    def setup_callbacks(self):
        """Setup dashboard callbacks."""
        self._setup_lollipop_callback()
        self._setup_main_data_callback()
        self._setup_common_callbacks()
    
    def _setup_lollipop_callback(self):
        """Setup lollipop chart initialization callback."""
        @self.app.callback(
            Output('lollipop-chart', 'figure'),
            [Input('lollipop-chart', 'id')]
        )
        def initialize_lollipop_chart(chart_id):
            group_by = self.config.get("heatmap_settings", {}).get("group_by")
            return create_lollipop_plot(self.processor.lollipop_chart_data, group_by=group_by)
    
    def _get_extended_vars(self):
        """Safely extend the variable list to include new variables from the configuration file."""
        df = self.processor.get_data()

        base_vars = [var for var in self.processor.vars if var in df.columns]
        
        config_vars = []
        for item in self.config.get("quantitative_configs", []):
            var_name = item["variable"]
            if var_name in df.columns and var_name not in base_vars:
                config_vars.append(var_name)
        
        extended_vars = base_vars + config_vars
        
        if config_vars:
            print(f"Add additional variable: {config_vars}")
            
        return extended_vars
    
    def _setup_main_data_callback(self):
        
        available_vars = self._get_extended_vars()
        
        df = self.processor.get_data()
        for var in available_vars:
            if var not in df.columns:
                print(f"Warning: '{var}' will be ignore because it is not in the data.")
        
        available_vars = [var for var in available_vars if var in df.columns]
        
        slider_inputs = [Input(f"{var}_slider", "value") for var in available_vars]
        na_inputs = [Input(f"{var}_na", "value") for var in available_vars]
        dropdown_inputs = [Input(f"{group}_dropdown", "value") for group in self.processor.checkbox_groups]
        
        all_inputs = slider_inputs + na_inputs + dropdown_inputs + [
            Input('select-all-button', 'n_clicks'),
            Input('clear-selection-button', 'n_clicks')
        ]

        @self.app.callback(
            [
                Output('datatable', 'data'),
                Output('quantitative-heatmap', 'figure'),
                Output('qualitative-heatmap', 'figure'),
                Output('filtered-data-store', 'data'),
                Output('datatable', 'selected_rows')
            ],
            all_inputs,
            [
                State('datatable', 'selected_rows'),
                State('filtered-data-store', 'data')
            ]
        )
        def update_all_data(*args): 
            df = self.processor.get_data().copy()
            
            num_numeric_vars = len(available_vars)
            categorical_start_index = num_numeric_vars * 2
            
            range_vals = args[:num_numeric_vars]
            include_na_flags = args[num_numeric_vars:2*num_numeric_vars]
            # Trailing args: select-all click, clear click, then two States
            categorical_values = args[categorical_start_index:-4]

            prev_selected_rows = args[-2]
            prev_filtered_data = args[-1]

            # Group numeric inputs
            numeric_vars_with_inputs = [
                (var, range_vals[i], include_na_flags[i]) 
                for i, var in enumerate(available_vars)
            ]

            # Apply numeric filters
            for var, range_val, include_na in numeric_vars_with_inputs:
                if var not in df.columns:
                    continue
                    
                # Ensure range_val is valid
                if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
                    min_val, max_val = range_val
                elif isinstance(range_val, (float, int)):
                    min_val = max_val = range_val
                else:
                    continue

                include_na_bool = (
                    (isinstance(include_na, str) and 'na' in include_na.lower()) or
                    (isinstance(include_na, list) and 'include_na' in include_na) or
                    (isinstance(include_na, bool) and include_na)
                )

                if include_na_bool:
                    df = df[
                        (df[var].between(min_val, max_val)) |
                        df[var].isna()
                    ]
                else:
                    df = df[
                        df[var].between(min_val, max_val) & df[var].notna()
                    ]

            # Apply categorical filters
            for i, group in enumerate(self.processor.checkbox_groups):
                if group in df.columns and i < len(categorical_values):
                    selected_values = categorical_values[i] or []
                    if 'NA' in selected_values:
                        non_na_values = [v for v in selected_values if v != 'NA']
                        df = df[
                            df[group].isin(non_na_values) |
                            df[group].isna()
                        ]
                    else:
                        df = df[df[group].isin(selected_values)]

            self.filtered_df = df

            # Prepare quantitative heatmap data
            quant_vars = self._get_heatmap_quantitative_vars()
            quant_vars = [var for var in quant_vars if var in df.columns]

            quant_df = pd.DataFrame(self.quantitative_heatmap_rows(df, quant_vars))
            quant_labels, qual_labels = self.get_variable_labels()

            group_by = self.config.get("heatmap_settings", {}).get("group_by", "run")
            quant_fig = create_heatmap(quant_df, quant_labels, group_by=group_by)

            qual_df = pd.DataFrame(self.qualitative_heatmap_rows(df))
            qual_fig = create_heatmap(qual_df, qual_labels, group_by=group_by)
            
            triggered = dash.callback_context.triggered
            trigger_id = triggered[0]['prop_id'].split('.')[0] if triggered else None

            if trigger_id == 'select-all-button':
                new_selected_rows = list(range(len(df)))
            elif trigger_id == 'clear-selection-button':
                new_selected_rows = []
            else:
                selected_ids = []
                if prev_selected_rows and prev_filtered_data:
                    try:
                        prev_df = pd.DataFrame(prev_filtered_data)
                        selected_ids = prev_df.iloc[prev_selected_rows]['ID'].tolist()
                    except Exception as e:
                        print("Failed to extract previous selected IDs:", e)

                new_selected_rows = []
                if selected_ids:
                    id_to_index = {row['ID']: i for i, row in df.reset_index().iterrows()}
                    new_selected_rows = [id_to_index[id_] for id_ in selected_ids if id_ in id_to_index]

            return (
                df.to_dict('records'),
                quant_fig,
                qual_fig,
                df.to_dict('records'),
                new_selected_rows 
            )
    
    def _get_heatmap_quantitative_vars(self):
        """Get quantitative variables for heatmap from config."""
        return self.config.get("heatmap_quantitative_vars", [])

    @staticmethod
    def _row_index(row):
        """Identifiers the heatmap groups by; absent or missing values fall back to 1.

        `session` stays a string because BIDS session labels need not be numeric
        (ses-pre, ses-V1); `run` is a BIDS index and is always an integer.
        """
        run, session = row.get('run', 1), row.get('session', '1')
        return {
            'run': int(run) if pd.notna(run) else 1,
            'session': str(session) if pd.notna(session) else '1',
        }

    def quantitative_heatmap_rows(self, df, quant_vars):
        """Long-format rows for the quantitative heatmap."""
        rows = []
        for _, row in df.iterrows():
            for var in quant_vars:
                value = row[var]
                status_str = self.assign_status(value, var)
                rows.append({
                    'ID': str(row['ID']),
                    'Variables': str(var),
                    'Value': float(value) if pd.notna(value) else None,
                    'Status': int(self.STATUS_TO_NUM[status_str]),
                    'StatusStr': str(status_str),
                    **self._row_index(row),
                })
        return rows

    def qualitative_heatmap_rows(self, df):
        """Long-format rows for the qualitative heatmap."""
        rows = []
        for _, row in df.iterrows():
            for var in self.processor.checkbox_groups:
                if var not in row:
                    continue
                status_str = str(row[var]) if pd.notna(row[var]) else 'NA'
                rows.append({
                    'ID': str(row['ID']),
                    'Variables': str(var),
                    'Status': int(self.STATUS_TO_NUM.get(status_str, 0)),
                    'StatusStr': str(status_str),
                    **self._row_index(row),
                })
        return rows
    
    def _setup_common_callbacks(self):
        """Setup common callbacks for table interactions."""
        
        # Callback for selected rows display
        @self.app.callback(
            Output('selected-rows-display', 'children'),
            [Input('datatable', 'selected_rows'),
            Input('filtered-data-store', 'data')]
        )
        def display_selected_rows(selected_rows, filtered_data):
            if not selected_rows or not filtered_data:
                return html.Div("No row selected.", style={'padding': '10px', 'text-align': 'center'})

            max_index = len(filtered_data)
            safe_selected_rows = [i for i in selected_rows if i < max_index]

            if not safe_selected_rows:
                return html.Div("Selected rows are out of range due to filtering.", style={'padding': '10px', 'text-align': 'center', 'color': 'red'})

            selected_data = [filtered_data[i] for i in safe_selected_rows]

            return dash_table.DataTable(
                data=selected_data,
                columns=[{"name": i, "id": i} for i in self.processor.get_data().columns],
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
            State('filtered-data-store', 'data')]
        )
        def download_selected_data(n_clicks, selected_rows, filtered_data):
            if n_clicks:
                if selected_rows and filtered_data:
                    max_index = len(filtered_data)
                    safe_selected_rows = [i for i in selected_rows if i < max_index]

                    if safe_selected_rows:
                        selected_data = [filtered_data[i] for i in safe_selected_rows]
                        df_result = pd.DataFrame(selected_data)
                    else:
                        df_result = pd.DataFrame({"Message": ["Selected rows are out of range due to filtering."]})
                else:
                    df_result = pd.DataFrame({"Message": ["No row selected."]})

                return dcc.send_data_frame(df_result.to_csv, f"{self.task}_MRI_QC_subj.csv", index=False)

            return dash.no_update
        
        @self.app.callback(
            Output('datatable', 'page_size'),
            [Input('page-size-dropdown', 'value')]
        )
        def update_page_size(page_size):
            return page_size
    
    def run(self, host='127.0.0.1', port=8050, debug=False):
        """Run the dashboard."""
        print(f"Starting dashboard at http://{host}:{port}")
        self.app.run(host=host, port=port, debug=debug)