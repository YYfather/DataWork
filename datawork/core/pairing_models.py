"""Pydantic contracts for V1.6 pairing and joint-outcome task groups."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from .formula import normalize_absolute_value_syntax


class PairMapping(BaseModel):
    treatment: str
    control: str

    @field_validator("treatment", "control")
    @classmethod
    def _clean_level(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("处理和对照水平不能为空")
        return cleaned

    @model_validator(mode="after")
    def _different_levels(self) -> "PairMapping":
        if self.treatment == self.control:
            raise ValueError("处理水平与对照水平不能相同")
        return self


class PairDerivedColumn(BaseModel):
    id: str
    name: str
    source_column: str
    formula: str
    unit: str = ""
    decimal_places: int = Field(default=8, ge=0, le=8)

    @field_validator("id")
    @classmethod
    def _clean_id(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("配对计算列必须包含稳定内部标识")
        if len(cleaned) > 120:
            raise ValueError("配对计算列内部标识不能超过 120 个字符")
        return cleaned

    @field_validator("name", "source_column")
    @classmethod
    def _clean_column(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("配对计算列名称和来源指标不能为空")
        if len(cleaned) > 120:
            raise ValueError("配对计算列名称不能超过 120 个字符")
        return cleaned

    @field_validator("formula")
    @classmethod
    def _clean_formula(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("配对计算公式不能为空")
        if len(cleaned) > 10000:
            raise ValueError("配对计算公式不能超过 10000 个字符")
        normalized = normalize_absolute_value_syntax(cleaned)
        if len(normalized) > 10000:
            raise ValueError("配对计算公式规范化后不能超过 10000 个字符")
        return normalized

    @field_validator("unit")
    @classmethod
    def _clean_unit(cls, value: str) -> str:
        cleaned = str(value).strip()
        if len(cleaned) > 80:
            raise ValueError("配对计算列单位不能超过 80 个字符")
        return cleaned


class PairingPlan(BaseModel):
    group_column: str
    mappings: list[PairMapping]
    match_columns: list[str] = Field(default_factory=list)
    pair_id_column: str | None = None
    derived_columns: list[PairDerivedColumn]

    @field_validator("group_column")
    @classmethod
    def _clean_group_column(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("配对方案必须指定配对分组列")
        return cleaned

    @field_validator("match_columns")
    @classmethod
    def _clean_match_columns(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("配对匹配标签不能重复")
        if len(cleaned) > 20:
            raise ValueError("配对匹配标签最多允许 20 列")
        return cleaned

    @field_validator("pair_id_column")
    @classmethod
    def _clean_pair_id(cls, value: str | None) -> str | None:
        cleaned = str(value).strip() if value is not None else ""
        return cleaned or None

    @model_validator(mode="after")
    def _validate_structure(self) -> "PairingPlan":
        if not self.mappings:
            raise ValueError("配对方案至少需要一组处理—对照映射")
        if len(self.mappings) > 100:
            raise ValueError("一个配对方案最多允许 100 组处理—对照映射")
        treatments = [item.treatment for item in self.mappings]
        controls = [item.control for item in self.mappings]
        if len(treatments) != len(set(treatments)):
            raise ValueError("同一个处理水平不能映射多个对照")
        if len(controls) != len(set(controls)):
            raise ValueError("同一个对照水平不能被多个处理水平复用")
        overlap = sorted(set(treatments) & set(controls))
        if overlap:
            raise ValueError(f"处理水平与对照水平不能重叠: {overlap}")
        if self.group_column in self.match_columns:
            raise ValueError("配对分组列不需要重复加入匹配标签")
        if self.pair_id_column in {self.group_column, *self.match_columns}:
            raise ValueError("显式样本 ID 不能与配对分组列或匹配标签重复")
        if not self.derived_columns:
            raise ValueError("配对方案至少需要一个配对计算列")
        if len(self.derived_columns) > 10:
            raise ValueError("一个配对方案最多允许 10 个配对计算列")
        ids = [item.id for item in self.derived_columns]
        names = [item.name for item in self.derived_columns]
        if len(ids) != len(set(ids)):
            raise ValueError("配对计算列内部标识不能重复")
        if len(names) != len(set(names)):
            raise ValueError("配对计算列名称不能重复")
        return self


class DependentVariableGroup(BaseModel):
    name: str
    dependent_variables: list[str]

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        cleaned = str(value).strip()
        if not cleaned:
            raise ValueError("联合因变量组名称不能为空")
        if len(cleaned) > 120:
            raise ValueError("联合因变量组名称不能超过 120 个字符")
        return cleaned

    @field_validator("dependent_variables")
    @classmethod
    def _clean_variables(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("同一联合因变量组不能重复选择因变量")
        if not cleaned:
            raise ValueError("联合因变量组不能为空")
        return cleaned
