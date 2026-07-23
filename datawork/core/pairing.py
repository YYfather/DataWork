"""Strict treatment/control pairing and pair-derived column calculation."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import numpy as np
import pandas as pd

from .formula import evaluate_formula, formula_references
from .splitting import build_split_groups

if TYPE_CHECKING:
    from .plan import AnalysisPlan, PairDerivedColumn, PairingPlan


_SOURCE_POSITION = "__dw_source_position"
_SOURCE_INDEX = "__dw_source_index"
_MAPPING_INDEX = "__dw_mapping_index"
_PAIR_KEY = "__dw_pair_key"
_PAIR_SEQUENCE = "__dw_pair_sequence"
_TREATMENT_POSITION = "__dw_treatment_source_row"
_CONTROL_POSITION = "__dw_control_source_row"
_TREATMENT_LEVEL = "__dw_pair_treatment_level"
_CONTROL_LEVEL = "__dw_pair_control_level"
_PAIR_STATUS = "__dw_pair_status"
_RESERVED_COLUMNS = {
    _SOURCE_POSITION,
    _SOURCE_INDEX,
    _MAPPING_INDEX,
    _PAIR_KEY,
    _PAIR_SEQUENCE,
    _TREATMENT_POSITION,
    _CONTROL_POSITION,
    _TREATMENT_LEVEL,
    _CONTROL_LEVEL,
    _PAIR_STATUS,
}


def apply_pairing(
    df: pd.DataFrame,
    plan: "AnalysisPlan",
) -> tuple[pd.DataFrame, dict[str, Any] | None, list[str]]:
    """Build the treatment-centric one-row-per-pair analysis frame.

    Split rules first determine which mapped treatment rows are in scope.  Pair
    keys are nevertheless created from the immutable import order, so a table
    preview or result sort can never change the treatment/control correspondence.
    """
    pairing = plan.pairing
    if pairing is None:
        return df, None, []
    collisions = sorted(_RESERVED_COLUMNS & set(map(str, df.columns)))
    if collisions:
        raise ValueError(f"原始数据包含系统保留列名，无法安全配对: {collisions}")

    work = df.copy()
    work[_SOURCE_POSITION] = np.arange(len(work), dtype="int64")
    work[_SOURCE_INDEX] = [str(item) for item in df.index]
    work = work.set_index(_SOURCE_POSITION, drop=False)
    work.index.name = None
    generated_names = {item.name for item in pairing.derived_columns}
    name_collisions = sorted(generated_names & set(map(str, df.columns)))
    if name_collisions:
        raise ValueError(f"配对计算列不能覆盖原始列: {name_collisions}")
    group_values = _normalized_text(work[pairing.group_column])
    treatment_to_mapping = {
        mapping.treatment: index for index, mapping in enumerate(pairing.mappings)
    }
    control_to_mapping = {
        mapping.control: index for index, mapping in enumerate(pairing.mappings)
    }
    treatment_mask = group_values.isin(treatment_to_mapping)
    control_mask = group_values.isin(control_to_mapping)
    treatments = work.loc[treatment_mask].copy()
    controls = work.loc[control_mask].copy()
    treatments[_MAPPING_INDEX] = group_values.loc[treatments.index].map(treatment_to_mapping)
    controls[_MAPPING_INDEX] = group_values.loc[controls.index].map(control_to_mapping)

    if treatments.empty:
        raise ValueError("当前分析范围内没有任何已映射处理行")

    scoped_positions = _scoped_treatment_positions(treatments, plan)
    scoped_treatments = treatments.loc[treatments.index.isin(scoped_positions)].copy()
    if scoped_treatments.empty:
        raise ValueError("自定义拆分规则排除后，没有已映射处理行可用于配对")

    missing_mappings = [
        mapping.treatment
        for index, mapping in enumerate(pairing.mappings)
        if not bool((scoped_treatments[_MAPPING_INDEX] == index).any())
    ]
    if missing_mappings:
        raise ValueError(f"当前分析范围缺少已配置处理水平: {missing_mappings}")

    key_columns = [*pairing.match_columns, _MAPPING_INDEX]
    if pairing.match_columns:
        missing_treatment_keys = int(scoped_treatments[pairing.match_columns].isna().any(axis=1).sum())
        if missing_treatment_keys:
            raise ValueError(f"有 {missing_treatment_keys} 条处理记录的匹配标签缺失")
    scoped_key_frame = scoped_treatments[key_columns].drop_duplicates()
    relevant_controls = controls.merge(scoped_key_frame, on=key_columns, how="inner")
    if relevant_controls.empty:
        raise ValueError("当前分析范围内没有与已映射处理行对应的对照行")
    if pairing.match_columns:
        missing_control_keys = int(relevant_controls[pairing.match_columns].isna().any(axis=1).sum())
        if missing_control_keys:
            raise ValueError(f"有 {missing_control_keys} 条对照记录的匹配标签缺失")

    treatments = _assign_pair_key(scoped_treatments, pairing, key_columns, side="处理")
    controls = _assign_pair_key(relevant_controls, pairing, key_columns, side="对照")
    join_columns = [*key_columns, _PAIR_KEY]
    _validate_pair_counts(treatments, controls, key_columns, pairing)

    control_payload = controls[join_columns + [_SOURCE_POSITION]].copy()
    control_payload = control_payload.rename(columns={_SOURCE_POSITION: _CONTROL_POSITION})
    paired = treatments.merge(
        control_payload,
        on=join_columns,
        how="left",
        validate="one_to_one",
    )
    if paired[_CONTROL_POSITION].isna().any():
        missing_count = int(paired[_CONTROL_POSITION].isna().sum())
        raise ValueError(f"有 {missing_count} 条处理记录未找到唯一对照，整次分析已停止")

    control_lookup = controls.set_index(_SOURCE_POSITION, drop=False)
    paired = paired.sort_values(_SOURCE_POSITION, kind="stable").reset_index(drop=True)
    paired = paired.rename(columns={_SOURCE_POSITION: _TREATMENT_POSITION})
    paired[_TREATMENT_LEVEL] = paired[_MAPPING_INDEX].map(
        {index: item.treatment for index, item in enumerate(pairing.mappings)}
    )
    paired[_CONTROL_LEVEL] = paired[_MAPPING_INDEX].map(
        {index: item.control for index, item in enumerate(pairing.mappings)}
    )
    paired[_PAIR_SEQUENCE] = paired[_PAIR_KEY]
    paired[_PAIR_STATUS] = "matched"

    logs: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, definition in enumerate(pairing.derived_columns, start=1):
        paired, item_log, item_warnings = _calculate_pair_column(
            paired,
            control_lookup,
            definition,
            control_storage_column=f"__dw_control_value_{index}",
        )
        logs.append(item_log)
        warnings.extend(item_warnings)

    mapped_mask = treatment_mask | control_mask
    unassigned_count = int(treatment_mask.sum()) - int(len(scoped_treatments))
    audit: dict[str, Any] = {
        "operation": "pairing",
        "input_rows": int(len(df)),
        "mapped_treatment_rows": int(treatment_mask.sum()),
        "mapped_control_rows": int(control_mask.sum()),
        "unmapped_excluded_rows": int((~mapped_mask).sum()),
        "split_scope_excluded_treatment_rows": unassigned_count,
        "scoped_treatment_rows": int(len(scoped_treatments)),
        "pairing_group_count": int(scoped_treatments[key_columns].drop_duplicates().shape[0]),
        "successful_pairs": int(len(paired)),
        "group_column": pairing.group_column,
        "mappings": [item.model_dump(mode="json") for item in pairing.mappings],
        "match_columns": list(pairing.match_columns),
        "pairing_order": (
            f"显式样本 ID：{pairing.pair_id_column}"
            if pairing.pair_id_column
            else "按匹配组内原始导入行顺序"
        ),
        "pair_id_column": pairing.pair_id_column,
        "generated_columns": logs,
    }
    paired = paired.drop(columns=[_MAPPING_INDEX], errors="ignore")
    return paired, audit, list(dict.fromkeys(warnings))


def _scoped_treatment_positions(treatments: pd.DataFrame, plan: "AnalysisPlan") -> set[int]:
    if not plan.split_by:
        return set(int(item) for item in treatments.index)
    assigned: set[int] = set()
    for _labels, subset in build_split_groups(treatments, plan):
        assigned.update(int(item) for item in subset.index)
    return assigned


def _assign_pair_key(
    frame: pd.DataFrame,
    pairing: "PairingPlan",
    key_columns: list[str],
    *,
    side: str,
) -> pd.DataFrame:
    result = frame.sort_values(_SOURCE_POSITION, kind="stable").copy()
    if pairing.pair_id_column:
        values = _normalized_text(result[pairing.pair_id_column])
        if values.isna().any() or bool(values.eq("").any()):
            raise ValueError(f"{side}侧显式样本 ID 存在缺失值")
        result[_PAIR_KEY] = values
        duplicated = result.duplicated([*key_columns, _PAIR_KEY], keep=False)
        if duplicated.any():
            sample = result.loc[duplicated, [*key_columns, _PAIR_KEY]].head(10).to_dict("records")
            raise ValueError(f"{side}侧显式样本 ID 在匹配组内重复: {sample}")
    else:
        result[_PAIR_KEY] = result.groupby(key_columns, dropna=False, sort=False).cumcount() + 1
    return result


def _validate_pair_counts(
    treatments: pd.DataFrame,
    controls: pd.DataFrame,
    key_columns: list[str],
    pairing: "PairingPlan",
) -> None:
    treatment_counts = treatments.groupby(key_columns, dropna=False, sort=False).size().rename("treatment_count")
    control_counts = controls.groupby(key_columns, dropna=False, sort=False).size().rename("control_count")
    counts = treatment_counts.to_frame().join(control_counts, how="outer").fillna(0).astype(int)
    mismatch = counts[counts["treatment_count"] != counts["control_count"]]
    if not mismatch.empty:
        details = _readable_count_records(mismatch.reset_index(), pairing)
        raise ValueError(f"处理与对照样本数不一致，整次分析已停止: {details[:20]}")
    treatment_keys = set(map(tuple, treatments[[*key_columns, _PAIR_KEY]].itertuples(index=False, name=None)))
    control_keys = set(map(tuple, controls[[*key_columns, _PAIR_KEY]].itertuples(index=False, name=None)))
    if treatment_keys != control_keys:
        missing_control = len(treatment_keys - control_keys)
        missing_treatment = len(control_keys - treatment_keys)
        raise ValueError(
            "显式样本 ID 无法一一对应，整次分析已停止"
            f"（缺少对照 {missing_control}，缺少处理 {missing_treatment}）"
        )


def _readable_count_records(frame: pd.DataFrame, pairing: "PairingPlan") -> list[dict[str, Any]]:
    records = frame.to_dict("records")
    for record in records:
        mapping_index = int(record.pop(_MAPPING_INDEX))
        mapping = pairing.mappings[mapping_index]
        record["mapping"] = f"{mapping.treatment}→{mapping.control}"
    return records


def _calculate_pair_column(
    paired: pd.DataFrame,
    control_lookup: pd.DataFrame,
    definition: "PairDerivedColumn",
    *,
    control_storage_column: str,
) -> tuple[pd.DataFrame, dict[str, Any], list[str]]:
    treatment_values = pd.to_numeric(paired[definition.source_column], errors="coerce")
    control_values = pd.to_numeric(
        control_lookup.loc[paired[_CONTROL_POSITION].astype(int), definition.source_column],
        errors="coerce",
    )
    control_values.index = paired.index
    operands = pd.DataFrame({"处理值": treatment_values, "对照值": control_values}, index=paired.index)
    references = formula_references(definition.formula)
    if not references or not set(references).issubset({"处理值", "对照值"}):
        raise ValueError(
            f"配对计算列 {definition.name!r} 只能引用 [处理值] 和 [对照值]，且至少引用一个"
        )
    source_complete = operands[references].notna().all(axis=1)
    computed = evaluate_formula(
        operands,
        definition.formula,
        allowed_columns=["处理值", "对照值"],
        require_brackets=True,
        basic_arithmetic_only=True,
        allow_abs=True,
    )
    computed = pd.to_numeric(computed, errors="coerce").replace([np.inf, -np.inf], np.nan)
    computed = computed.round(definition.decimal_places)
    invalid_count = int((source_complete & computed.isna()).sum())
    missing_count = int(computed.isna().sum())
    if int(computed.notna().sum()) == 0:
        raise ValueError(f"配对计算列 {definition.name!r} 没有任何有效计算结果")
    result = paired.copy()
    result[control_storage_column] = control_values
    result[definition.name] = computed
    warnings = []
    if invalid_count:
        warnings.append(
            f"配对计算列 {definition.name!r} 有 {invalid_count} 行因除零、溢出或无效运算转为缺失值"
        )
    log = {
        "name": definition.name,
        "source_column": definition.source_column,
        "formula": definition.formula,
        "unit": definition.unit,
        "decimal_places": definition.decimal_places,
        "control_storage_column": control_storage_column,
        "missing_result_count": missing_count,
        "invalid_operation_count": invalid_count,
    }
    return result, log, warnings


def _normalized_text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip()
