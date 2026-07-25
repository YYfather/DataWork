from pathlib import Path

from scripts.run_golden_validation import validate_suite


def test_frozen_golden_dataset_suite_matches_independent_references():
    root = Path(__file__).resolve().parents[2]
    case_count, check_count, failures = validate_suite(root)
    assert case_count >= 50
    assert not failures, "\n".join(
        f"{item.case_id}: {item.message}; actual={item.actual!r}; check={item.check!r}"
        for item in failures[:30]
    )
    assert check_count >= 400
