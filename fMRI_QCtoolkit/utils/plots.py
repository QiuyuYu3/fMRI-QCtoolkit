"""
Plotting utilities for MRI QC dashboards: heatmaps and lollipop charts
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd

from .status import get_status_colors, get_status_mapping

_LOLLIPOP_COLORS = ['#A6CEE3', '#1F78B4', '#B2DF8A', '#33A02C', '#FB9A99',
                    '#E31A1C', '#FDBF6F', '#FF7F00', '#CAB2D6', '#6A3D9A']


def format_session(value):
    """BIDS session labels need not be numeric; numeric ones keep their zero padding."""
    label = str(value)
    return label.zfill(2) if label.isdigit() else label


def _id_sort_key(value):
    """Numeric IDs first in numeric order, then alphanumeric ones; matches the prep output order."""
    label = str(value)
    return (0, int(label), label) if label.isdigit() else (1, 0, label)

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

    status_colors = get_status_colors()
    num_to_status = {num: status for status, num in get_status_mapping().items()}
    # Rows keep the order the variables arrive in, listed top to bottom
    var_order = list(dict.fromkeys(data['Variables']))
    label_px = max(50, 7 * max(len(str(variable_labels.get(v, v))) for v in var_order))

    # Add default session if not present
    if 'session' not in data.columns:
        data = data.copy()
        data['session'] = '1'

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
                    group_labels.append(f"Session {format_session(primary_val)} - Run {int(secondary_val)}")
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
                group_labels.append(f"Session {format_session(group_val)}")
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

    # Create subplots; each panel is cell_size per row, with room between panels for ticks and a title
    n_groups = len(group_data)
    panel_gap = 100
    plot_height = n_groups * (cell_size * len(var_order) + panel_gap) - panel_gap
    fig = make_subplots(
        rows=n_groups, cols=1,
        vertical_spacing=panel_gap / plot_height if n_groups > 1 else 0,
        subplot_titles=group_labels
    )
    # At the panel's left edge, so a figure wider than its scroll box still shows the titles
    fig.update_annotations(x=0, xanchor='left')

    max_subjects = 0
    traces = []

    # Process each group
    for i, group_subset in enumerate(group_data, start=1):
        if group_subset.empty:
            continue

        # Create pivot tables for this group
        pivot_data_num = group_subset.pivot(index='Variables', columns='ID', values='Status').fillna(0)
        pivot_data_num = pivot_data_num.reindex([v for v in var_order if v in pivot_data_num.index])

        # Sort by ID
        sorted_ids = sorted(pivot_data_num.columns, key=_id_sort_key)
        pivot_data_num = pivot_data_num[sorted_ids]

        if 'StatusStr' in group_subset.columns:
            pivot_data_str = group_subset.pivot(index='Variables', columns='ID', values='StatusStr').fillna('NA')
            pivot_data_str = pivot_data_str.reindex(pivot_data_num.index)[sorted_ids]
        else:
            pivot_data_str = pivot_data_num.map(lambda x: num_to_status[x])

        n_subjects = len(pivot_data_num.columns)
        n_variables = len(pivot_data_num.index)

        max_subjects = max(max_subjects, n_subjects)

        # Create coordinates
        x_coords = list(range(n_subjects))
        y_coords = list(range(n_variables))

        # Hover text: subject, session and run per column, then variable and status per cell
        first_rows = group_subset.drop_duplicates('ID').set_index('ID').loc[sorted_ids]
        subjects = [f"Subject: {id_val}" for id_val in sorted_ids]
        if 'session' in first_rows.columns:
            subjects = [f"{s}<br>Session: {format_session(v)}" for s, v in zip(subjects, first_rows['session'])]
        if 'run' in first_rows.columns:
            subjects = [f"{s}<br>Run: {int(v)}" for s, v in zip(subjects, first_rows['run'])]
        var_labels = [variable_labels.get(var, var) for var in pivot_data_str.index]
        statuses = pivot_data_str.to_numpy()
        cell_hover = [f"{subject}<br>Variable: {label}<br>Status: {status}"
                      for label, row in zip(var_labels, statuses) for subject, status in zip(subjects, row)]

        # Build square-marker grid (discrete colors, no interpolation)
        # A 2 px gap between cells, as the plot area gives each cell exactly cell_size
        marker_size = max(6, cell_size - 2)
        cell_colors = [status_colors.get(int(num), status_colors[0]) for num in pivot_data_num.to_numpy().ravel()]
        traces.append(dict(
            type="scatter",
            x=np.tile(np.arange(n_subjects), n_variables).tolist(),
            y=np.repeat(np.arange(n_variables), n_subjects).tolist(),
            mode="markers",
            marker=dict(symbol="square", size=marker_size,
                        color=cell_colors, line=dict(width=0)),
            text=cell_hover,
            hovertemplate="%{text}<extra></extra>",
            showlegend=False,
            # make_subplots numbers the axes of a one-column grid by row
            xaxis="x" if i == 1 else f"x{i}",
            yaxis="y" if i == 1 else f"y{i}",
        ))

        # Update axes
        fig.update_xaxes(
            tickmode="array",
            tickvals=x_coords,
            ticktext=pivot_data_num.columns,
            tickangle=45,
            showline=False,
            showgrid=False,
            zeroline=False,
            range=[-0.5, n_subjects - 0.5],
            row=i, col=1
        )

        fig.update_yaxes(
            tickmode="array",
            tickvals=y_coords,
            ticktext=[variable_labels.get(v, v) for v in pivot_data_num.index],
            showline=False,
            showgrid=False,
            zeroline=False,
            range=[n_variables - 0.5, -0.5],
            row=i, col=1
        )

    # Every panel spaces its cells as the widest one does
    fig.update_xaxes(range=[-0.5, max_subjects - 0.5])

    # The plot area is cell_size per subject; the margins hold the row labels and the last tilted tick
    fig_width = cell_size * max_subjects + 50 + label_px
    fig_height = plot_height + 100

    fig.update_layout(
        title=title,
        height=fig_height,
        width=fig_width,
        margin=dict(t=50, b=50, l=label_px, r=50),
        font=dict(size=10, color='#444'),
        plot_bgcolor='#ffffff'
    )

    # Plotly would validate every cell's color and text one by one, which dominated the time on large tables
    return go.Figure(data=traces, layout=fig.layout, _validate=False)

def _lollipop_groups(data, group_by):
    """Split lollipop data into (title, subset) panels. Falls back to a single panel."""
    if isinstance(group_by, str):
        group_by = [group_by]
    cols = [c for c in (group_by or []) if c in data.columns]
    if not cols:
        return [("", data)]

    combos = data[cols].drop_duplicates().sort_values(cols)
    groups = []
    for _, combo in combos.iterrows():
        mask = pd.Series(True, index=data.index)
        parts = []
        for c in cols:
            mask &= data[c] == combo[c]
            if c == "session":
                parts.append(f"Session {format_session(combo[c])}")
            elif c == "run":
                parts.append(f"Run {int(combo[c])}")
            else:
                parts.append(f"{c} {combo[c]}")
        groups.append((" - ".join(parts), data[mask]))
    return groups


def _add_lollipop_panel(fig, data, row, show_legend):
    """Add lollipop markers + stems for one panel, with x ordered within the panel."""
    d = data.copy()
    d["ID_int"] = pd.to_numeric(d["ID"], errors="coerce")
    d = d.sort_values(["Variable", "ID_int"]).reset_index(drop=True)
    d["x_pos"] = range(1, len(d) + 1)

    for i, var in enumerate(d["Variable"].unique()):
        color = _LOLLIPOP_COLORS[i % len(_LOLLIPOP_COLORS)]
        var_data = d[d["Variable"] == var]
        x_jittered = var_data["x_pos"] + np.random.uniform(-0.15, 0.15, len(var_data))

        # Stems: one trace per variable, segments separated by None
        stem_x, stem_y = [], []
        for xj, val in zip(x_jittered, var_data["Value"]):
            stem_x += [xj, xj, None]
            stem_y += [0, val, None]
        fig.add_trace(go.Scatter(
            x=stem_x,
            y=stem_y,
            mode="lines",
            line=dict(color=color, width=1),
            legendgroup=var,
            showlegend=False,
            hoverinfo="skip"
        ), row=row, col=1)

        fig.add_trace(go.Scatter(
            x=x_jittered,
            y=var_data["Value"],
            mode="markers",
            marker=dict(size=8, color=color),
            name=var,
            legendgroup=var,
            showlegend=show_legend,
            hovertemplate='<b>ID:</b> %{customdata[0]}<br>' +
                         '<b>Value:</b> %{y}<br>' +
                         '<b>Variable:</b> %{customdata[1]}<br>' +
                         '<b>Mean:</b> %{customdata[2]:.4f}<extra></extra>',
            customdata=var_data[["ID", "Variable", "mean_value"]].values
        ), row=row, col=1)


def create_lollipop_plot(data, group_by=None):
    """
    Create lollipop chart for standardized variables.
    If group_by columns (e.g. session/run) are present, draw one stacked panel per group.
    """
    if data is None or len(data) == 0:
        return go.Figure()

    groups = _lollipop_groups(data, group_by)
    n = len(groups)

    fig = make_subplots(
        rows=n, cols=1,
        subplot_titles=[title for title, _ in groups],
        vertical_spacing=(0.15 / (n - 1)) if n > 1 else 0.15
    )

    for i, (_, group_subset) in enumerate(groups, start=1):
        _add_lollipop_panel(fig, group_subset, row=i, show_legend=(i == 1))
        fig.update_xaxes(title_text="Variables", showgrid=True, zeroline=True, row=i, col=1)
        fig.update_yaxes(title_text="Standardized Value", showgrid=True,
                         zeroline=True, zerolinewidth=2, row=i, col=1)

    fig.update_layout(
        title="",
        height=max(400, 380 * n),
        hovermode="closest",
        template="plotly_white",
        margin=dict(t=60, b=60, l=60, r=60),
        hoverlabel=dict(bgcolor="rgb(40, 40, 40)", font=dict(size=10, color="white"))
    )

    return fig