
import dash
from dash import dcc, html, Input, Output, State, dash_table
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from plotly.subplots import make_subplots
import plotly.graph_objs as go

# Initialize the Dash app
app = dash.Dash(__name__)

session = "01"
prefix = "sub-"
project = "branch"
task = "kidvid_output"

# Set paths
df_final = pd.read_csv('/home/qy49547/Desktop/test/df_final.csv') # load data
lollipop_chart_data = pd.read_csv('/home/qy49547/Desktop/test/lollipop_chart_data.csv') # load data

# Define variable lists --------------------------------------------------------------
rating_bases = ["vorig", "ve2a", "va2t", "vstat", "mot", "regr", "radcor", "warns", "qsumm", "FINAL"]
core_cols = ["ID", "runs", "TRs_total_raw", "TRs_removed", "cens_mot", "cens_displace", "DF_frac", "TSNR", "cens_frac", "GCOR"]

frac_cols = [col for col in df_final.columns if col.startswith("frac_TRs_cens_")]
checkbox_groups = [f"{col}_r" for col in rating_bases]
vars = ["cens_frac", "cens_mot", "cens_displace", "TSNR", "DF_frac", "flip_guess", "GCOR"] + frac_cols

vars_of_interest = ["cens_frac", "cens_mot", "cens_displace", "TSNR", "DF_frac", "GCOR", "TRs_total_raw"]

# Dash APP ------------------------------------------------------------------

# Function to assign status value
def assign_status(value, variable_name):
    if pd.isna(value):
        return "NA"
    
    variable_name = str(variable_name)
    
    if variable_name == "DF_frac":
        if value > 0.7:
            return "good"
        elif value > 0.6:
            return "other"
        else:
            return "bad"
    elif variable_name == "cens_frac":
        if value >= 0.2:
            return "bad"
        elif value >= 0.15:
            return "other"
        else:
            return "good"
    elif variable_name == "cens_mot":
        if value >= 0.15:
            return "bad"
        elif value >= 0.1:
            return "other"
        else:
            return "good"
    elif variable_name == "cens_displace":
        if value >= 8:
            return "bad"
        elif value >= 6:
            return "other"
        else:
            return "good"
    elif variable_name == "GCOR":
        if value >= 0.2:
            return "bad"
        elif value >= 0.15:
            return "other"
        else:
            return "good"
    elif variable_name == "flip_guess":
        if value == 0:
            return "good"
        else:
            return "bad"
    elif variable_name == "TSNR":
        if value <= 150:
            return "other"
        else:
            return "good"
    else:
        return "other"


# Lollipop chart Plot ------------------------------------------------------------------

def create_lollipop_plot():
    fig = go.Figure()
    
    colors = ['#A6CEE3', '#1F78B4', '#B2DF8A', '#33A02C', '#FB9A99', 
              '#E31A1C', '#FDBF6F', '#FF7F00', '#CAB2D6', '#6A3D9A']
    
    variables = lollipop_chart_data['Variable'].unique()
    
    for i, var in enumerate(variables):
        var_data = lollipop_chart_data[lollipop_chart_data['Variable'] == var]
        
        # Add jitter to x positions
        x_jittered = var_data['row_number'] + np.random.uniform(-0.15, 0.15, len(var_data))
        
        # Add scatter points
        fig.add_trace(go.Scatter(
            x=x_jittered,
            y=var_data['Value'],
            mode='markers',
            marker=dict(size=8, color=colors[i % len(colors)]),
            name=var,
            hovertemplate='<b>ID:</b> %{customdata[0]}<br>' +
                         '<b>Value:</b> %{y}<br>' +
                         '<b>Variable:</b> %{customdata[1]}<br>' +
                         '<b>Mean:</b> %{customdata[2]:.4f}<extra></extra>',
            customdata=var_data[['ID', 'Variable', 'mean_value']].values
        ))
        
        # Add segments from 0 to each point
        for idx, (_, row) in enumerate(var_data.iterrows()):
            fig.add_trace(go.Scatter(
                x=[x_jittered.iloc[idx], x_jittered.iloc[idx]],
                y=[0, row['Value']],
                mode='lines',
                line=dict(color=colors[i % len(colors)], width=1),
                showlegend=False,
                hoverinfo='skip'
            ))
    
        fig.update_layout(
            title="",
            xaxis_title="Variables",
            yaxis_title="Standardized Value",
            height=600,
            hovermode='closest',
            template='plotly_white',
            margin=dict(t=60, b=60, l=60, r=60),
            xaxis=dict(showgrid=True, zeroline=True),
            yaxis=dict(showgrid=True, zeroline=True, zerolinewidth=2),
            hoverlabel=dict(
                bgcolor="rgb(40, 40, 40)",
                font=dict(size=10, color="white")
            )
        )

    
    return fig

