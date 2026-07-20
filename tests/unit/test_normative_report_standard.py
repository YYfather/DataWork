from datawork.application.ai_assistant_service import (
    _deterministic_normative_report,
    _ordered_comparisons_from_result,
    _render_normative_report,
)


def test_ordering_prioritizes_significance_then_emm_then_descriptive_means():
    execution = {
        "kind": "single",
        "result": {
            "significance_letters": [
                {"factor": "处理", "method": "Tukey", "group": "A", "mean": 10.0, "letters": "a"},
                {"factor": "处理", "method": "Tukey", "group": "B", "mean": 5.0, "letters": "b"},
            ],
            "estimated_marginal_means": [
                {"group": "C", "mean": 8.0, "levels": {"品种": "C"}},
                {"group": "D", "mean": 7.0, "levels": {"品种": "D"}},
            ],
            "descriptive_stats": [
                {"group": "E", "mean": 6.0},
                {"group": "F", "mean": 4.0},
            ],
        },
    }

    ordered = _ordered_comparisons_from_result(execution)

    assert "显著性层级" in ordered[0]
    assert next(index for index, item in enumerate(ordered) if "Tukey对应的估计值" in item) < next(
        index for index, item in enumerate(ordered) if "估计边际均值" in item
    )
    assert next(index for index, item in enumerate(ordered) if "估计边际均值" in item) < next(
        index for index, item in enumerate(ordered) if "描述性均值" in item
    )


def test_batch_normative_report_keeps_every_table_row_without_repeating_rows_in_prose():
    overview = [
        {
            "task_id": 1,
            "effect": f"检验{i}",
            "p_value": 0.5,
            "p_adjusted_across_tasks": 0.5,
            "conclusion": "校正后不显著",
        }
        for i in range(501)
    ]
    contrasts = [
        {
            "contrast": f"水平{i} vs 对照",
            "estimate": float(i),
            "p_value": 0.2,
            "p_adjusted": 0.2,
            "correction": "holm",
        }
        for i in range(25)
    ]
    execution = {
        "kind": "batch",
        "result": {
            "method": "threeway_anova",
            "settings": {"cross_model_p_adjust": "holm"},
            "results": [
                {
                    "subset_key": "年份=2024",
                    "subset_info": {"task_id": 1, "年份": "2024"},
                    "n_rows": 30,
                    "error": "",
                    "result": {
                        "alpha": 0.05,
                        "method": {"label_zh": "三因素方差分析"},
                        "descriptive_stats": [{"group": "2024", "n": 30, "mean": 8.2, "sd": 1.1}],
                        "omnibus_tests": [
                            {"effect": "A", "df_num": 1, "df_den": 22, "f_value": 1.2, "p_value": 0.28, "eta_sq_p": 0.05, "is_significant": False},
                            {"effect": "A × B × C", "df_num": 1, "df_den": 22, "f_value": 5.2, "p_value": 0.03, "eta_sq_p": 0.19, "is_significant": True},
                            {"effect": "A × B", "df_num": 1, "df_den": 22, "f_value": 2.2, "p_value": 0.15, "eta_sq_p": 0.09, "is_significant": False},
                        ],
                        "contrasts": contrasts,
                    },
                }
            ],
            "overview": overview,
        },
    }

    report = _deterministic_normative_report(execution, title="完整批次规范报告")

    assert len(report.tables) == 3
    assert len(report.tables[0].rows) == 1
    assert "记录类型" not in report.tables[0].columns
    assert "效应量值" not in report.tables[0].columns
    assert len(report.tables[1].rows) == 504
    assert "效应量（含区间）" in report.tables[1].columns
    assert sum("补充效应量" in row for row in report.tables[1].rows) == 3
    contrast_table = report.tables[2]
    assert len(contrast_table.rows) == 25
    inference = "\n".join(report.inferential_results)
    assert len(report.inferential_results) <= 3
    assert "正文不逐任务复制 p 值" in inference
    assert "交互、主效应和父子检验层级仍由本地规范规则控制" in inference
    assert "A × B × C达到" not in inference
    assert len(report.descriptive_statistics) == 1
    assert "年份=2024" not in report.descriptive_statistics[0]


