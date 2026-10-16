"""Human-readable offline PDF risk reports."""

from __future__ import annotations

import io
from html import escape
from typing import Any, Iterable


def _record_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if hasattr(item, "__dataclass_fields__"):
        return {name: getattr(item, name) for name in item.__dataclass_fields__}
    return dict(item)


def _value(value: Any) -> str:
    if value is None or value == "":
        return "Not provided"
    if isinstance(value, (list, tuple)):
        return ", ".join(_value(item) for item in value) or "None"
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_value(item)}" for key, item in value.items())
    return str(value)


def generate_pdf(records: Iterable[Any], *, title: str = "SENTINAL Risk Report") -> bytes:
    """Render stored alert records as a readable, printable PDF."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("PDF export requires optional dependency 'reportlab'") from exc

    rows = [_record_dict(item) for item in records]
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.6 * inch,
        leftMargin=0.6 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=title,
        author="SENTINAL",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#10233f"),
        alignment=TA_CENTER,
        spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="Subtitle",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.HexColor("#58677d"),
        alignment=TA_CENTER,
        spaceAfter=14,
    ))
    styles.add(ParagraphStyle(
        name="Section",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#10233f"),
        spaceBefore=12,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="BodySmall",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#24344d"),
    ))
    styles.add(ParagraphStyle(
        name="Muted",
        parent=styles["BodyText"],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#58677d"),
    ))

    story: list[Any] = [
        Paragraph(escape(title), styles["ReportTitle"]),
        Paragraph("Explainable decision-support summary | Synthetic/local data unless otherwise stated", styles["Subtitle"]),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#d7e0eb")),
    ]

    for index, record in enumerate(rows):
        explanation = record.get("explanation") or {}
        level = str(record.get("level", "unknown")).upper()
        score = record.get("risk_score", record.get("score", "Not provided"))
        severity_color = {
            "CRITICAL": "#b42318",
            "HIGH": "#c2410c",
            "MEDIUM": "#a16207",
            "LOW": "#166534",
        }.get(level, "#475569")

        story.extend([
            Paragraph(f"Incident {index + 1}: {escape(_value(record.get('incident_id', record.get('id'))))}", styles["Section"]),
            Table(
                [
                    [
                        Paragraph("<b>Asset</b><br/>" + escape(_value(record.get("asset_id"))), styles["BodySmall"]),
                        Paragraph("<b>Risk score</b><br/>" + escape(_value(score)), styles["BodySmall"]),
                        Paragraph("<b>Severity</b><br/><font color='" + severity_color + "'><b>" + escape(level) + "</b></font>", styles["BodySmall"]),
                        Paragraph("<b>Status</b><br/>" + escape(_value(record.get("status"))), styles["BodySmall"]),
                    ]
                ],
                colWidths=[1.8 * inch, 1.25 * inch, 1.25 * inch, 1.65 * inch],
                style=TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2f6fa")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dbe4ee")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]),
            ),
        ])

        story.extend([
            Paragraph("Assessment", styles["Section"]),
            Paragraph(escape(_value(explanation.get("what", "No assessment summary was stored."))), styles["BodySmall"]),
            Paragraph("Why this result", styles["Section"]),
        ])
        reasons = explanation.get("why") or ["No reason details were stored."]
        story.extend(Paragraph(f"&bull; {escape(_value(reason))}", styles["BodySmall"]) for reason in reasons)

        factors = explanation.get("factors") or {}
        if factors:
            story.append(Paragraph("Factor contributions", styles["Section"]))
            factor_rows = [[Paragraph("<b>Factor</b>", styles["BodySmall"]), Paragraph("<b>Contribution</b>", styles["BodySmall"])]]
            factor_rows.extend([Paragraph(escape(str(name)), styles["BodySmall"]), Paragraph(escape(_value(value)), styles["BodySmall"])] for name, value in factors.items())
            factor_table_rows = [factor_rows[0]] + [[factor_rows[i], factor_rows[i + 1]] for i in range(1, len(factor_rows), 2)]
            story.append(Table(factor_table_rows, colWidths=[3.7 * inch, 2.25 * inch], style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef6")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])))

        gaps = explanation.get("data_gaps") or []
        evidence = explanation.get("evidence") or []
        if gaps:
            story.append(Paragraph("Data gaps and limitations", styles["Section"]))
            story.append(Paragraph(escape(_value(gaps)), styles["Muted"]))
        if evidence:
            story.append(Paragraph("Evidence references", styles["Section"]))
            story.append(Paragraph(escape(_value(evidence)), styles["Muted"]))

        next_steps = explanation.get("next_steps") or []
        if next_steps:
            story.append(Paragraph("Recommended next steps", styles["Section"]))
            story.extend(Paragraph(f"{position}. {escape(_value(step))}", styles["BodySmall"]) for position, step in enumerate(next_steps, 1))
        story.append(Spacer(1, 8))

    story.append(HRFlowable(width="100%", thickness=0.7, color=colors.HexColor("#d7e0eb")))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "SENTINAL is an offline decision-support prototype. Verify evidence independently before taking operational action. "
        "This report does not represent an autonomous command or control decision.",
        styles["Muted"],
    ))
    document.build(story)
    return buffer.getvalue()
