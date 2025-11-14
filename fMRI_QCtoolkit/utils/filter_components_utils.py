"""
Utility functions for generating filter components in dashboards (sidebars)
"""

from dash import dcc, html
import pandas as pd

def create_quantitative_slider(var, label, min_val, max_val, default_val, step):
    """Create a quantitative variable slider component."""

    # Ensure all values are JSON serializable (convert numpy types to Python types)
    min_val = float(min_val) if pd.notna(min_val) else 0.0
    max_val = float(max_val) if pd.notna(max_val) else 1.0

    step = float(step) if pd.notna(step) else 0.01
    
    default_val = [float(default_val[0]), float(default_val[1])]
    
    # Create string keys for marks dictionary
    marks_dict = {
        str(min_val): f'{min_val:.2f}',
        str(max_val): f'{max_val:.2f}'
    }
    
    return html.Div([
        html.Label(label, style={'font-weight': 'bold'}),
        dcc.RangeSlider(
            id=f'{var}_slider',
            min=min_val,
            max=max_val,
            value=default_val,
            step=step,
            marks=marks_dict,
            tooltip={'placement': 'bottom', 'always_visible': True}
        ),
        dcc.Checklist(
            id=f'{var}_na',
            options=[{'label': 'Include NA', 'value': 'include_na'}],
            value=['include_na'],
            style={'margin-top': '5px'}
        )
    ], style={'margin-bottom': '15px'})


def create_qualitative_dropdown(group, options, defaults):
    """Create a qualitative variable dropdown component."""
    return html.Div([
        html.Label(group.replace('_', ' ').title(), style={'font-weight': 'bold'}),
        dcc.Dropdown(
            id=f'{group}_dropdown',
            options=options,
            value=defaults,
            multi=True,
            style={'font-size': '12px'}
        )
    ], style={'margin-bottom': '10px'})


def process_quantitative_configs(df, quantitative_configs):
    """
    Process quantitative variable configurations to prepare slider parameters.

    Determines the actual min and max values for the slider based on either:
      * The provided min_value/max_value_offset in the configuration, or
      * The data's minimum/maximum values with an offset (±0.1 or ±1, depends on stepsize).
    - Sets the default range to [min, max] if not explicitly defined.
    - Returns a list of tuples that can be passed to slider creation functions.
    """
    quant_configs = []
    
    for config in quantitative_configs:
        var = config["variable"]
        if var in df.columns:

            label = config["label"]
            min_val = config["min_value"]
            max_offset = config["max_value_offset"]
            default_range = config["default_range"]
            step = config["step"]
            
            # Offset rule: use 0.1 for step < 1, and 1 for step >= 1
            offset = 0.1 if step < 1 else 1

            if min_val is None:
                actual_min = df[var].min() - offset
            else:
                actual_min = min_val

            if max_offset is None:
                actual_max = df[var].max() + offset
            else:
                actual_max = df[var].max() + max_offset
                
            # If default_range is None, use the full [min, max] range
            if default_range is None:
                default_range = [actual_min, actual_max]
                
            quant_configs.append((var, label, actual_min, actual_max, default_range, step))
    
    return quant_configs


def create_fraction_sliders(df, frac_defaults):
    """Create fraction TRs censored sliders (AFNI-specific)."""
    components = []
    frac_cols = [col for col in df.columns if col.startswith("frac_TRs_cens_")]
    
    for col in frac_cols:
        label_text = col.replace("_", " ").title()
        components.append(
            html.Div([
                html.Label(label_text, style={'font-weight': 'bold'}),
                dcc.RangeSlider(
                    id=f"{col}_slider",
                    min=0,
                    max=1,
                    value=frac_defaults["range"],
                    step=frac_defaults["step"],
                    marks=frac_defaults["marks"],
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
    
    return components


def generate_filter_components(df, processor, config, include_fraction_sliders=False):
    """
    Generate filter components for dashboards.
    """
    components = []
    
    # Quantitative variable sliders
    quant_configs = process_quantitative_configs(df, config["quantitative_configs"])
    
    for var, label, min_val, max_val, default_val, step in quant_configs:
        components.append(create_quantitative_slider(var, label, min_val, max_val, default_val, step))
    
    # Fraction TRs censored sliders (AFNI-specific)
    if include_fraction_sliders and "frac_trs_defaults" in config:
        components.extend(create_fraction_sliders(df, config["frac_trs_defaults"]))
    
    # Qualitative variable dropdowns
    for group in processor.checkbox_groups:
        components.append(
            create_qualitative_dropdown(
                group, 
                config["qualitative_options"], 
                config["qualitative_defaults"]
            )
        )
    
    return components