def test_batch_effect_sizes_merge_into_same_task_condition_and_effect_row():
    execution = {
        "kind": "batch",
        "result": {
            "method": "twoway_anova",
            "split_cols": ["脱叶剂喷施时间"],
            "settings": {"cross_model_p_adjust": "holm"},
            "results": [
                {
                    "subset_key": "task_id=1, 脱叶剂喷施时间=CK1",
                    "subset_info": {"task_id": 1, "脱叶剂喷施时间": "CK1"},
                    "error": "",
                    "result": {
                        "method": {"label_zh": "双因素方差分析"},
                        "omnibus_tests": [
                            {
                                "effect": "品种",
                                "f_value": 8.262927,
                                "df_num": 1,
                                "df_den": 30,
                                "p_value": 0.007371,
                                "eta_sq": 0.0097,
                                "eta_sq_p": 0.0199,
                                "omega_sq": 0.0,
                            }
                        ],
                    },
                }
            ],
            # Legacy saved overviews did not retain task_id, but did retain the
            # split condition. Report generation must still recover the join.
            "overview": [
                {
                    "脱叶剂喷施时间": "CK1",
                    "effect": "品种",
                    "statistic_name": "F",
                    "statistic_value": 8.262927,
                    "df_num": 1,
                    "df_den": 30,
                    "p_value": 0.007371,
                    "raw_conclusion": "原始显著",
                    "p_adjusted_across_tasks": 0.007371,
                    "conclusion": "校正后显著",
                }
            ],
        },
    }

    report = _deterministic_normative_report(execution, title="批量效应量合并")
    table = report.tables[1]

    assert len(table.rows) == 1
    row = dict(zip(table.columns, table.rows[0]))
    assert row["任务 ID"] == "1"
    assert row["任务条件"] == "脱叶剂喷施时间=CK1"
    assert row["效应"] == "品种"
    assert "η²=0.009700" in row["效应量（含区间）"]
    assert "偏 η²=0.019900" in row["效应量（含区间）"]
    assert "ω²=0.000000" in row["效应量（含区间）"]
    assert all("补充效应量" not in cell for cell in table.rows[0])


def test_single_factorial_report_explains_interactions_before_main_effects():
    execution = {
        "kind": "single",
        "result": {
            "method": {"label_zh": "双因素方差分析", "name": "twoway_anova"},
            "alpha": 0.05,
            "design": {
                "dependent_vars": ["y1", "y2"],
                "between_factors": ["A", "B"],
                "variables": [
                    {"name": "A", "levels": ["a1", "a2", "a3"], "n_unique": 3},
                    {"name": "B", "levels": ["b1", "b2"], "n_unique": 2},
                ],
            },
            "omnibus_tests": [
                {"effect": "年份", "df_num": 1, "df_den": 40, "f_value": 4.1, "p_value": 0.049, "eta_sq_p": 0.09, "is_significant": True},
                {"effect": "年份 × 品种", "df_num": 1, "df_den": 40, "f_value": 7.2, "p_value": 0.011, "eta_sq_p": 0.15, "is_significant": True},
            ],
        },
    }

    report = _deterministic_normative_report(execution, title="析因规范报告")
    inference = "\n".join(report.inferential_results)

    assert inference.index("年份 × 品种") < inference.index("年份达到")
    assert "受交互限定的主效应不作脱离条件的总体概括" in inference
    assert "简单效应" in inference


def test_normative_report_uses_requested_flow_and_writes_descriptives_into_prose():
    execution = {
        "kind": "single",
        "result": {
            "method": {"label_zh": "双因素方差分析", "name": "twoway_anova"},
            "design": {"between_factors": ["年份", "品种"], "dependent_vars": ["产量"]},
            "alpha": 0.05,
            "descriptive_stats": [
                {"年份": "2024", "品种": "A", "n": 12, "mean": 8.2, "sd": 1.1},
                {"年份": 2025, "品种": "A", "n": 12, "mean": 8.8, "sd": 1.0},
            ],
            "omnibus_tests": [
                {"effect": "年份 × 品种", "df_num": 1, "df_den": 44, "f_value": 0.85, "p_value": 0.433, "eta_sq_p": 0.03, "is_significant": False},
                {"effect": "年份", "df_num": 1, "df_den": 44, "f_value": 5.2, "p_value": 0.028, "eta_sq_p": 0.11, "is_significant": True},
            ],
        },
    }

    report = _deterministic_normative_report(execution, title="规范报告")
    markdown = _render_normative_report(report)

    assert any("年份=2024" in line and "M=8.2000" in line and "SD=1.1000" in line for line in report.descriptive_statistics)
    assert any("年份=2025" in line and "n=12" in line for line in report.descriptive_statistics)
    assert "偏 η²=0.0300" in "\n".join(report.inferential_results)
    assert markdown.index("## 二、描述性统计") < markdown.index("## 四、交互作用、主效应与整体检验")
    assert markdown.index("年份 × 品种未达到") < markdown.index("年份达到")
    assert "## 五、后续分析与具体差异" in markdown
    assert "## 六、效应量、结论与解释边界" in markdown


