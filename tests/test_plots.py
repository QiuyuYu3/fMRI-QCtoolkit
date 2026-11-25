import pandas as pd
from fMRI_QCtoolkit.utils.plots import create_heatmap, create_lollipop_plot, format_session


class TestCreateHeatmap:
    
    def test_creates_heatmap_with_valid_data(self, random_plot_data):
        """Test heatmap creation with random data"""
        variable_labels = {f'var{i+1}': f'Variable {i+1}' for i in range(len(random_plot_data['Variables'].unique()))}
        
        fig = create_heatmap(random_plot_data, variable_labels, title="Test Heatmap")
        
        assert fig is not None
        assert hasattr(fig, 'data')
    
    def test_handles_empty_data(self):
        """Test handling of empty data"""
        data = pd.DataFrame()
        variable_labels = {}
        
        fig = create_heatmap(data, variable_labels)
        
        # Should return figure with "No data" message
        assert fig is not None
    
    def test_groups_by_run(self, random_plot_data):
        """Test grouping by run with random data"""
        variable_labels = {f'var{i+1}': f'Var{i+1}' for i in range(len(random_plot_data['Variables'].unique()))}
        
        fig = create_heatmap(random_plot_data, variable_labels, group_by='run')
        
        assert fig is not None
        # Should create subplots for each run
        assert len(fig.data) > 0

    @staticmethod
    def _grid(ids, sessions, with_status_str=True):
        rows = []
        for session in sessions:
            for subject in ids:
                row = {'ID': subject, 'Variables': 'var1', 'Status': 3, 'session': session, 'run': 1}
                if with_status_str:
                    row['StatusStr'] = 'good'
                rows.append(row)
        return pd.DataFrame(rows)

    def test_alphanumeric_ids_sort_after_numeric(self):
        data = self._grid(['A01', '010', '9', 'pilot1'], ['01'])
        fig = create_heatmap(data, {}, group_by='session')
        assert list(fig.layout.xaxis.ticktext) == ['9', '010', 'A01', 'pilot1']

    def test_non_numeric_session_labels(self):
        data = self._grid(['001', '002'], ['pre', 'post'])
        fig = create_heatmap(data, {}, group_by=['session', 'run'])
        titles = [a.text for a in fig.layout.annotations]
        assert titles == ['Session post - Run 1', 'Session pre - Run 1']

    def test_without_status_strings(self):
        data = self._grid(['001', '002'], ['01'], with_status_str=False)
        fig = create_heatmap(data, {}, group_by='session')
        assert 'Status: good' in fig.data[0].text[0]

    @staticmethod
    def _two_variables(first, second):
        return pd.DataFrame([{'ID': '001', 'Variables': v, 'Status': 3, 'StatusStr': 'good',
                              'session': '01', 'run': 1} for v in (first, second)])

    def test_variables_are_listed_top_down_in_the_order_given(self):
        fig = create_heatmap(self._two_variables('zeta', 'alpha'), {'zeta': 'Zeta'}, group_by='session')
        assert list(fig.layout.yaxis.ticktext) == ['Zeta', 'alpha']
        low, high = fig.layout.yaxis.range
        assert low > high

    def test_long_labels_widen_the_figure_not_shrink_the_cells(self):
        data = self._two_variables('a', 'b')
        short = create_heatmap(data, {}, group_by='session')
        long = create_heatmap(data, {'a': 'Max Censored Displacement'}, group_by='session')
        assert long.layout.width - long.layout.margin.l == short.layout.width - short.layout.margin.l
        assert long.layout.margin.l > short.layout.margin.l


class TestCreateLollipopPlot:
    
    def test_creates_lollipop_with_valid_data(self, random_lollipop_data):
        """Test lollipop plot creation with random data"""
        fig = create_lollipop_plot(random_lollipop_data)
        
        assert fig is not None
        assert hasattr(fig, 'data')
        assert len(fig.data) > 0
    
    def test_handles_multiple_variables(self, random_lollipop_data):
        """Test handling multiple variables with random data"""
        fig = create_lollipop_plot(random_lollipop_data)
        
        assert fig is not None
        # Should create traces for each variable
        assert len(fig.data) > 2

class TestFormatSession:
    """BIDS session labels need not be numeric."""

    def test_numeric_labels_keep_zero_padding(self):
        assert format_session("01") == "01"
        assert format_session("1") == "01"
        assert format_session(1) == "01"

    def test_non_numeric_labels_pass_through(self):
        assert format_session("pre") == "pre"
        assert format_session("V1") == "V1"
