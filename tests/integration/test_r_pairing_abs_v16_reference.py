from __future__ import annotations

import os

import pytest

from scripts.compare_all_methods_r import locate_rscript
from scripts.compare_pairing_abs_r import compare


@pytest.mark.skipif(
    os.environ.get("DATAWORK_RUN_R_REFERENCE") != "1",
    reason="development-only R/Python V1.6 abs cross-check; set DATAWORK_RUN_R_REFERENCE=1",
)
def test_v16_pairing_absolute_value_matches_r() -> None:
    result = compare(locate_rscript(os.environ.get("DATAWORK_RSCRIPT")))
    assert result["cases"] == 6
    assert result["formulas"] == 4
    assert result["passed"], result["failures"]
