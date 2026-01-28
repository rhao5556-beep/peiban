from app.api.endpoints.profile import UserSettingsModel


def test_user_settings_schema_ignores_unknown_fields():
    settings = UserSettingsModel.model_validate({
        "version": 1,
        "timezone": "Asia/Shanghai",
        "locale": "zh-CN",
        "ui": {"theme": "dark"},
        "unknown": 123,
        "nested_unknown": {"x": 1},
    })
    dumped = settings.model_dump()
    assert dumped["timezone"] == "Asia/Shanghai"
    assert "unknown" not in dumped
    assert "nested_unknown" not in dumped

