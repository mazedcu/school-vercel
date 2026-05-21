"""
Timetable PDF generation utilities.
Generates class-wise and teacher-wise timetable PDFs using ReportLab.
"""
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from utils.pdf_base import get_base_styles, PRIMARY_DARK, BORDER, BG_LIGHT, TEXT_MUTED
from timetable.models import TimeSlot, TimetableEntry


DAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
DAY_LABELS = {
    'monday': 'Mon', 'tuesday': 'Tue', 'wednesday': 'Wed',
    'thursday': 'Thu', 'friday': 'Fri', 'saturday': 'Sat', 'sunday': 'Sun',
}

# ── Using Shared Palette ──────────────────────────────────────────────────
HEADER_BG = PRIMARY_DARK
HEADER_FG = colors.white
ROW_ALT   = BG_LIGHT
CELL_BG   = colors.HexColor('#eef2ff')
GRID_CLR  = BORDER
ACCENT    = colors.HexColor('#6366f1')


def _build_styles():
    """Return custom paragraph styles for the PDF."""
    styles = get_base_styles()
    styles.add(ParagraphStyle(
        'TitleCustom', parent=styles['MainTitle'],
        fontSize=16, spaceAfter=2 * mm,
    ))
    styles.add(ParagraphStyle(
        'CellSubject', parent=styles['Normal'],
        fontSize=8, textColor=HEADER_BG, leading=10,
        alignment=TA_CENTER, fontName='Helvetica-Bold',
    ))
    styles.add(ParagraphStyle(
        'CellTeacher', parent=styles['Normal'],
        fontSize=6.5, textColor=colors.HexColor('#64748b'),
        leading=8, alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        'CellRoom', parent=styles['Normal'],
        fontSize=6, textColor=colors.HexColor('#7c3aed'),
        leading=8, alignment=TA_CENTER, fontName='Helvetica-Bold',
    ))
    styles.add(ParagraphStyle(
        'TimeCell', parent=styles['Normal'],
        fontSize=7.5, textColor=HEADER_BG, leading=10,
        alignment=TA_CENTER, fontName='Helvetica-Bold',
    ))
    return styles


def _grid_table_style(n_rows, n_cols):
    """Return a professional TableStyle for the timetable grid."""
    style_cmds = [
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
        ('TEXTCOLOR', (0, 0), (-1, 0), HEADER_FG),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, GRID_CLR),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        # Time column styling
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f8fafc')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
    ]
    # Alternating row backgrounds
    for i in range(1, n_rows):
        if i % 2 == 0:
            style_cmds.append(('BACKGROUND', (1, i), (-1, i), ROW_ALT))
    return TableStyle(style_cmds)


def _build_section_grid(section, entries, styles):
    """Build the grid data for a section's timetable."""
    # Build lookup
    lookup = {}
    for e in entries:
        key = (e.time_slot.day, str(e.time_slot.start_time), str(e.time_slot.end_time))
        lookup[key] = e

    # Determine active days
    active_day_set = set(e.time_slot.day for e in entries)
    active_days = [d for d in DAY_ORDER if d in active_day_set]
    if not active_days:
        active_days = DAY_ORDER[:5]

    # Get unique time slots for this section's entries
    slot_ids = set(e.time_slot_id for e in entries)
    unique_times = TimeSlot.objects.filter(id__in=slot_ids).values_list(
        'start_time', 'end_time'
    ).distinct().order_by('start_time')

    # Header row
    header = ['Time'] + [DAY_LABELS.get(d, d) for d in active_days]
    data = [header]

    for start_time, end_time in unique_times:
        time_str = f"{start_time.strftime('%H:%M')}\n{end_time.strftime('%H:%M')}"
        row = [Paragraph(time_str.replace('\n', '<br/>'), styles['TimeCell'])]
        for day in active_days:
            entry = lookup.get((day, str(start_time), str(end_time)))
            if entry:
                cell_content = (
                    f"<b>{entry.subject.name}</b><br/>"
                    f"<font size=6 color='#64748b'>{entry.teacher.get_full_name() or entry.teacher.username}</font>"
                )
                if entry.room:
                    cell_content += f"<br/><font size=5 color='#7c3aed'>📍 {entry.room}</font>"
                row.append(Paragraph(cell_content, styles['CellSubject']))
            else:
                row.append(Paragraph('—', styles['CellTeacher']))
        data.append(row)

    return data, active_days


