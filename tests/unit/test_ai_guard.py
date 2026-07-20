import json

from datawork.ai.guard import validate_all_reported_numbers, validate_statistical_values


RESULT = {
    "kind": "single",
    "result": {
        "omnibus_tests": [
            {"effect": "A:B", "df_num": 2, "df_den": 54, "f_value": 4.56, "p_value": 0.014, "eta_sq_p": 0.145}
        ]
    },
}


def test_guard_reads_nested_execution_envelope():
    text = "交互效应显著，F(2, 54)=4.56，p=0.014，η²p=0.145。"
    assert validate_statistical_values(text, json.dumps(RESULT)) == []


def test_guard_rejects_changed_p_and_effect_size():
    text = "交互效应显著，F(2, 54)=4.56，p=0.041，η²p=0.451。"
    violations = validate_statistical_values(text, json.dumps(RESULT))
    assert any("p 值不匹配" in item for item in violations)
    assert any("偏 η² 不匹配" in item for item in violations)


def test_guard_matches_same_df_rows_by_f_value():
    result = {
        "omnibus_tests": [
            {"effect": "A", "df_num": 2, "df_den": 54, "f_value": 0.85, "p_value": 0.433, "eta_sq_p": 0.03},
            {"effect": "A:B", "df_num": 2, "df_den": 54, "f_value": 4.56, "p_value": 0.014, "eta_sq_p": 0.145},
        ]
    }
    text = "A 未显著，F(2,54)=0.85，p=0.433；A:B 显著，F(2,54)=4.56，p=0.014。"
    assert validate_statistical_values(text, json.dumps(result)) == []


def test_strict_number_guard_rejects_untraceable_values():
    assert validate_all_reported_numbers("F(2,54)=9.99，p=0.014。", json.dumps(RESULT)) == [
        "[Guard R9] 报告数值 9.99 未在统计结果中找到可追溯来源"
    ]


def test_strict_number_guard_accepts_traceable_percentages_and_p_thresholds():
    text = "该效应 F(2,54)=4.56，p<0.05，偏 η²p=14.5%，置信水平为 95%。"
    assert validate_statistical_values(text, json.dumps(RESULT)) == []
    assert validate_all_reported_numbers(text, json.dumps(RESULT)) == []


def test_strict_number_guard_accepts_years_that_are_canonical_group_labels():
    result = {
        **RESULT,
        "grouping": {
            "factor": "年份",
            "levels": ["2024", "2025年"],
            "summaries": {"2024": {"mean": 4.2}, "2025": {"mean": 4.8}},
        },
    }
    text = "2024 与 2025 年是当前年份因素的两个观测水平。"
    assert validate_all_reported_numbers(text, json.dumps(result, ensure_ascii=False)) == []


def test_strict_number_guard_still_rejects_year_not_in_canonical_labels():
    result = {**RESULT, "grouping": {"factor": "年份", "levels": ["2024", "2025"]}}
    assert validate_all_reported_numbers("2026 年未出现在结果中。", json.dumps(result, ensure_ascii=False)) == [
        "[Guard R9] 报告数值 2026 未在统计结果中找到可追溯来源"
    ]


def test_strict_number_guard_accepts_years_inside_composite_group_labels():
    result = {
        **RESULT,
        "result": {
            **RESULT["result"],
            "estimated_marginal_means": [
                {"group": "年份=2024｜品种=XLZ48", "mean": 86.564},
                {"group": "年份=2025｜品种=XLZ48", "mean": 78.704},
            ],
        },
    }
    text = "2024 与 2025 是结果中的年份水平，估计均值分别为 86.56 与 78.70。"
    assert validate_all_reported_numbers(text, json.dumps(result, ensure_ascii=False)) == []


def test_strict_number_guard_discovers_numeric_labels_under_original_factor_column_names():
    result = {
        **RESULT,
        "result": {
            **RESULT["result"],
            "design": {"between_factors": ["年份", "处理"]},
            "descriptive_stats": [
                {"年份": "2024", "处理": "1", "mean": 86.564},
                {"年份": 2025, "处理": 2, "mean": 78.704},
            ],
        },
    }
    text = "年份水平为 2024 与 2025，处理水平为 1 与 2。"
    assert validate_all_reported_numbers(text, json.dumps(result, ensure_ascii=False)) == []


def test_strict_number_guard_accepts_numeric_labels_from_profile_value_fields():
    result = {
        **RESULT,
        "profile": {
            "columns": [
                {"name": "年份", "role": "between", "unique_values": ["2024", "2025"]}
            ]
        },
    }
    assert validate_all_reported_numbers(
        "年份包含 2024 和 2025 两个水平。", json.dumps(result, ensure_ascii=False)
    ) == []


def test_strict_number_guard_uses_numbers_from_deterministic_reference_evidence():
    source = {
        "canonical_result": RESULT,
        "deterministic_reference": {
            "descriptive_statistics": ["年份因素包含 2024 与 2025 两个水平。"]
        },
    }
    assert validate_all_reported_numbers(
        "分析比较了 2024 与 2025 两个年份水平。",
        json.dumps(source, ensure_ascii=False),
    ) == []


def test_strict_number_guard_accepts_conventional_rounding_at_float_boundary():
    result = {**RESULT, "pillai": 0.22149999999999998}
    assert validate_all_reported_numbers("Pillai=0.222。", json.dumps(result)) == []
