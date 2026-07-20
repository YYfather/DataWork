import pandas as pd

from datawork.application.analysis_service import AnalysisService, ExecutionContext
from datawork.application.dataset_service import DatasetService
from datawork.core.plan import AnalysisPlan
from datawork.core.provenance import canonical_json_hash, dataframe_hash


CSV = b"group,value\nA,1\nA,2\nA,3\nB,3\nB,4\nB,5\n"


def test_hashes_are_stable_and_execution_records_environment():
    frame = pd.DataFrame({"group": ["A", "A", "A", "B", "B", "B"], "value": [1, 2, 4, 3, 5, 8]})
    assert dataframe_hash(frame) == dataframe_hash(frame.copy())

    plan = AnalysisPlan(
        dependent_variables=["value"],
        fixed_factors=["group"],
        method="welch_ttest",
    )
    execution = AnalysisService().execute(frame, plan)
    assert execution.provenance.plan_sha256 == canonical_json_hash(plan)
    assert execution.provenance.dataset.cleaned_sha256 == dataframe_hash(frame)
    assert execution.provenance.environment.python_version
    assert execution.result.provenance["reproducibility"]["run_id"] == execution.run_id


def test_dataset_service_records_source_and_cleaning_fingerprints():
    loaded = DatasetService().load_bytes(CSV, "sample.csv")
    assert loaded.fingerprint.source_size_bytes == len(CSV)
    assert loaded.fingerprint.n_rows == 6
    assert loaded.cleaning_log[0].operation == "conservative_clean"
