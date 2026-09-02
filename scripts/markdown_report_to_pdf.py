"""Render a generated Markdown report as a PDF.

The Markdown file stays the source of truth; this only changes the container, so the PDF cannot
carry a number the Markdown does not. Handles the subset of Markdown the report generators emit:
headings, paragraphs, bullet and numbered lists, block quotes, fenced code, pipe tables, and
horizontal rules.

Requires reportlab, which is optional report-rendering tooling and not a package dependency:
    pip install reportlab

Usage:
    python scripts/markdown_report_to_pdf.py docs/report.md docs/report.pdf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    ListFlowable,
    ListItem,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#5a5a5a")
RULE = colors.HexColor("#c9c9c9")
BAND = colors.HexColor("#f2f2f2")
ACCENT = colors.HexColor("#2f4858")

_BOLD = re.compile(r"\*\*(.+?)\*\*")
# Single asterisks, run after bold so the two markers cannot be confused.
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CODE = re.compile(r"`([^`]+)`")


def inline(text: str) -> str:
    """Convert inline Markdown to reportlab markup, escaping XML first."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = _LINK.sub(r"\1", text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    text = _CODE.sub(r'<font face="Courier" size="8.5">\1</font>', text)
    # Markdown check marks used in the briefing read poorly in the base PDF fonts.
    return text.replace("❌", "<b>No:</b>").replace("✅", "<b>Yes:</b>")


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontSize=20, leading=25, textColor=ACCENT,
            spaceAfter=4, alignment=TA_LEFT,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"], fontSize=14.5, leading=18, textColor=ACCENT,
            spaceBefore=16, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontSize=12, leading=15, textColor=INK,
            spaceBefore=12, spaceAfter=4,
        ),
        "h3": ParagraphStyle(
            "h3", parent=base["Heading3"], fontSize=10.5, leading=13, textColor=INK,
            spaceBefore=10, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontSize=9.5, leading=13.5, textColor=INK,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "bullet", parent=base["BodyText"], fontSize=9.5, leading=13, textColor=INK,
            spaceAfter=2,
        ),
        "quote": ParagraphStyle(
            "quote", parent=base["BodyText"], fontSize=8.8, leading=12, textColor=MUTED,
            leftIndent=16, rightIndent=8, spaceAfter=6, borderPadding=4,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["BodyText"], fontSize=8.2, leading=10.5, textColor=INK,
            spaceAfter=0,
        ),
        "cellhead": ParagraphStyle(
            "cellhead", parent=base["BodyText"], fontSize=8.2, leading=10.5, textColor=INK,
            spaceAfter=0, fontName="Helvetica-Bold",
        ),
    }


def is_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip("|").split("|")]


