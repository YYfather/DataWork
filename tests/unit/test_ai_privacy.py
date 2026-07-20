from datawork.application.ai_assistant_service import _sanitize_context


def test_metadata_privacy_removes_preview_and_secrets():
    context = {
        "api_key": "never",
        "Authorization": "Bearer never",
        "preview": [{"name": "Alice", "value": 3}],
        "profile": {"n_rows": 10},
    }
    cleaned = _sanitize_context(context, include_preview=False)
    assert "api_key" not in cleaned
    assert "Authorization" not in cleaned
    assert cleaned["preview"] == "[隐私模式已省略原始数据预览]"
    assert cleaned["profile"]["n_rows"] == 10


def test_preview_mode_limits_rows():
    context = {"preview": [{"value": index} for index in range(20)]}
    cleaned = _sanitize_context(context, include_preview=True)
    assert len(cleaned["preview"]) == 5


def test_gui_settings_are_reused_by_runtime_provider(tmp_path, monkeypatch):
    from datawork.ai.provider import ProviderKind, create_provider
    from datawork.ai.settings import AISettings, AISettingsService, SecretStorage
    from datawork.infrastructure.paths import resolve_workspace_paths

    monkeypatch.setenv("DATAWORK_HOME", str(tmp_path))
    service = AISettingsService(resolve_workspace_paths())
    service.save(
        AISettings(
            enabled=True,
            provider=ProviderKind.DEEPSEEK,
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        ),
        api_key="runtime-secret",
        secret_storage=SecretStorage.SESSION,
    )
    provider = create_provider()
    assert provider is not None
    assert provider.config.kind == ProviderKind.DEEPSEEK
    assert provider.config.api_key == "runtime-secret"