# Heatmap Plot ------------------------------------------------------------------
# set n - subplots
#TODO
def create_heatmap(data, variable_labels, title="", n=2):
    if data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data to display", 
                          xref="paper", yref="paper", 
                          x=0.5, y=0.5, showarrow=False)
        return fig

    status_colors = {
        0: '#D3D3D3',  # NA
        1: '#F8786E',  # bad
        2: '#FFD966',  # other
        3: '#C5E0B3'   # good
    }
    
    num_to_status = {0: 'NA', 1: 'bad', 2: 'other', 3: 'good'}

    pivot_data_num = data.pivot(index='Variables', columns='ID', values='Status').fillna(0)
    
    if 'StatusStr' in data.columns:
        pivot_data_str = data.pivot(index='Variables', columns='ID', values='StatusStr').fillna('NA')
    else:
        pivot_data_str = pivot_data_num.applymap(lambda x: num_to_status[x])

    unique_ids = list(pivot_data_num.columns)
    total_ids = len(unique_ids)
    ids_per_plot = total_ids // n + (1 if total_ids % n > 0 else 0)

    fig = make_subplots(
        rows=n, cols=1,
        vertical_spacing=0.08
    )

    for i in range(n):
        start_idx = i * ids_per_plot
        end_idx = min((i + 1) * ids_per_plot, total_ids)

        plot_ids = unique_ids[start_idx:end_idx]
        plot_data_num = pivot_data_num[plot_ids]
        plot_data_str = pivot_data_str[plot_ids]

        n_subjects = len(plot_data_num.columns)
        n_variables = len(plot_data_num.index)
        
        x_coords = list(range(n_subjects))  # [0, 1, 2, ...]
        y_coords = list(range(n_variables))  # [0, 1, 2, ...]
        
        hovertext = []
        for var_idx, var in enumerate(plot_data_str.index):
            row = []
            for subj_idx, id_val in enumerate(plot_data_str.columns):
                status = plot_data_str.loc[var, id_val]
                row.append(f"Subject: {id_val}<br>Variable: {variable_labels.get(var, var)}<br>Status: {status}")
            hovertext.append(row)

        fig.add_trace(
            go.Heatmap(
                z=plot_data_num.values,
                x=x_coords,
                y=y_coords,
                colorscale=[
                    [0.0, status_colors[0]],   # NA
                    [0.33, status_colors[1]],  # bad
                    [0.66, status_colors[2]],  # other
                    [1.0, status_colors[3]]    # good
                ],
                showscale=False,
                xgap=2,
                ygap=2,
                hoverinfo="text",
                hovertext=hovertext,
                zmin=0,
                zmax=3
            ),
            row=i+1, col=1
        )

        fig.update_xaxes(
            tickmode="array",
            tickvals=x_coords,
            ticktext=plot_data_num.columns,
            tickangle=45,
            showline=False,
            showgrid=False,
            zeroline=False,
            row=i+1, col=1
        )
        
        fig.update_yaxes(
            tickmode="array",
            tickvals=y_coords,
            ticktext=[variable_labels.get(v, v) for v in plot_data_num.index],
            showline=False,
            showgrid=False,
            zeroline=False,
            row=i+1, col=1
        )

    fig.update_layout(
        title=title,
        height=280 * n,
        margin=dict(t=50, b=50, l=50, r=50),
        font=dict(size=10, color='#444'),
        plot_bgcolor='#ffffff'
    )

    return fig

# App layout ------------------------------------------------------------------

frac_slider_components = []

