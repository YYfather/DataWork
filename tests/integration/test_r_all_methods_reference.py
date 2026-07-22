from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.compare_all_methods_r import compare, locate_rscript


@pytest.mark.skipif(
    os.environ.get("DATAWORK_RUN_R_REFERENCE") != "1",
    reason="development-only R/Python cross-check; set DATAWORK_RUN_R_REFERENCE=1",
)
def test_every_runnable_method_matches_independent_r_reference() -> None:
    rscript = locate_rscript(os.environ.get("DATAWORK_RSCRIPT"))
    assert Path(rscript).exists()
    result = compare(rscript)
    assert result["methods"] == 47
    assert result["compared_fields"] >= 130
    assert result["passed"], result["failures"]
