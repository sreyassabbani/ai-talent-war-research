from pathlib import Path

from tag_edgar.technology import load_technology_screen


def test_load_technology_screen_and_explain_match(tmp_path: Path) -> None:
    source = tmp_path / "screen.toml"
    source.write_text(
        'version = "test-v1"\nsource = "citation"\n[codes]\n7372 = "Prepackaged software"\n',
        encoding="utf-8",
    )

    screen = load_technology_screen(source)

    assert screen.rationale("7372") == "Target SIC 7372: Prepackaged software"
    assert screen.rationale("4941") is None