def build_table(rows: list[list[str]], style: dict[str, ParagraphStyle], width: float) -> Table:
    columns = max(len(r) for r in rows)
    data = [
        [
            Paragraph(inline(r[i] if i < len(r) else ""), style["cellhead" if n == 0 else "cell"])
            for i in range(columns)
        ]
        for n, r in enumerate(rows)
    ]
    # First column carries the labels and needs the room; the rest share what is left.
    first = min(width * 0.42, width / columns * 1.8) if columns > 1 else width
    rest = (width - first) / (columns - 1) if columns > 1 else 0
    table = Table(data, colWidths=[first, *([rest] * (columns - 1))], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BAND),
                ("LINEBELOW", (0, 0), (-1, 0), 0.75, RULE),
                ("GRID", (0, 0), (-1, -1), 0.25, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def convert(source: Path, target: Path) -> int:
    style = styles()
    lines = source.read_text(encoding="utf-8").split("\n")
    frame_width = LETTER[0] - 2 * inch
    story: list[object] = []
    pending: list[list[str]] = []
    bullets: list[ListItem] = []
    first_heading = True

    def flush_table() -> None:
        nonlocal pending
        if pending:
            story.append(Spacer(1, 3))
            story.append(build_table(pending, style, frame_width))
            story.append(Spacer(1, 8))
            pending = []

    def flush_bullets() -> None:
        nonlocal bullets
        if bullets:
            story.append(
                ListFlowable(
                    bullets, bulletType="bullet", start="•", leftIndent=14, bulletFontSize=7
                )
            )
            story.append(Spacer(1, 6))
            bullets = []

    index = 0
    while index < len(lines):
        line = lines[index].rstrip()

        if is_row(line):
            flush_bullets()
            row = cells(line)
            if not all(set(c) <= set("-: ") and c for c in row):
                pending.append(row)
            index += 1
            continue
        flush_table()

        if line.startswith("```"):
            flush_bullets()
            index += 1
            block: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                block.append(lines[index])
                index += 1
            index += 1
            story.append(
                Preformatted("\n".join(block), ParagraphStyle("code", fontName="Courier", fontSize=8, leading=10, textColor=INK))
            )
            story.append(Spacer(1, 8))
            continue

        if line.startswith("#"):
            flush_bullets()
            level = len(line) - len(line.lstrip("#"))
            text = inline(line[level:].strip())
            if level == 1 and first_heading:
                story.append(Paragraph(text, style["title"]))
                first_heading = False
            else:
                story.append(Paragraph(text, style[f"h{min(level, 3)}"]))
        elif line.startswith("> "):
            flush_bullets()
            story.append(Paragraph(inline(line[2:]), style["quote"]))
        elif line.startswith(("- ", "* ")):
            bullets.append(ListItem(Paragraph(inline(line[2:]), style["bullet"]), leftIndent=14))
        elif re.match(r"^\d+\. ", line):
            flush_bullets()
            story.append(
                Paragraph(inline(re.sub(r"^(\d+)\. ", r"<b>\1.</b> ", line)), style["body"])
            )
        elif line.strip() in {"---", "***"}:
            flush_bullets()
            story.append(Spacer(1, 4))
        elif line.strip():
            flush_bullets()
            buffer = [line.strip()]
            while (
                index + 1 < len(lines)
                and lines[index + 1].strip()
                and not lines[index + 1].startswith(("#", "|", ">", "- ", "* ", "```"))
                and not re.match(r"^\d+\. ", lines[index + 1])
            ):
                index += 1
                buffer.append(lines[index].strip())
            story.append(Paragraph(inline(" ".join(buffer)), style["body"]))
        else:
            flush_bullets()
        index += 1

    flush_table()
    flush_bullets()

    title = source.stem.replace("_", " ")

    def decorate(canvas: object, doc: object) -> None:
        canvas.saveState()  # type: ignore[attr-defined]
        canvas.setFont("Helvetica", 7.5)  # type: ignore[attr-defined]
        canvas.setFillColor(MUTED)  # type: ignore[attr-defined]
        canvas.drawString(inch, 0.6 * inch, title)  # type: ignore[attr-defined]
        canvas.drawRightString(  # type: ignore[attr-defined]
            LETTER[0] - inch, 0.6 * inch, f"page {doc.page}"  # type: ignore[attr-defined]
        )
        canvas.setStrokeColor(RULE)  # type: ignore[attr-defined]
        canvas.line(inch, 0.75 * inch, LETTER[0] - inch, 0.75 * inch)  # type: ignore[attr-defined]
        canvas.restoreState()  # type: ignore[attr-defined]

    document = BaseDocTemplate(
        str(target), pagesize=LETTER,
        leftMargin=inch, rightMargin=inch, topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        title=title, author="Georgia Tech TAG Internship",
    )
    frame = Frame(inch, 0.9 * inch, frame_width, LETTER[1] - 1.8 * inch, id="body")
    document.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=decorate)])
    blocks = len(story)
    # build() consumes the story list, so the count has to be taken first.
    document.build(story)
    return blocks


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print((__doc__ or "").strip(), file=sys.stderr)
        return 2
    source, target = Path(argv[1]), Path(argv[2])
    if not source.exists():
        print(f"{source} not found.", file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    blocks = convert(source, target)
    print(f"Wrote {target} ({blocks} blocks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
