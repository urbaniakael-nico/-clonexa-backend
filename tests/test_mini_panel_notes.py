from app.api.v1.endpoints.mini_panel_notes import NOTES_ALIASES, VALID_TYPES, _norm


def test_notes_agenda_catalog_code_is_supported() -> None:
    assert _norm("Notas / Agenda") == "notas_agenda"
    assert "notas_agenda" in NOTES_ALIASES


def test_notes_agenda_supports_events() -> None:
    assert "event" in VALID_TYPES
