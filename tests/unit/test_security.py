from pathlib import Path


def test_source_contains_no_hardcoded_sk_key():
    source = Path("datawork/ai/provider.py").read_text(encoding="utf-8")
    assert 'or "sk-' not in source
    assert "8908e51d" not in source


def test_source_contains_no_builtin_eval_in_derive_variable():
    source = Path("datawork/engine/batch.py").read_text(encoding="utf-8")
    assert "eval(expr)" not in source
