"""Offline tests for deterministic word-cloud rendering."""

from __future__ import annotations

from tag_edgar.wordcloud import CloudConfig, render_svg, write_cloud_index

FREQUENCIES = {"retention": 40, "vesting": 25, "severance": 15, "equity": 8, "bonus": 5}


def test_render_is_byte_identical_across_runs() -> None:
    first = render_svg(FREQUENCIES, config=CloudConfig(width=400, height=200))
    second = render_svg(FREQUENCIES, config=CloudConfig(width=400, height=200))
    assert first == second
    assert first.startswith("<svg")
    assert "retention" in first


def test_frequency_order_controls_font_size() -> None:
    svg = render_svg(FREQUENCIES, config=CloudConfig())
    retention_index = svg.index("retention")
    equity_index = svg.index("equity")
    retention_font = float(svg[svg.rindex('font-size="', 0, retention_index) + 11 :].split('"')[0])
    equity_font = float(svg[svg.rindex('font-size="', 0, equity_index) + 11 :].split('"')[0])
    assert retention_font > equity_font


def test_empty_frequencies_render_placeholder() -> None:
    svg = render_svg({}, config=CloudConfig())
    assert "no terms" in svg


def test_html_index_written(tmp_path) -> None:
    out = tmp_path / "clouds.html"
    result = write_cloud_index({"group_a": FREQUENCIES, "group_b": {"employees": 9}}, out)
    assert str(out) == result
    page = out.read_text(encoding="utf-8")
    assert page.startswith("<!DOCTYPE html>")
    assert "group_a" in page and "group_b" in page
