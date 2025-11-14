"""
Plotting utilities for MRI QC dashboards: heatmaps and lollipop charts
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np

def create_heatmap(data, variable_labels, title="", 
                   group_by=None, target_width=1200, cell_size=16):
    """
    Create heatmap visualization with flexible grouping options.
    Supports hierarchical grouping by session and run.
    
    Parameters:
    -----------
    data : pd.DataFrame
        Must contain columns: 'ID', 'Variables', 'Status'
        Optional: 'session', 'run', 'StatusStr'
    group_by : str or list
        - 'session': Group by session only
        - 'run': Group by run only
        - ['session', 'run']: Hierarchical grouping (session -> run)
        - None: Auto-group by number of subjects
    """
    if data.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data to display", 
                          xref="paper", yref="paper", 
                          x=0.5, y=0.5, showarrow=False)
        return fig

    status_colors = {
        0: '#D3D3D3',  # NA - light gray
        1: '#F8786E',  # bad - red
        2: '#FFD966',  # other - yellow
        3: '#C5E0B3'   # good - green
    }
    
    num_to_status = {0: 'NA', 1: 'bad', 2: 'other', 3: 'good'}

    # Add default session if not present
    if 'session' not in data.columns:
        data = data.copy()
        data['session'] = 1

    # Auto-detect grouping strategy if not specified
    if group_by is None:
        # Check if multiple sessions exist
        if 'session' in data.columns and data['session'].nunique() > 1:
            # Check if multiple runs exist
            if 'run' in data.columns and data['run'].nunique() > 1:
                group_by = ['session', 'run']
            else:
                group_by = 'session'
        elif 'run' in data.columns and data['run'].nunique() > 1:
            group_by = 'run'

    # Determine grouping strategy
    group_data = []
    group_labels = []
    
    if isinstance(group_by, list) and len(group_by) == 2:
        # Hierarchical grouping: session -> run
        primary, secondary = group_by
        
        if primary in data.columns and secondary in data.columns:
            # Get unique combinations of primary and secondary
            unique_combinations = data[[primary, secondary]].drop_duplicates().sort_values([primary, secondary])
            
            for _, row in unique_combinations.iterrows():
                primary_val = row[primary]
                secondary_val = row[secondary]
                
                subset = data[
                    (data[primary] == primary_val) & 
                    (data[secondary] == secondary_val)
                ]
                
                if not subset.empty:
                    group_data.append(subset)
                    group_labels.append(f"Session {int(primary_val):02d} - Run {int(secondary_val)}")
        else:
            print(f"Warning: Columns {primary} or {secondary} not found, using default grouping")
            group_by = None
    
    elif isinstance(group_by, str) and group_by in data.columns:
        # Single column grouping
        groups = sorted(data[group_by].dropna().unique())
        
        for group_val in groups:
            subset = data[data[group_by] == group_val]
            group_data.append(subset)
            
            if group_by == 'session':
                group_labels.append(f"Session {int(group_val):02d}")
            elif group_by == 'run':
                group_labels.append(f"Run {int(group_val)}")
            else:
                group_labels.append(f"{group_by.title()} {group_val}")
    
    # Default grouping: by number of subjects
    if not group_data:
        pivot_data_num = data.pivot(index='Variables', columns='ID', values='Status').fillna(0)
        unique_ids = list(pivot_data_num.columns)
        total_ids = len(unique_ids)
        
        # Calculate optimal subjects per subplot
        subjects_per_subplot = max(1, (target_width - 150) // cell_size)
        n_subplots = total_ids // subjects_per_subplot + (1 if total_ids % subjects_per_subplot > 0 else 0)
        n_subplots = max(1, n_subplots)
        
        # Redistribute subjects evenly
        base_subjects_per_plot = total_ids // n_subplots
        extra_subjects = total_ids % n_subplots
        
        start_idx = 0
        for i in range(n_subplots):
            subjects_in_this_plot = base_subjects_per_plot + (1 if i < extra_subjects else 0)
            end_idx = start_idx + subjects_in_this_plot
            
            group_ids = unique_ids[start_idx:end_idx]
            group_subset = data[data['ID'].isin(group_ids)]
            group_data.append(group_subset)
            group_labels.append(f"Subjects {start_idx+1}-{end_idx}")
            start_idx = end_idx

    # Create subplots
    n_groups = len(group_data)
    fig = make_subplots(
        rows=n_groups, cols=1,
        vertical_spacing=0.25 / max(1, n_groups - 1) if n_groups > 1 else 0.25,
        subplot_titles=group_labels
    )

    max_subjects = 0
    max_vars = 0

    # Process each group
    for i, group_subset in enumerate(group_data, start=1):
        if group_subset.empty:
            continue
            
        # Create pivot tables for this group
        pivot_data_num = group_subset.pivot(index='Variables', columns='ID', values='Status').fillna(0)
        
        # Sort by ID
        sorted_ids = sorted(pivot_data_num.columns, key=lambda x: int(x))
        pivot_data_num = pivot_data_num[sorted_ids]

        if 'StatusStr' in group_subset.columns:
            pivot_data_str = group_subset.pivot(index='Variables', columns='ID', values='StatusStr').fillna('NA')
            pivot_data_str = pivot_data_str[sorted_ids]
        else:
            pivot_data_str = pivot_data_num.applymap(lambda x: num_to_status[x])

        n_subjects = len(pivot_data_num.columns)
        n_variables = len(pivot_data_num.index)

        max_subjects = max(max_subjects, n_subjects)
        max_vars = max(max_vars, n_variables)

        # Create coordinates
        x_coords = list(range(n_subjects))
        y_coords = list(range(n_variables))

        # Prepare hover text
        hovertext = []
        for var_idx, var in enumerate(pivot_data_str.index):
            row = []
            for subj_idx, id_val in enumerate(pivot_data_str.columns):
                status = pivot_data_str.loc[var, id_val]
                var_label = variable_labels.get(var, var)
                
                # Add session/run info to hover if available
                hover_parts = [f"Subject: {id_val}", f"Variable: {var_label}", f"Status: {status}"]
                
                # Get session/run from the subset data
                subj_data = group_subset[group_subset['ID'] == id_val]
                if not subj_data.empty:
                    if 'session' in subj_data.columns:
                        session_val = subj_data['session'].iloc[0]
                        hover_parts.insert(1, f"Session: {int(session_val):02d}")
                    if 'run' in subj_data.columns:
                        run_val = subj_data['run'].iloc[0]
                        hover_parts.insert(2, f"Run: {int(run_val)}")
                
                row.append("<br>".join(hover_parts))
            hovertext.append(row)

        # Add heatmap trace
        fig.add_trace(
            go.Heatmap(
                z=pivot_data_num.values,
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
            row=i, col=1
        )

        # Update axes
        fig.update_xaxes(
            tickmode="array",
            tickvals=x_coords,
            ticktext=pivot_data_num.columns,
            tickangle=45,
            showline=False,
            showgrid=False,
            zeroline=False,
            row=i, col=1
        )
        
        fig.update_yaxes(
            tickmode="array",
            tickvals=y_coords,
            ticktext=[variable_labels.get(v, v) for v in pivot_data_num.index],
            showline=False,
            showgrid=False,
            zeroline=False,
            row=i, col=1
        )

    # Calculate figure dimensions
    fig_width = cell_size * max_subjects + 200
    fig_height = (cell_size * max_vars + 100) * n_groups

    fig.update_layout(
        title=title,
        height=fig_height,
        width=fig_width,
        margin=dict(t=50, b=50, l=50, r=50),
        font=dict(size=10, color='#444'),
        plot_bgcolor='#ffffff'
    )

    return fig

def create_lollipop_plot(data):
    """
    Create lollipop chart for standardized variables.
    """
    fig = go.Figure()
    
    colors = ['#A6CEE3', '#1F78B4', '#B2DF8A', '#33A02C', '#FB9A99', 
              '#E31A1C', '#FDBF6F', '#FF7F00', '#CAB2D6', '#6A3D9A']
    
    variables = data['Variable'].unique()
    
    for i, var in enumerate(variables):
        var_data = data[data['Variable'] == var]
        
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