for col in frac_cols:
    label_text = col.replace("_", " ")
    # match = re.search(r"_(\d+)$", col)
    # suffix_number = match.group(1) if match else ""
    # label_text = f"fraction TRs censored {suffix_number}"
    frac_slider_components.append(
        html.Div([
            html.Label(label_text, style={'font-weight': 'bold'}),
            dcc.RangeSlider(
                id=f"{col}_slider",
                min=0,
                max=1,
                value=[0, 0.2],
                step=0.01,
                marks={0: '0', 0.2: '0.2', 1: '1'},
                tooltip={'placement': 'bottom', 'always_visible': True}
            ),
            dcc.Checklist(
                id=f"{col}_na",
                options=[{'label': 'Include NA', 'value': 'include_na'}],
                value=['include_na'],
                style={'margin-top': '5px'}
            )
        ], style={'margin-bottom': '15px'})
    )

app.layout = html.Div([
    # Store component for sharing filtered data between callbacks
    dcc.Store(id='filtered-data-store'),
    
    html.Div([
        # Sidebar
        html.Div([
            html.Div([
                html.H3("Filters"),
                html.P([
                    "Final DF fraction > 0.7, Censor fraction < 0.15, Average censored motion < 0.1, ",
                    "Max censored displacement < 6, Global correlation (GCOR) < 0.15, Flip guess, ",
                    "TSNR > 150(resting state), fraction TRs censored < 0.2"
                ], style={'font-size': '12px', 'color': '#666'}),
                
                # All slider inputs
                html.Div([
                    html.Label("Censor Fraction", style={'font-weight': 'bold'}),
                    dcc.RangeSlider(
                        id='cens_frac_slider',
                        min=0,
                        max=df_final['cens_frac'].max()+0.1,
                        value=[0, 0.15],
                        step=0.01,
                        marks={0: '0', 0.15: '0.15', round(df_final['cens_frac'].max(), 2): f"{df_final['cens_frac'].max():.2f}"},
                        tooltip={'placement': 'bottom', 'always_visible': True}
                    ),
                    dcc.Checklist(
                        id='cens_frac_na',
                        options=[{'label': 'Include NA', 'value': 'include_na'}],
                        value=['include_na'],
                        style={'margin-top': '5px'}
                    )
                ], style={'margin-bottom': '15px'}),
                
                html.Div([
                    html.Label("Average Censored Motion", style={'font-weight': 'bold'}),
                    dcc.RangeSlider(
                        id='cens_mot_slider',
                        min=0,
                        max=df_final['cens_mot'].max() + 0.1,
                        value=[0, 0.1],
                        step=0.01,
                        marks={0: '0', 0.1: '0.1', round(df_final['cens_mot'].max(), 2): f"{df_final['cens_mot'].max():.2f}"},
                        tooltip={'placement': 'bottom', 'always_visible': True}
                    ),
                    dcc.Checklist(
                        id='cens_mot_na',
                        options=[{'label': 'Include NA', 'value': 'include_na'}],
                        value=['include_na'],
                        style={'margin-top': '5px'}
                    )
                ], style={'margin-bottom': '15px'}),
                
                html.Div([
                    html.Label("Max Censored Displacement", style={'font-weight': 'bold'}),
                    dcc.RangeSlider(
                        id='cens_displace_slider',
                        min=0,
                        max=df_final['cens_displace'].max() + 10,
                        value=[0, 6],
                        step=0.01,
                        marks={0: '0', 6: '6', round(df_final['cens_displace'].max(), 1): f"{df_final['cens_displace'].max():.1f}"},
                        tooltip={'placement': 'bottom', 'always_visible': True}
                    ),
                    dcc.Checklist(
                        id='cens_displace_na',
                        options=[{'label': 'Include NA', 'value': 'include_na'}],
                        value=['include_na'],
                        style={'margin-top': '5px'}
                    )
                ], style={'margin-bottom': '15px'}),
                
                html.Div([
                    html.Label("TSNR Average", style={'font-weight': 'bold'}),
                    dcc.RangeSlider(
                        id='TSNR_slider',
                        min=df_final['TSNR'].min() - 1,
                        max=df_final['TSNR'].max() + 1,
                        value=[df_final['TSNR'].min() - 1, df_final['TSNR'].max() + 1],
                        step=1,
                        marks={int(df_final['TSNR'].min()): f"{int(df_final['TSNR'].min())}", 
                              int(df_final['TSNR'].max()): f"{int(df_final['TSNR'].max())}"},
                        tooltip={'placement': 'bottom', 'always_visible': True}
                    ),
                    dcc.Checklist(
                        id='TSNR_na',
                        options=[{'label': 'Include NA', 'value': 'include_na'}],
                        value=['include_na'],
                        style={'margin-top': '5px'}
                    )
                ], style={'margin-bottom': '15px'}),
                
                html.Div([
                    html.Label("final DF fraction", style={'font-weight': 'bold'}),
                    dcc.RangeSlider(
                        id='DF_frac_slider',
                        min=0,
                        max=1,
                        value=[0.7, 1],
                        step=0.1,
                        marks={0: '0', 0.7: '0.7', 1: '1'},
                        tooltip={'placement': 'bottom', 'always_visible': True}
                    ),
                    dcc.Checklist(
                        id='DF_frac_na',
                        options=[{'label': 'Include NA', 'value': 'include_na'}],
                        value=['include_na'],
                        style={'margin-top': '5px'}
                    )
                ], style={'margin-bottom': '15px'}),
                
                html.Div([
                    html.Label("flip guess", style={'font-weight': 'bold'}),
                    dcc.RangeSlider(
                        id='flip_guess_slider',
                        min=0,
                        max=1,
                        value=[0, 1],
                        step=1,
                        marks={0: '0', 1: '1'},
                        tooltip={'placement': 'bottom', 'always_visible': True}
                    ),
                    dcc.Checklist(
                        id='flip_guess_na',
                        options=[{'label': 'Include NA', 'value': 'include_na'}],
                        value=['include_na'],
                        style={'margin-top': '5px'}
                    )
                ], style={'margin-bottom': '15px'}),
                
                html.Div([
                    html.Label("GCOR", style={'font-weight': 'bold'}),
                    dcc.RangeSlider(
                        id='GCOR_slider',
                        min=0,
                        max=1,
                        value=[0, 0.15],
                        step=0.01,
                        marks={0: '0', 0.15: '0.15', 1: '1'},
                        tooltip={'placement': 'bottom', 'always_visible': True}
                    ),
                    dcc.Checklist(
                        id='GCOR_na',
                        options=[{'label': 'Include NA', 'value': 'include_na'}],
                        value=['include_na'],
                        style={'margin-top': '5px'}
                    )
                ], style={'margin-bottom': '15px'}),

                html.Div(frac_slider_components),
                
                # Qualitative variable dropdowns exactly as in original
                *[html.Div([
                    html.Label(group, style={'font-weight': 'bold'}),
                    dcc.Dropdown(
                        id=f'{group}_dropdown',
                        options=[
                            {'label': 'good', 'value': 'good'},
                            {'label': 'other', 'value': 'other'},
                            {'label': 'bad', 'value': 'bad'},
                            {'label': 'NA', 'value': 'NA'}
                        ],
                        value=['good', 'other', 'bad', 'NA'],
                        multi=True,
                        style={'font-size': '12px'}
                    )
                ], style={'margin-bottom': '10px'}) for group in checkbox_groups]
                
            ], style={
                'background-color': '#f8f9fa',
                'padding': '15px',
                'border-radius': '5px',
                'border': '1px solid #dee2e6'
            })
        ], style={'width': '18%', 'display': 'inline-block', 'vertical-align': 'top', 'margin-right': '2%'}),
        
        # Main content area with correct tab structure
        html.Div([
            dcc.Tabs(id='main-tabs', value='table-tab', children=[
                
                # Tab 1: Table
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
                        
                        # Data table
                        dash_table.DataTable(
                            id='datatable',
                            columns=[{"name": i, "id": i} for i in df_final.columns],
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
                                html.H4("Selected Row"),
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
                
                # Tab 2: Plots
                dcc.Tab(label='Plots', value='plots-tab', children=[
                    html.Div([
                        # Heatmap Section
                        html.Div([
                            html.H4("Heatmap"),

                            html.Div([
                                html.H5("Quantitative Heatmap"),
                                dcc.Graph(id='quantitative-heatmap'),

                                html.H5("Qualitative Heatmap"),
                                dcc.Graph(id='qualitative-heatmap')
                            ])
                        ], style={
                            'background-color': '#f8f9fa',
                            'padding': '15px',
                            'border-radius': '5px',
                            'border': '1px solid #dee2e6',
                            'margin': '20px 0'
                        }),

                        # Lollipop Chart Section
                        html.Div([
                            html.H4("Lollipop Chart"),
                            dcc.Graph(id='lollipop-chart', figure=create_lollipop_plot())
                        ], style={
                            'background-color': '#f8f9fa',
                            'padding': '15px',
                            'border-radius': '5px',
                            'border': '1px solid #dee2e6',
                            'margin': '20px 0'
                        })
                    ])
                ]),
                
                # Tab 3: Resources
                dcc.Tab(label='Resources', value='resources-tab', children=[
                    html.Div([
                        html.H4("Reference"),
                        html.P([
                            html.A("https://afni.github.io/qc-demo-repo/", 
                                  href="https://afni.github.io/qc-demo-repo/",
                                  target="_blank")
                        ]),
                        html.P([
                            html.A("Reynolds, R. C., Taylor, P. A., & Glen, D. R. (2023). Quality control practices in FMRI analysis: Philosophy, methods and examples using AFNI. Frontiers in Neuroscience, 16, 1073800. https://doi.org/10.3389/fnins.2022.1073800", 
                                  href="https://doi.org/10.3389/fnins.2022.1073800",
                                  target="_blank")
                        ]),
                        html.P([
                            html.A("Paul A. Taylor, Daniel R. Glen, Gang Chen, Robert W. Cox, Taylor Hanayik, Chris Rorden, Dylan M. Nielson, Justin K. Rajendra, Richard C. Reynolds; A Set of FMRI Quality Control Tools in AFNI: Systematic, in-depth, and interactive QC with afni_proc.py and more. Imaging Neuroscience 2024; 2 1–39. doi: https://doi.org/10.1162/imag_a_00246", 
                                  href="https://doi.org/10.1162/imag_a_00246",
                                  target="_blank")
                        ])
                    ], style={'padding': '20px'})
                ])
            ])
        ], style={'width': '80%', 'display': 'inline-block', 'vertical-align': 'top'})
    ])
])

@app.callback(
    [
        Output('datatable', 'data'),
        Output('quantitative-heatmap', 'figure'),
        Output('qualitative-heatmap', 'figure'),
        Output('filtered-data-store', 'data'),
        Output('datatable', 'selected_rows'),
    ],
    # Combine numeric inputs (slider + NA toggle)
    [Input(f"{var}_slider", "value") for var in vars] +
    [Input(f"{var}_na", "value") for var in vars] +
    # Add group dropdown inputs
    [Input(f"{group}_dropdown", "value") for group in checkbox_groups],

    [State('datatable', 'selected_rows'),
     State('filtered-data-store', 'data')]
)

def update_all_data(*args):
    num_numeric_vars = len(vars)
    categorical_start_index = num_numeric_vars * 2

    # Extract slider ranges and include_na flags for numeric variables
    range_vals = args[:num_numeric_vars]
    include_na_flags = args[num_numeric_vars:2*num_numeric_vars]
    categorical_values = args[categorical_start_index:-2]

    prev_selected_rows = args[-2]
    prev_filtered_data = args[-1]

    status_to_num = {'NA': 0, 'bad': 1, 'other': 2, 'good': 3}
    filtered_df = df_final.copy()

    # Apply filters for numeric variables
    for idx, var in enumerate(vars):
        if var not in filtered_df.columns:
            # print(f"Warning: {var} not found in DataFrame. Skipping.")
            continue

        # Extract the corresponding range and NA flag
        range_val = range_vals[idx] if idx < len(range_vals) else None
        include_na = include_na_flags[idx] if idx < len(include_na_flags) else False

        # Ensure range_val is a valid range (tuple or list of length 2)
        if isinstance(range_val, (list, tuple)) and len(range_val) == 2:
            min_val, max_val = range_val
        elif isinstance(range_val, (float, int)):
            # Single numeric value means an exact match
            min_val = max_val = range_val
        else:
            print(f"Warning: Invalid range for {var}: {range_val}. Skipping.")
            continue

        # Normalize include_na to boolean
        include_na_bool = (
            (isinstance(include_na, str) and 'na' in include_na.lower()) or
            (isinstance(include_na, list) and 'include_na' in include_na) or
            (isinstance(include_na, bool) and include_na)
        )

        # Apply filter with or without NA values
        if include_na_bool:
            filtered_df = filtered_df[
                (filtered_df[var].between(min_val, max_val)) | filtered_df[var].isna()
            ]
        else:
            filtered_df = filtered_df[
                filtered_df[var].between(min_val, max_val) & filtered_df[var].notna()
            ]

    # Apply filters for categorical variables
    for i, group in enumerate(checkbox_groups):
        if group in filtered_df.columns:
            selected_values = categorical_values[i] or []
            if 'NA' in selected_values:
                # Filter by selected values including NA
                non_na_values = [v for v in selected_values if v != 'NA']
                filtered_df = filtered_df[
                    filtered_df[group].isin(non_na_values) |
                    filtered_df[group].isna()
                ]
            else:
                # Filter only by selected values
                filtered_df = filtered_df[filtered_df[group].isin(selected_values)]
    
    # Prepare quantitative heatmap data
    quant_vars = ['cens_frac', 'cens_mot', 'cens_displace', 'TSNR', 'DF_frac', 
                  'flip_guess', 'GCOR']
    
    quant_data = []
    for _, row in filtered_df.iterrows():
        for var in quant_vars:
            if var in row:
                value = row[var]
                status_str = assign_status(value, var)
                status_num = status_to_num[status_str]
                
                hover_text = f"Subject: {row['ID']}<br>Variable: {var}<br>Value: {value if pd.notna(value) else 'NA'}<br>Status: {status_str}"
                quant_data.append({
                    'ID': row['ID'],
                    'Variables': var,
                    'Value': value,
                    'Status': status_num,
                    'StatusStr': status_str,
                    'hover_text': hover_text
                })
    
    quant_df = pd.DataFrame(quant_data)
    
    # Create quantitative heatmap
    quant_variable_labels = {
        "cens_frac": "cens fraction",
        "cens_mot": "cens motion", 
        "cens_displace": "cens displace",
        "DF_frac": "DF fraction",
        "flip_guess": "flip guess",
        "TSNR": "TSNR"
    }
    
    quant_fig = create_heatmap(quant_df, quant_variable_labels)
    
    # Prepare qualitative heatmap data exactly as in original R code
    qual_data = []
    for _, row in filtered_df.iterrows():
        for var in checkbox_groups:
            if var in row:
                status_str = row[var] if pd.notna(row[var]) else 'NA'
                status_num = status_to_num[status_str]   # 转换为数字
                
                hover_text = f"Subject: {row['ID']}<br>Metric: {var}<br>Status: {status_str}"
                qual_data.append({
                    'ID': row['ID'],
                    'Variables': var,
                    'Status': status_num,
                    'StatusStr': status_str,
                    'hover_text': hover_text
                })
    
    qual_df = pd.DataFrame(qual_data)
    
    # Create qualitative heatmap
    qual_variable_labels = {
        "mot_r": "motion",
        "radcor_r": "correlation",
        "regr_r": "regression", 
        "va2t_r": "anat to template",
        "ve2a_r": "EPI to anat",
        "vorig_r": "vorig",
        "vstat_r": "vstat",
        "warns_r": "warnings",
        "qsumm_r": "quantitative",
        "FINAL_r": "final"
    }
    
    qual_fig = create_heatmap(qual_df, qual_variable_labels)
    
    selected_ids = []
    if prev_selected_rows and prev_filtered_data:
        try:
            prev_df = pd.DataFrame(prev_filtered_data)
            selected_ids = prev_df.iloc[prev_selected_rows]['ID'].tolist()
        except Exception as e:
            print("Failed to extract previous selected IDs:", e)


    new_selected_rows = []
    if selected_ids:
        id_to_index = {row['ID']: i for i, row in filtered_df.reset_index().iterrows()}
        new_selected_rows = [id_to_index[id_] for id_ in selected_ids if id_ in id_to_index]

    return (
        filtered_df.to_dict('records'),
        quant_fig,
        qual_fig,
        filtered_df.to_dict('records'),
        new_selected_rows 
    )

# Callback for selected rows display
@app.callback(
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
        columns=[{"name": i, "id": i} for i in df_final.columns],
        style_table={'height': '300px', 'overflowY': 'auto', 'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'fontSize': '11px', 'padding': '6px'},
        style_header={'backgroundColor': '#e9ecef', 'fontWeight': 'bold'},
        page_size=50
    )

# Callback for download
@app.callback(
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

        return dcc.send_data_frame(df_result.to_csv, f"{project}_{task}_{session}_MRI_QC_subj.csv", index=False)

    return dash.no_update

@app.callback(
    Output('datatable', 'page_size'),
    [Input('page-size-dropdown', 'value')]
)
def update_page_size(page_size):
    return page_size

if __name__ == '__main__':
    app.run(debug=True)