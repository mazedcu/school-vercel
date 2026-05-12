"""
performance/pdf_utils.py — Generates a printable PDF Performance Report using ReportLab.
"""
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle,
    Spacer, HRFlowable
)

from utils.pdf_base import (
    get_base_styles, draw_footer,
    PRIMARY_DARK, PRIMARY, SUCCESS, WARNING, DANGER,
    TEXT_MAIN, TEXT_MUTED, BG_LIGHT, BORDER
)
from .services import get_performance_grade, calculate_final_score


def _grade_colour(score):
    if score is None:
        return TEXT_MUTED
    score = Decimal(str(score))
    if score >= 80:
        return SUCCESS
    elif score >= 60:
        return PRIMARY
    elif score >= 50:
        return WARNING
    return DANGER


def generate_performance_report_pdf(evaluation):
    """
    Generate a PDF for a StaffEvaluation instance.
    Returns BytesIO buffer.
    """
    buffer = BytesIO()
    styles = get_base_styles()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Performance Report — {evaluation.staff.get_full_name()}",
    )

    story = []
    final_score = evaluation.final_score
    grade_info = get_performance_grade(final_score)

    # ── Header ──────────────────────────────────────────────────────────────
    story.append(Paragraph("STAFF PERFORMANCE REPORT", styles['MainTitle']))
    story.append(Paragraph(
        f"{evaluation.cycle.name}  |  {evaluation.cycle.start_date.strftime('%d %b %Y')} – {evaluation.cycle.end_date.strftime('%d %b %Y')}",
        styles['SubTitle']
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=PRIMARY_DARK, spaceAfter=4 * mm))

    # ── Staff Info Box ───────────────────────────────────────────────────────
    staff = evaluation.staff
    evaluator = evaluation.evaluated_by
    info_data = [
        ['Staff Name:', staff.get_full_name() or staff.username,
         'Role:', evaluation.get_role_type_display()],
        ['Staff ID:', f"#{staff.id}",
         'Evaluated By:', evaluator.get_full_name() if evaluator else '—'],
        ['Period:', f"{evaluation.cycle.start_date} — {evaluation.cycle.end_date}",
         'Status:', evaluation.get_status_display()],
        ['Submitted:', evaluation.submitted_at.strftime('%d %b %Y %H:%M') if evaluation.submitted_at else 'Not yet submitted',
         '', ''],
    ]
    info_table = Table(info_data, colWidths=[35 * mm, 65 * mm, 30 * mm, 50 * mm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), TEXT_MAIN),
        ('TEXTCOLOR', (0, 0), (0, -1), TEXT_MUTED),
        ('TEXTCOLOR', (2, 0), (2, -1), TEXT_MUTED),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6 * mm))

    # ── Score summary bar ────────────────────────────────────────────────────
    score_display = f"{final_score:.1f}" if final_score is not None else "—"
    grade_colour = _grade_colour(final_score)

    score_data = [[
        Paragraph(f"<b>FINAL SCORE</b>", styles['Normal']),
        Paragraph(f"<font size='16' color='{grade_colour.hexval()}'><b>{score_display}</b></font> / 100", styles['Normal']),
        Paragraph(f"<b>{grade_info['letter']}</b> — {grade_info['label']}", styles['Normal']),
    ]]
    score_table = Table(score_data, colWidths=[45 * mm, 65 * mm, 70 * mm])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('ROUNDEDCORNERS', [4]),
        ('BOX', (0, 0), (-1, -1), 1, BORDER),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 8 * mm))

    # ── KPI Sections ─────────────────────────────────────────────────────────
    sections = evaluation.cycle.sections.filter(role_type=evaluation.role_type).prefetch_related('kpis')
    score_map = {ks.kpi_id: ks for ks in evaluation.kpi_scores.select_related('kpi').all()}

    for section in sections:
        story.append(Paragraph(section.name.upper(), styles['Heading2']))
        story.append(Spacer(1, 2 * mm))

        kpi_data = [['KPI', 'Data Source', 'Weight', 'Score', 'Earned', 'Comment']]
        section_earned = Decimal('0')
        section_max = Decimal('0')

        for kpi in section.kpis.all():
            ks = score_map.get(kpi.id)
            score = ks.score if ks else Decimal('0')
            earned = (score * kpi.max_weight) / Decimal('100')
            section_earned += earned
            section_max += kpi.max_weight

            kpi_data.append([
                Paragraph(kpi.title, styles['Normal']),
                Paragraph(kpi.data_source, styles['Normal']),
                f"{kpi.max_weight:.0f}%",
                f"{score:.0f}",
                f"{earned:.2f}",
                Paragraph(ks.comment if ks and ks.comment else '—', styles['Normal']),
            ])

        # Section subtotal row
        kpi_data.append([
            Paragraph('<b>Section Total</b>', styles['Normal']),
            '', f"{section_max:.0f}%", '', f"{section_earned:.2f}", ''
        ])

        kpi_table = Table(
            kpi_data,
            colWidths=[55 * mm, 42 * mm, 16 * mm, 14 * mm, 16 * mm, 37 * mm]
        )
        kpi_table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY_DARK),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            # Data rows
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('ALIGN', (2, 1), (4, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, BG_LIGHT]),
            # Subtotal row
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#e0e7ff')),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 5 * mm))

    # ── Overall Comment ──────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4 * mm))
    story.append(Paragraph("<b>Evaluator's Overall Remarks</b>", styles['Normal']))
    story.append(Spacer(1, 2 * mm))
    comment_text = evaluation.overall_comment or "No remarks provided."
    story.append(Paragraph(comment_text, styles['Normal']))
    story.append(Spacer(1, 12 * mm))

    # ── Signature Block ──────────────────────────────────────────────────────
    sig_data = [[
        'Staff Signature: ____________________',
        'Evaluator Signature: ____________________',
        'Date: ________________',
    ]]
    sig_table = Table(sig_data, colWidths=[65 * mm, 70 * mm, 45 * mm])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), TEXT_MUTED),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(sig_table)

    doc.build(story, onFirstPage=lambda c, d: draw_footer(c, d), onLaterPages=lambda c, d: draw_footer(c, d))
    buffer.seek(0)
    return buffer
