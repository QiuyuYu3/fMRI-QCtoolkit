import pandas as pd
from fMRI_QCtoolkit.utils.plots import create_heatmap, create_lollipop_plot


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