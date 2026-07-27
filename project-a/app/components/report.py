"""
PDF Report generation using ReportLab.
Produces a multi-page PDF scorecard report.
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.flowables import HRFlowable


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm

TIER_COLORS = {
    1: colors.HexColor("#e74c3c"),
    2: colors.HexColor("#e67e22"),
    3: colors.HexColor("#f1c40f"),
    4: colors.HexColor("#2980b9"),
    5: colors.HexColor("#27ae60"),
}

TIER_LABELS = {
    1: "Ad Hoc",
    2: "Developing",
    3: "Defined",
    4: "Managed",
    5: "Optimizing",
}

BRAND_DARK = colors.HexColor("#1a1a2e")
BRAND_BLUE = colors.HexColor("#2980b9")
LIGHT_GREY = colors.HexColor("#f5f6fa")
MID_GREY = colors.HexColor("#95a5a6")
DARK_GREY = colors.HexColor("#333333")


# ------------------------------------------------------------------
# Style helpers
# ------------------------------------------------------------------

def _build_styles():
    base = getSampleStyleSheet()

    styles = {
        "cover_title": ParagraphStyle(
            "cover_title",
            fontName="Helvetica-Bold",
            fontSize=28,
            textColor=colors.white,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "cover_subtitle": ParagraphStyle(
            "cover_subtitle",
            fontName="Helvetica",
            fontSize=14,
            textColor=colors.HexColor("#d0d0d0"),
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta",
            fontName="Helvetica",
            fontSize=11,
            textColor=colors.HexColor("#aaaaaa"),
            alignment=TA_CENTER,
        ),
        "section_heading": ParagraphStyle(
            "section_heading",
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=BRAND_DARK,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "dim_heading": ParagraphStyle(
            "dim_heading",
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=BRAND_DARK,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Helvetica",
            fontSize=10,
            textColor=DARK_GREY,
            leading=15,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "small",
            fontName="Helvetica",
            fontSize=9,
            textColor=MID_GREY,
            spaceAfter=2,
        ),
        "rec_item": ParagraphStyle(
            "rec_item",
            fontName="Helvetica",
            fontSize=10,
            textColor=DARK_GREY,
            leading=14,
            leftIndent=16,
            spaceAfter=5,
        ),
        "tier_label": ParagraphStyle(
            "tier_label",
            fontName="Helvetica-Bold",
            fontSize=11,
            spaceAfter=2,
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName="Helvetica",
            fontSize=8,
            textColor=MID_GREY,
            alignment=TA_CENTER,
        ),
    }
    return styles


# ------------------------------------------------------------------
# Page template with header/footer
# ------------------------------------------------------------------

def _make_page_template(org_name: str, report_date: str):
    def on_page(canvas, doc):
        canvas.saveState()
        w, h = A4

        # Header bar
        canvas.setFillColor(BRAND_DARK)
        canvas.rect(0, h - 12 * mm, w, 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(MARGIN, h - 8 * mm, "AI Platform Maturity Assessment")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(w - MARGIN, h - 8 * mm, org_name)

        # Footer bar
        canvas.setFillColor(LIGHT_GREY)
        canvas.rect(0, 0, w, 10 * mm, fill=1, stroke=0)
        canvas.setFillColor(MID_GREY)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(MARGIN, 3.5 * mm, f"Generated: {report_date}")
        canvas.drawCentredString(w / 2, 3.5 * mm, "Confidential")
        canvas.drawRightString(w - MARGIN, 3.5 * mm, f"Page {doc.page}")

        canvas.restoreState()

    return on_page


# ------------------------------------------------------------------
# Section builders
# ------------------------------------------------------------------

def _cover_page(styles: dict, org_name: str, overall_score: float,
                maturity_tier: int, maturity_label: str,
                completed_at: str) -> list:
    elements = []

    # Dark cover background via a large table
    tier_color = TIER_COLORS.get(maturity_tier, BRAND_BLUE)

    cover_data = [[
        Paragraph("AI Platform Maturity Assessment", styles["cover_title"])
    ]]
    cover_table = Table(cover_data, colWidths=[PAGE_W - 2 * MARGIN])
    cover_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_DARK),
        ("TOPPADDING", (0, 0), (-1, -1), 40),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
    ]))
    elements.append(cover_table)
    elements.append(Spacer(1, 8 * mm))

    # Org name
    elements.append(Paragraph(org_name, styles["cover_subtitle"]))
    elements.append(Spacer(1, 16 * mm))

    # Score badge table
    badge_data = [[
        Paragraph(f"Level {maturity_tier}", ParagraphStyle(
            "badge_tier", fontName="Helvetica-Bold", fontSize=13,
            textColor=colors.white, alignment=TA_CENTER
        )),
        Paragraph(maturity_label, ParagraphStyle(
            "badge_label", fontName="Helvetica-Bold", fontSize=22,
            textColor=colors.white, alignment=TA_CENTER
        )),
        Paragraph(f"{overall_score:.2f} / 5.00", ParagraphStyle(
            "badge_score", fontName="Helvetica", fontSize=13,
            textColor=colors.HexColor("#d0d0d0"), alignment=TA_CENTER
        )),
    ]]
    badge_table = Table(badge_data, colWidths=[40 * mm, 80 * mm, 50 * mm])
    badge_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), tier_color),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [6]),
    ]))
    elements.append(badge_table)
    elements.append(Spacer(1, 12 * mm))

    # Date
    elements.append(Paragraph(
        f"Assessment completed: {completed_at}",
        styles["cover_meta"]
    ))
    elements.append(PageBreak())
    return elements


def _executive_summary(styles: dict, overall_score: float,
                       maturity_tier: int, maturity_label: str,
                       dimension_scores: list) -> list:
    elements = []
    elements.append(Paragraph("Executive Summary", styles["section_heading"]))
    elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_BLUE))
    elements.append(Spacer(1, 4 * mm))

    tier_color = TIER_COLORS.get(maturity_tier, BRAND_BLUE)

    # Summary paragraph
    strongest = max(dimension_scores, key=lambda d: d["score"])
    weakest = min(dimension_scores, key=lambda d: d["score"])

    summary_text = (
        f"This organisation achieved an overall AI maturity score of "
        f"<b>{overall_score:.2f} out of 5.00</b>, placing it at "
        f"<b>Level {maturity_tier}: {maturity_label}</b>. "
        f"The assessment evaluated six dimensions of AI platform maturity covering "
        f"data infrastructure, model development, platform engineering, governance, "
        f"team culture, and business integration. "
        f"The strongest area was <b>{strongest['label']}</b> "
        f"(score: {strongest['score']:.2f}), while the greatest opportunity for "
        f"improvement lies in <b>{weakest['label']}</b> "
        f"(score: {weakest['score']:.2f}). "
        f"The recommendations in this report are prioritised to address the most "
        f"impactful gaps at the current maturity level."
    )
    elements.append(Paragraph(summary_text, styles["body"]))
    elements.append(Spacer(1, 6 * mm))

    # Dimension summary table
    elements.append(Paragraph("Dimension Summary", styles["dim_heading"]))

    table_data = [["Dimension", "Score", "Maturity Level"]]
    for dim in dimension_scores:
        dim_tier = dim["tier"]
        dim_color = TIER_COLORS.get(dim_tier, BRAND_BLUE)
        table_data.append([
            dim["label"],
            f"{dim['score']:.2f} / 5.00",
            f"Level {dim_tier}: {dim['tier_label']}",
        ])

    col_widths = [90 * mm, 35 * mm, 55 * mm]
    summary_table = Table(table_data, colWidths=col_widths)

    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (2, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]

    # Color the tier column per tier
    for i, dim in enumerate(dimension_scores, start=1):
        dim_color = TIER_COLORS.get(dim["tier"], BRAND_BLUE)
        table_style.append(("TEXTCOLOR", (2, i), (2, i), dim_color))
        table_style.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))

    summary_table.setStyle(TableStyle(table_style))
    elements.append(summary_table)
    elements.append(PageBreak())
    return elements


def _dimension_pages(styles: dict, dimension_scores: list,
                     recommendations: dict) -> list:
    elements = []
    elements.append(Paragraph("Detailed Findings & Recommendations", styles["section_heading"]))
    elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_BLUE))
    elements.append(Spacer(1, 4 * mm))

    for dim in dimension_scores:
        dim_id = dim["id"]
        dim_tier = dim["tier"]
        tier_color = TIER_COLORS.get(dim_tier, BRAND_BLUE)
        recs = recommendations.get(dim_id, [])

        # Dimension header block
        header_data = [[
            Paragraph(dim["label"], ParagraphStyle(
                "dh", fontName="Helvetica-Bold", fontSize=13,
                textColor=colors.white
            )),
            Paragraph(
                f"Level {dim_tier}: {dim['tier_label']}  |  Score: {dim['score']:.2f}",
                ParagraphStyle(
                    "ds", fontName="Helvetica", fontSize=11,
                    textColor=colors.white, alignment=TA_RIGHT
                )
            ),
        ]]
        header_table = Table(header_data, colWidths=[100 * mm, 80 * mm])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), tier_color),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (0, -1), 10),
            ("RIGHTPADDING", (-1, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))

        dim_block = [header_table, Spacer(1, 3 * mm)]

        # Recommendations
        if recs:
            dim_block.append(Paragraph("Recommended Actions", styles["dim_heading"]))
            for i, rec in enumerate(recs, 1):
                rec_data = [[
                    Paragraph(str(i), ParagraphStyle(
                        "rn", fontName="Helvetica-Bold", fontSize=10,
                        textColor=colors.white, alignment=TA_CENTER
                    )),
                    Paragraph(rec, styles["body"]),
                ]]
                rec_table = Table(rec_data, colWidths=[8 * mm, 162 * mm])
                rec_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (0, 0), tier_color),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (0, 0), 2),
                    ("LEFTPADDING", (1, 0), (1, 0), 8),
                    ("RIGHTPADDING", (1, 0), (1, 0), 4),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#eeeeee")),
                ]))
                dim_block.append(rec_table)

        dim_block.append(Spacer(1, 6 * mm))
        elements.append(KeepTogether(dim_block))

    return elements


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

def generate_pdf_report(
    org_name: str,
    overall_score: float,
    maturity_tier: int,
    maturity_label: str,
    dimension_scores: list,
    recommendations: dict,
    completed_at: str,
) -> bytes:
    """
    Generate a PDF report and return it as bytes.
    Ready to stream directly to Streamlit download_button.
    """
    buffer = io.BytesIO()
    report_date = datetime.utcnow().strftime("%d %B %Y")

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=18 * mm,
        bottomMargin=14 * mm,
        title=f"AI Maturity Report — {org_name}",
        author="AI Maturity Assessment Tool",
    )

    styles = _build_styles()
    on_page = _make_page_template(org_name, report_date)

    elements = []
    elements += _cover_page(
        styles, org_name, overall_score,
        maturity_tier, maturity_label, completed_at
    )
    elements += _executive_summary(
        styles, overall_score, maturity_tier,
        maturity_label, dimension_scores
    )
    elements += _dimension_pages(styles, dimension_scores, recommendations)

    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
    buffer.seek(0)
    return buffer.read()