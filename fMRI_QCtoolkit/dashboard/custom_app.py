"""Dashboard for a table prepared by 'fmriqc prep custom'."""

from .base_app import BaseDashboard
from .config import parse_config


class CustomDashboard(BaseDashboard):
    """Dashboard whose ratings, metrics and defaults come from the table's columns."""

    PIPELINE = 'custom'
    DEFAULTS_NOTE = "Every numeric column, without thresholds"

    def __init__(self, data_processor, *args, **kwargs):
        keys = [c for c in ('session', 'run') if c in data_processor.get_data().columns]
        self.GROUP_BY = keys if len(keys) == 2 else (keys[0] if keys else None)
        super().__init__(data_processor, *args, **kwargs)

    def packaged_config(self):
        return None

    def default_config(self):
        processor = self.processor
        return parse_config({"metrics": {column: {} for column in processor.vars},
                             "table_columns": list(processor.table_only)}, source="defaults")

    def rating_label(self, group):
        return group