def test_three_way_report_blocks_nested_effects_and_untriggered_simple_effects():
    valid_simple = {
        "fixed_factor": "B × C", "fixed_level": "B=b1, C=c1",
        "effect": "A @ B=b1, C=c1", "df_num": 2, "df_den": 48,
        "f_value": 6.2, "p_value": 0.004, "p_adjusted": 0.012,
        "correction": "holm", "is_significant": True,
    }
    invalid_simple = {
        "fixed_factor": "B", "fixed_level": "B=b1",
        "effect": "A @ B=b1", "df_num": 2, "df_den": 48,
        "f_value": 5.8, "p_value": 0.006, "p_adjusted": 0.018,
        "correction": "holm", "is_significant": True,
    }
    execution = {
        "kind": "single",
        "result": {
            "method": {"name": "threeway_anova", "label_zh": "三因素方差分析"},
            "design": {
                "between_factors": ["A", "B", "C"],
                "variables": [
                    {"name": "A", "levels": ["a1", "a2", "a3"], "n_unique": 3},
                    {"name": "B", "levels": ["b1", "b2"], "n_unique": 2},
                    {"name": "C", "levels": ["c1", "c2"], "n_unique": 2},
                ],
            },
            "alpha": 0.05,
            "omnibus_tests": [
                {"effect": "A × B × C", "df_num": 2, "df_den": 48, "f_value": 7.1, "p_value": 0.002, "is_significant": True},
                {"effect": "A × B", "df_num": 2, "df_den": 48, "f_value": 4.9, "p_value": 0.011, "is_significant": True},
                {"effect": "A", "df_num": 2, "df_den": 48, "f_value": 8.0, "p_value": 0.001, "is_significant": True},
            ],
            "simple_effects": [valid_simple, invalid_simple],
            "contrasts": [
                {"contrast": "A @ B=b1, C=c1 | a1 - a2", "estimate": 1.4, "p_value": 0.003, "p_adjusted": 0.009, "correction": "holm", "significant": True},
                {"contrast": "A @ B=b1 | a1 - a2", "estimate": 1.2, "p_value": 0.004, "p_adjusted": 0.012, "correction": "holm", "significant": True},
            ],
        },
    }

    report = _deterministic_normative_report(execution, title="三因素规范报告")
    inference = "\n".join(report.inferential_results)
    follow_up = "\n".join(report.follow_up_results)

    assert "A × B达到统计显著" in inference
    assert "低阶交互受更高阶显著交互限定" in inference
    assert "A达到统计显著" in inference
    assert "主效应受更高阶显著交互限定" in inference
    assert "简单简单效应" in follow_up
    assert "A @ B=b1, C=c1 | a1 - a2" in follow_up
    assert "A @ B=b1 | a1 - a2" not in follow_up
    assert "没有显著交互" in follow_up