def _build_teacher_grid(teacher, entries, styles):
    """Build the grid data for a teacher's timetable."""
    lookup = {}
    for e in entries:
        key = (e.time_slot.day, str(e.time_slot.start_time), str(e.time_slot.end_time))
        lookup[key] = e

    active_day_set = set(e.time_slot.day for e in entries)
    active_days = [d for d in DAY_ORDER if d in active_day_set]
    if not active_days:
        active_days = DAY_ORDER[:5]

    slot_ids = set(e.time_slot_id for e in entries)
    unique_times = TimeSlot.objects.filter(id__in=slot_ids).values_list(
        'start_time', 'end_time'
    ).distinct().order_by('start_time')

    header = ['Time'] + [DAY_LABELS.get(d, d) for d in active_days]
    data = [header]

    for start_time, end_time in unique_times:
        time_str = f"{start_time.strftime('%H:%M')}\n{end_time.strftime('%H:%M')}"
        row = [Paragraph(time_str.replace('\n', '<br/>'), styles['TimeCell'])]
        for day in active_days:
            entry = lookup.get((day, str(start_time), str(end_time)))
            if entry:
                section_name = f"{entry.section.class_group.name} - {entry.section.name}"
                cell_content = (
                    f"<b>{entry.subject.name}</b><br/>"
                    f"<font size=6 color='#64748b'>{section_name}</font>"
                )
                if entry.room:
                    cell_content += f"<br/><font size=5 color='#7c3aed'>📍 {entry.room}</font>"
                row.append(Paragraph(cell_content, styles['CellSubject']))
            else:
                row.append(Paragraph('—', styles['CellTeacher']))
        data.append(row)

    return data, active_days


def generate_section_timetable_pdf(section):
    """
    Generate a PDF timetable for a given section.
    Returns a BytesIO buffer containing the PDF.
    """
    buffer = io.BytesIO()
    styles = _build_styles()

    entries = TimetableEntry.objects.filter(section=section).select_related(
        'subject', 'teacher', 'time_slot', 'section__class_group'
    )

    if not entries.exists():
        # Return a simple "no data" PDF
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                topMargin=2 * cm, bottomMargin=1.5 * cm)
        doc.build([
            Paragraph(f"Timetable — {section.class_group.name} {section.name}", styles['TitleCustom']),
            Spacer(1, 1 * cm),
            Paragraph("No classes have been scheduled for this section yet.", styles['Normal']),
        ])
        buffer.seek(0)
        return buffer

    data, active_days = _build_section_grid(section, entries, styles)
    n_cols = len(active_days) + 1

    # Calculate column widths
    available_width = landscape(A4)[0] - 3 * cm
    time_col_width = 55
    day_col_width = (available_width - time_col_width) / max(len(active_days), 1)
    col_widths = [time_col_width] + [day_col_width] * len(active_days)

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(_grid_table_style(len(data), n_cols))

    # Build document
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=1.5 * cm, bottomMargin=1 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )

    title = Paragraph(
        f"📅 Timetable — {section.class_group.name} Section {section.name}",
        styles['TitleCustom']
    )
    subtitle = Paragraph(
        f"Academic Year: {section.academic_year} | SMS Pro — School Management System",
        styles['SubTitle']
    )

    doc.build([title, subtitle, table])
    buffer.seek(0)
    return buffer


def generate_teacher_timetable_pdf(teacher):
    """
    Generate a PDF timetable for a given teacher.
    Returns a BytesIO buffer containing the PDF.
    """
    buffer = io.BytesIO()
    styles = _build_styles()

    entries = TimetableEntry.objects.filter(teacher=teacher).select_related(
        'subject', 'teacher', 'time_slot', 'section__class_group'
    )

    teacher_name = teacher.get_full_name() or teacher.username

    if not entries.exists():
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                                topMargin=2 * cm, bottomMargin=1.5 * cm)
        doc.build([
            Paragraph(f"Timetable — {teacher_name}", styles['TitleCustom']),
            Spacer(1, 1 * cm),
            Paragraph("No classes have been assigned to you yet.", styles['Normal']),
        ])
        buffer.seek(0)
        return buffer

    data, active_days = _build_teacher_grid(teacher, entries, styles)
    n_cols = len(active_days) + 1

    available_width = landscape(A4)[0] - 3 * cm
    time_col_width = 55
    day_col_width = (available_width - time_col_width) / max(len(active_days), 1)
    col_widths = [time_col_width] + [day_col_width] * len(active_days)

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(_grid_table_style(len(data), n_cols))

    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=1.5 * cm, bottomMargin=1 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )

    title = Paragraph(f"📅 My Timetable — {teacher_name}", styles['TitleCustom'])
    subtitle = Paragraph(
        f"SMS Pro — School Management System",
        styles['SubTitle']
    )

    doc.build([title, subtitle, table])
    buffer.seek(0)
    return buffer
