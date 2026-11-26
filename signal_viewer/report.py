"""PDF report generation (built in code with ReportLab, not a screenshot).

The report contains a title block, one or more graph snapshots and a
statistics table (mean, std, min, max, duration, sampling rate) per signal.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .signal_model import Signal

_HEADERS = ["Signal", "Mean", "Std", "Min", "Max", "Duration (s)", "Fs (Hz)"]


def _stats_table(signals: Iterable[Signal]) -> Table:
    rows = [_HEADERS]
    for s in signals:
        st = s.statistics()
        rows.append([st["Signal"]] + [f"{st[h]:.3f}" for h in _HEADERS[1:]])
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f4f9")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8cfdb")),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def build_report(path: str, snapshots: list[tuple[str, str]], groups: dict[str, list[Signal]],
                 title: str = "Biomedical Signal Report") -> str:
    """Write a PDF to *path*.

    snapshots: list of (caption, png_path)
    groups:    {"Graph 1": [signals...], "Graph 2": [...]} for the statistics tables
    """
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                            topMargin=1.6 * cm, bottomMargin=1.6 * cm, title=title)
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(f"Generated {datetime.now():%Y-%m-%d %H:%M}", styles["Normal"]),
        Spacer(1, 0.5 * cm),
    ]

    for name, signals in groups.items():
        if not signals:
            continue
        story += [Paragraph(f"{name}: signal statistics", styles["Heading2"]), _stats_table(signals),
                  Spacer(1, 0.4 * cm)]

    if snapshots:
        story.append(Paragraph("Snapshots", styles["Heading2"]))
        width = A4[0] - 3.6 * cm
        for i, (caption, png) in enumerate(snapshots):
            img = Image(png)
            ratio = img.imageHeight / float(img.imageWidth)
            img.drawWidth, img.drawHeight = width, width * ratio
            story += [Paragraph(caption, styles["Italic"]), img, Spacer(1, 0.35 * cm)]
            if i % 2 == 1 and i != len(snapshots) - 1:
                story.append(PageBreak())

    doc.build(story)
    return path