def test_manova_report_uses_primary_parent_test_and_blocks_bogus_follow_up():
    execution = {
        "kind": "single",
        "result": {
            "method": {"name": "twoway_manova", "label_zh": "双因素 MANOVA"},
            "data_snapshot": {"primary_multivariate_test": "pillai"},
            "design": {
                "between_factors": ["A", "B"],
                "dependent_vars": ["y1", "y2"],
                "variables": [
                    {"name": "A", "levels": ["a1", "a2", "a3"], "n_unique": 3},
                    {"name": "B", "levels": ["b1", "b2"], "n_unique": 2},
                ],
            },
            "alpha": 0.05,
            "descriptive_stats": [
                {"A": "a1", "B": "b1", "n": 12, "y1_mean": 8.2, "y1_sd": 1.1, "y2_mean": 6.3, "y2_sd": 0.9},
            ],
            "omnibus_tests": [
                {"effect": "A × B", "statistic_name": "Pillai 轨迹", "statistic_value": 0.08, "df_num": 2, "df_den": 44, "f_value": 1.9, "p_value": 0.16, "is_significant": False},
                {"effect": "A × B", "statistic_name": "Wilks' Lambda", "statistic_value": 0.75, "df_num": 2, "df_den": 44, "f_value": 6.2, "p_value": 0.004, "is_significant": True},
                {"effect": "A", "statistic_name": "Pillai 轨迹", "statistic_value": 0.22, "df_num": 4, "df_den": 88, "f_value": 3.1, "p_value": 0.02, "is_significant": True},
            ],
            "follow_up_tests": [
                {"outcome": "y1", "effect": "A × B", "df_num": 2, "df_den": 44, "f_value": 8.0, "p_value": 0.001, "p_adjusted": 0.003, "correction": "holm", "significant": True},
                {"outcome": "y1", "effect": "A", "df_num": 2, "df_den": 44, "f_value": 5.0, "p_value": 0.01, "p_adjusted": 0.03, "correction": "holm", "significant": True},
            ],
            "simple_effects": [
                {"fixed_factor": "B", "fixed_level": "B=b1", "effect": "[y1] A @ B=b1", "df_num": 2, "df_den": 42, "f_value": 7.0, "p_value": 0.003, "p_adjusted": 0.009, "correction": "holm", "is_significant": True},
            ],
            "contrasts": [
                {"contrast": "[y1 | A] a1 - a2", "estimate": 1.1, "p_value": 0.006, "p_adjusted": 0.018, "correction": "holm", "significant": True},
            ],
        },
    }

    report = _deterministic_normative_report(execution, title="MANOVA 规范报告")
    inference = "\n".join(report.inferential_results)
    follow_up = "\n".join(report.follow_up_results)

    assert "预先指定的Pillai 轨迹" in inference
    assert "Wilks' Lambda" not in inference
    assert "y1 的 A 单变量跟进" in follow_up
    assert "y1 的 A × B 单变量跟进" not in follow_up
    assert "[y1] A @ B=b1" not in follow_up
    assert "多变量父检验" in follow_up
    assert "[y1 | A] a1 - a2" in follow_up
    assert len(report.tables) == 3
    assert report.tables[0].title.startswith("表1. ")
    assert report.tables[0].columns == ["A", "B", "n", "y1", "y2"]
    assert report.tables[0].rows[0][-2:] == ["8.2000 ± 1.1000", "6.3000 ± 0.9000"]
    assert "Pillai 轨迹" in report.tables[1].title
    assert all("Wilks' Lambda" not in cell for row in report.tables[1].rows for cell in row)
    assert report.tables[2].title.startswith("表3. ")


def test_two_level_factor_is_not_written_as_posthoc_multiple_comparison():
    execution = {
        "kind": "single",
        "result": {
            "method": {"name": "twoway_anova", "label_zh": "双因素方差分析"},
            "design": {
                "between_factors": ["A", "B"],
                "variables": [
                    {"name": "A", "levels": ["a1", "a2"], "n_unique": 2},
                    {"name": "B", "levels": ["b1", "b2"], "n_unique": 2},
                ],
            },
            "alpha": 0.05,
            "omnibus_tests": [
                {"effect": "A × B", "df_num": 1, "df_den": 40, "f_value": 0.8, "p_value": 0.38, "is_significant": False},
                {"effect": "A", "df_num": 1, "df_den": 40, "f_value": 6.0, "p_value": 0.019, "is_significant": True},
            ],
            "contrasts": [
                {"contrast": "[A] a1 - a2", "estimate": 1.0, "p_value": 0.019, "p_adjusted": 0.019, "correction": "tukey", "significant": True},
            ],
        },
    }

    report = _deterministic_normative_report(execution, title="两水平因素报告")
    follow_up = "\n".join(report.follow_up_results)

    assert "[A] a1 - a2" not in follow_up
    assert "A仅含两个水平，不另写成事后多重比较" in follow_up
    assert len(report.tables) == 3
    contrast_table = next(table for table in report.tables if "事后比较" in table.title)
    assert any("[A] a1 - a2" in cell for row in contrast_table.rows for cell in row)


def test_none_correction_hides_legacy_adjusted_fields_from_normative_table():
    execution = {
        "kind": "batch",
        "result": {
            "method": "oneway_anova",
            "settings": {"cross_model_p_adjust": "none"},
            "results": [],
            "overview": [
                {
                    "task_id": 1,
                    "effect": "A",
                    "p_value": 0.02,
                    "significant": True,
                    # 模拟旧项目中遗留的伪“校正后”字段。
                    "p_adjusted_across_tasks": 0.02,
                    "significant_adjusted": True,
                    "conclusion": "校正后显著",
                }
            ],
        },
    }

    report = _deterministic_normative_report(execution, title="无跨任务校正报告")
    table = report.tables[1]

    assert "校正前显著性" in table.columns
    assert "跨任务校正 p" not in table.columns
    assert "结论" not in table.columns
    assert any("原始显著" in cell for row in table.rows for cell in row)
