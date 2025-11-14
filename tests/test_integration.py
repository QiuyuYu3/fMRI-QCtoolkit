from fMRI_QCtoolkit.data.afni_pipeline import AFNIPipeline
from fMRI_QCtoolkit.data.fmriprep_pipeline import FMRIPrepPipeline


class TestAFNIIntegration:
    
    def test_full_afni_pipeline(self, mock_afni_directory):
        output_dir = mock_afni_directory / "output"
        
        pipeline = AFNIPipeline(
            input_dir=mock_afni_directory,
            task="rest",
            prefix="sub-",
            output_dir=output_dir
        )

        pipeline.process()

        assert (output_dir / "df_final.csv").exists()
        assert (output_dir / "lollipop_chart_data.csv").exists()

        assert pipeline.df_final is not None
        assert len(pipeline.df_final) > 0
        assert pipeline.lollipop_chart_data is not None
    
    def test_reload_saved_data(self, mock_afni_directory):
        output_dir = mock_afni_directory / "output"

        pipeline1 = AFNIPipeline(
            input_dir=mock_afni_directory,
            task="rest",
            prefix="sub-",
            output_dir=output_dir
        )
        pipeline1.process()

        pipeline2 = AFNIPipeline.from_saved_data(
            data_file=output_dir / "df_final.csv",
            lollipop_file=output_dir / "lollipop_chart_data.csv",
            task="rest"
        )

        assert len(pipeline1.df_final) == len(pipeline2.df_final)
        assert list(pipeline1.df_final.columns) == list(pipeline2.df_final.columns)


class TestFMRIPrepIntegration:
    
    def test_full_fmriprep_pipeline(self, temp_dir, random_bold_data, random_rating_data):
        """Test complete fMRIPrep pipeline with random data"""
        bold_file = temp_dir / "group_bold.tsv"
        rating_dir = temp_dir / "ratings"
        output_dir = temp_dir / "output"
        rating_dir.mkdir()
        
        # Use random BOLD data
        random_bold_data.to_csv(bold_file, sep='\t', index=False)

        # Create rating CSV files for each subject
        for _, row in random_rating_data.iterrows():
            subject_id = row['ID']
            filename = f"sub-{subject_id}_rest.csv"
            (rating_dir / filename).write_text(row.to_frame().T.to_csv(index=False))

        pipeline = FMRIPrepPipeline(
            bold_file=bold_file,
            rating_dir=rating_dir,
            task="rest",
            output_dir=output_dir
        )
        pipeline.process()

        assert (output_dir / "df_final.csv").exists()
        assert (output_dir / "lollipop_chart_data.csv").exists()
        assert len(pipeline.df_final) > 0