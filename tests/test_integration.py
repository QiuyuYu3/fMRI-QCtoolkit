import warnings

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal

from fMRI_QCtoolkit.data.afni_pipeline import AFNIPipeline
from fMRI_QCtoolkit.data.base import read_csv_exact
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

        assert sorted(p.name for p in output_dir.iterdir()) == ["df_final.csv"]
        assert pipeline.df_final is not None
        assert len(pipeline.df_final) > 0
        assert not pipeline.get_lollipop_data().empty

    def test_reload_saved_data(self, mock_afni_directory):
        output_dir = mock_afni_directory / "output"

        pipeline1 = AFNIPipeline(
            input_dir=mock_afni_directory,
            task="rest",
            prefix="sub-",
            output_dir=output_dir
        )
        pipeline1.process()

        pipeline2 = AFNIPipeline.from_saved_data(data_file=output_dir / "df_final.csv", task="rest")

        assert len(pipeline1.df_final) == len(pipeline2.df_final)
        assert list(pipeline1.df_final.columns) == list(pipeline2.df_final.columns)
        assert_frame_equal(pipeline1.get_lollipop_data(), pipeline2.get_lollipop_data())


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

        assert sorted(p.name for p in output_dir.iterdir()) == ["df_final.csv"]
        assert len(pipeline.df_final) > 0


class TestSavedTableKeepsFullPrecision:
    """The dashboard recomputes the lollipop data from df_final.csv, so the file must not lose digits."""

    @staticmethod
    def _run_prep(temp_dir, random_bold_data, random_rating_data):
        bold_file = temp_dir / "group_bold.tsv"
        rating_dir = temp_dir / "ratings"
        rating_dir.mkdir()
        random_bold_data.to_csv(bold_file, sep='\t', index=False)
        for _, row in random_rating_data.iterrows():
            (rating_dir / f"sub-{row['ID']}_rest.csv").write_text(row.to_frame().T.to_csv(index=False))
        pipeline = FMRIPrepPipeline(bold_file=bold_file, rating_dir=rating_dir, task="rest",
                                    output_dir=temp_dir / "output")
        return pipeline.process()

    def test_values_are_not_rounded(self, temp_dir, random_bold_data, random_rating_data):
        pipeline = self._run_prep(temp_dir, random_bold_data, random_rating_data)

        saved = read_csv_exact(temp_dir / "output" / "df_final.csv")

        assert (saved["gsr_x"].dropna().round(3) != saved["gsr_x"].dropna()).any()
        assert_series_equal(saved["gsr_x"], pipeline.df_final["gsr_x"].reset_index(drop=True),
                            check_exact=True)

    def test_reading_back_is_exact_and_raises_no_warning(self, temp_dir):
        values = np.random.default_rng(0).uniform(0, 0.01, 20_000)
        path = temp_dir / "values.csv"
        pd.DataFrame({"v": values}).to_csv(path, index=False)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            back = read_csv_exact(path)["v"].to_numpy()

        assert (back == values).all()

    def test_lollipop_from_the_file_equals_the_one_from_memory(self, temp_dir, random_bold_data,
                                                               random_rating_data):
        pipeline = self._run_prep(temp_dir, random_bold_data, random_rating_data)

        reloaded = FMRIPrepPipeline.from_saved_data(temp_dir / "output" / "df_final.csv", task="rest")

        assert_frame_equal(reloaded.get_lollipop_data().reset_index(drop=True),
                           pipeline.get_lollipop_data().reset_index(drop=True),
                           check_dtype=False)
