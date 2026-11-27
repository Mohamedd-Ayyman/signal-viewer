"""PDF report generation, built in code with ReportLab (never a screenshot turned into a PDF).

Layout: a title block with a summary, a statistics table (mean, std, duration,
min, max, sampling rate) for every signal in each graph, then each snapshot with
its caption and a table of the signals it shows. Long reports flow onto as many
pages as needed, with page numbers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .signal_model import Signal

TABLE_COLUMNS = ["Signal", "Mean", "Std", "Min", "Max", "Duration (s)", "Fs (Hz)"]
PAGE_MARGIN = 1.8 * cm


@dataclass
class Snapshot:
    caption: str
    image_path: str
    statistics: list[dict]     # one row per signal visible when the snapshot was taken


def _statistics_table(rows: Iterable[dict]) -> Table:
    table_rows = [TABLE_COLUMNS]
    for statistics in rows:
        table_rows.append([statistics["Signal"]] + [f"{statistics[column]:.3f}" for column in TABLE_COLUMNS[1:]])
    table = Table(table_rows, repeatRows=1, hAlign="LEFT")
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


def _draw_page_number(canvas, document):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawRightString(A4[0] - PAGE_MARGIN, 1.0 * cm, f"Page {document.page}")
    canvas.drawString(PAGE_MARGIN, 1.0 * cm, "Signal Viewer report")
    canvas.restoreState()


def build_report(path: str, snapshots: list[Snapshot], signals_by_graph: dict[str, list[Signal]],
                 title: str = "Biomedical Signal Report") -> str:
    """Write the PDF to *path* and return the path."""
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(path, pagesize=A4, leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
                                 topMargin=1.6 * cm, bottomMargin=1.8 * cm, title=title)
    signal_count = sum(len(signals) for signals in signals_by_graph.values())
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(f"Generated {datetime.now():%Y-%m-%d %H:%M} · {signal_count} signal(s) · "
                  f"{len(snapshots)} snapshot(s)", styles["Normal"]),
        Spacer(1, 0.5 * cm),
    ]

    for graph_name, signals in signals_by_graph.items():
        if signals:
            story += [Paragraph(f"{graph_name}: signal statistics", styles["Heading2"]),
                      _statistics_table(signal.statistics() for signal in signals), Spacer(1, 0.4 * cm)]

    if snapshots:
        story.append(Paragraph("Snapshots", styles["Heading2"]))
        image_width = A4[0] - 2 * PAGE_MARGIN
        for position, snapshot in enumerate(snapshots):
            image = Image(snapshot.image_path)
            image.drawWidth, image.drawHeight = image_width, image_width * image.imageHeight / float(image.imageWidth)
            block = [Paragraph(snapshot.caption, styles["Italic"]), Spacer(1, 0.15 * cm), image, Spacer(1, 0.2 * cm)]
            if snapshot.statistics:
                block.append(_statistics_table(snapshot.statistics))
            story.append(KeepTogether(block))
            if position < len(snapshots) - 1:
                story.append(Spacer(1, 0.5 * cm))

    document.build(story, onFirstPage=_draw_page_number, onLaterPages=_draw_page_number)
    return path
