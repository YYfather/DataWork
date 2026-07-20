from pathlib import Path

from datawork.io.reader import clean_dataframe, read_file


def test_gb18030_semicolon_csv_is_detected(tmp_path: Path):
    path = tmp_path / "数据.csv"
    path.write_bytes("处理;数值\n对照;1\n处理;2\n".encode("gb18030"))
    result = read_file(path)
    frame = next(iter(result.values()))
    assert list(frame.columns) == ["处理", "数值"]
    assert frame.shape == (2, 2)


def test_clean_dataframe_does_not_fill_missing_by_default():
    import pandas as pd
    frame = pd.DataFrame({"group": ["a", None, "b"], "y": [1, 2, 3]})
    cleaned = clean_dataframe(frame)
    assert cleaned["group"].isna().sum() == 1


def test_excel_sheet_name_with_spaces_is_preserved_and_reloadable(tmp_path: Path):
    import pandas as pd
    path = tmp_path / "book.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"x": [1, 2]}).to_excel(writer, sheet_name="田间 数据", index=False)
    all_sheets = read_file(path)
    assert "田间 数据" in all_sheets
    selected = read_file(path, sheet_name="田间 数据")
    assert selected["田间 数据"]["x"].tolist() == [1, 2]


def test_blank_header_columns_are_excluded_even_with_accidental_value():
    import pandas as pd

    frame = pd.DataFrame({
        "有效列": [1, 2, 3],
        "Unnamed: 1": [None, "误填", None],
        "全空列": [" ", None, ""],
    })
    cleaned = clean_dataframe(frame)
    assert list(cleaned.columns) == ["有效列"]


def test_single_column_csv_is_not_misdetected_as_delimited_by_decimal_symbols(tmp_path):
    path = tmp_path / "single.csv"
    path.write_text("y\n-0.5854038336302881\n1.25\n2.5\n", encoding="utf-8")
    sheets = read_file(path)
    frame = next(iter(sheets.values()))
    assert list(frame.columns) == ["y"]
    assert frame.shape == (3, 1)


def test_small_numeric_measurement_is_not_misclassified_as_factor():
    import pandas as pd
    from datawork.io.profiler import profile_dataframe

    frame = pd.DataFrame({"group": ["A", "A", "A", "B", "B", "B"], "value": [1, 2, 3, 4, 5, 6]})
    profile = profile_dataframe(frame)
    roles = {column.name: column.inferred_role for column in profile.columns}
    assert roles["group"] == "between"
    assert roles["value"] == "dependent"
