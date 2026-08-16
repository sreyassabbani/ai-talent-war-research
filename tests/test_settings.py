from tag_edgar.settings import load_settings


def test_core_form_configuration_includes_meeting_priorities(monkeypatch) -> None:
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    settings = load_settings(require_user_agent=False)

    assert {"424B3", "SC 14D9", "SC TO-T", "SC TO-I"}.issubset(settings.forms)
    assert settings.document_prefixes == ("EX-2.", "EX-10.", "EX-99.")
