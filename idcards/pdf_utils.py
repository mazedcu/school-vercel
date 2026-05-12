"""
ID Card PDF generation utilities.
Generates print-ready CR80 (85.6mm x 54mm) ID cards using ReportLab Canvas.
Layout: student cards in indigo, teacher cards in green.
"""
import io
import os

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

# ── Card dimensions (CR80 credit card standard) ────────────────────────────
CARD_W = 85.6 * mm
CARD_H = 54.0 * mm

# ── Palette ────────────────────────────────────────────────────────────────
STUDENT_HEADER  = colors.HexColor('#312e81')   # Indigo
TEACHER_HEADER  = colors.HexColor('#064e3b')   # Emerald
WHITE           = colors.white
LIGHT_GRAY      = colors.HexColor('#f1f5f9')
DARK_TEXT       = colors.HexColor('#0f172a')
MUTED_TEXT      = colors.HexColor('#64748b')
STUDENT_BADGE   = colors.HexColor('#6366f1')
TEACHER_BADGE   = colors.HexColor('#10b981')

SCHOOL_NAME = "OpDevSM"
SCHOOL_SUB  = "School Management System"


def _draw_card(c, x, y, header_color, badge_color, role_label,
               full_name, line1, line2, line3, user_id, photo_path=None):
    """
    Draw one ID card at canvas position (x, y).
    x, y = bottom-left corner of card.
    """
    W, H = CARD_W, CARD_H

    # ── Card background ──────────────────────────────────────────────────
    c.setFillColor(WHITE)
    c.roundRect(x, y, W, H, 4 * mm, fill=1, stroke=0)

    # ── Header bar ───────────────────────────────────────────────────────
    header_h = 13 * mm
    c.setFillColor(header_color)
    # Top corners rounded, bottom straight
    c.roundRect(x, y + H - header_h, W, header_h, 4 * mm, fill=1, stroke=0)
    c.rect(x, y + H - header_h, W, header_h / 2, fill=1, stroke=0)

    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x + W / 2, y + H - 6.5 * mm, SCHOOL_NAME)
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(x + W / 2, y + H - 10 * mm, SCHOOL_SUB)

    # ── Footer strip ─────────────────────────────────────────────────────
    footer_h = 8 * mm
    c.setFillColor(LIGHT_GRAY)
    c.rect(x, y, W, footer_h, fill=1, stroke=0)

    # Role badge
    badge_w = 22 * mm
    badge_h = 5 * mm
    bx = x + W - badge_w - 4 * mm
    by = y + 1.5 * mm
    c.setFillColor(badge_color)
    c.roundRect(bx, by, badge_w, badge_h, 2 * mm, fill=1, stroke=0)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(bx + badge_w / 2, by + 1.5 * mm, role_label)

    # User ID text
    c.setFillColor(MUTED_TEXT)
    c.setFont("Helvetica", 6)
    c.drawString(x + 3 * mm, y + 2.5 * mm, f"ID: {user_id}")

    # ── Photo area ───────────────────────────────────────────────────────
    photo_x = x + 3 * mm
    photo_y = y + footer_h + 2 * mm
    photo_w = 18 * mm
    photo_h = 22 * mm

    if photo_path and os.path.exists(photo_path):
        try:
            img = ImageReader(photo_path)
            c.drawImage(img, photo_x, photo_y, photo_w, photo_h,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            _draw_placeholder(c, photo_x, photo_y, photo_w, photo_h, header_color)
    else:
        _draw_placeholder(c, photo_x, photo_y, photo_w, photo_h, header_color)

    # ── Info area (right of photo) ────────────────────────────────────────
    info_x = photo_x + photo_w + 3 * mm
    info_w = W - photo_w - 9 * mm

    # Name
    c.setFillColor(DARK_TEXT)
    c.setFont("Helvetica-Bold", 8.5)
    # Truncate long names
    name_display = full_name if len(full_name) <= 20 else full_name[:18] + "…"
    c.drawString(info_x, y + H - header_h - 7 * mm, name_display)

    # Divider
    c.setStrokeColor(colors.HexColor('#e2e8f0'))
    c.setLineWidth(0.4)
    c.line(info_x, y + H - header_h - 8.5 * mm,
           info_x + info_w, y + H - header_h - 8.5 * mm)

    # Detail lines
    detail_start_y = y + H - header_h - 12 * mm
    for label, value in [line1, line2, line3]:
        if not value:
            continue
        c.setFont("Helvetica-Bold", 5.5)
        c.setFillColor(MUTED_TEXT)
        c.drawString(info_x, detail_start_y, label)
        c.setFont("Helvetica", 5.5)
        c.setFillColor(DARK_TEXT)
        val_display = str(value) if len(str(value)) <= 22 else str(value)[:20] + "…"
        c.drawString(info_x + 14 * mm, detail_start_y, val_display)
        detail_start_y -= 4 * mm

    # ── Card border ───────────────────────────────────────────────────────
    c.setStrokeColor(colors.HexColor('#e2e8f0'))
    c.setLineWidth(0.5)
    c.roundRect(x, y, W, H, 4 * mm, fill=0, stroke=1)


def _draw_placeholder(c, x, y, w, h, color):
    """Draw a placeholder silhouette when no photo is available."""
    c.setFillColor(colors.HexColor('#e0e7ff'))
    c.roundRect(x, y, w, h, 2 * mm, fill=1, stroke=0)
    # Simple person icon
    c.setFillColor(color)
    cx = x + w / 2
    # Head circle
    r = 4 * mm
    c.circle(cx, y + h - 7 * mm, r, fill=1, stroke=0)
    # Body
    c.setFillColor(color)
    c.ellipse(cx - 5 * mm, y + 1 * mm, cx + 5 * mm, y + h - 8 * mm, fill=1, stroke=0)


def generate_student_id_card(student_user):
    """
    Generate a single student ID card PDF.
    Returns a BytesIO buffer.
    """
    profile = getattr(student_user, 'student_profile', None)
    section = profile.section if profile else None

    photo_path = profile.photo.path if (profile and profile.photo) else None
    full_name  = student_user.get_full_name() or student_user.username
    roll       = profile.roll_number if profile else '—'
    section_str = f"{section.class_group.name} - {section.name}" if section else "Unassigned"
    year       = section.academic_year if section else '—'

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(CARD_W, CARD_H))
    _draw_card(
        c, 0, 0,
        header_color=STUDENT_HEADER,
        badge_color=STUDENT_BADGE,
        role_label="STUDENT",
        full_name=full_name,
        line1=("Roll:", roll),
        line2=("Class:", section_str),
        line3=("Year:", year),
        user_id=student_user.id,
        photo_path=photo_path,
    )
    c.save()
    buf.seek(0)
    return buf


def generate_teacher_id_card(teacher_user):
    """
    Generate a single teacher ID card PDF.
    Returns a BytesIO buffer.
    """
    profile = getattr(teacher_user, 'teacher_profile', None)

    photo_path  = profile.photo.path if (profile and profile.photo) else None
    full_name   = teacher_user.get_full_name() or teacher_user.username
    emp_id      = profile.employee_id if profile else '—'
    designation = profile.specialization if profile else '—'
    joined      = profile.date_of_joining.strftime('%d %b %Y') if (profile and profile.date_of_joining) else '—'

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(CARD_W, CARD_H))
    _draw_card(
        c, 0, 0,
        header_color=TEACHER_HEADER,
        badge_color=TEACHER_BADGE,
        role_label="TEACHER",
        full_name=full_name,
        line1=("Emp ID:", emp_id),
        line2=("Subject:", designation),
        line3=("Joined:", joined),
        user_id=teacher_user.id,
        photo_path=photo_path,
    )
    c.save()
    buf.seek(0)
    return buf


def generate_bulk_student_cards(section):
    """
    Generate a multi-card PDF with all students in a section.
    Layout: 2 columns × 2 rows per A4 page (4 cards per page).
    Returns a BytesIO buffer.
    """
    from reportlab.lib.pagesizes import A4

    students = section.students.select_related('user').all()

    buf    = io.BytesIO()
    PAGE_W, PAGE_H = A4
    MARGIN = 10 * mm
    GAP    = 5 * mm

    # 2 cols, 2 rows — centred on A4
    col_w  = CARD_W
    col_h  = CARD_H
    grid_w = 2 * col_w + GAP
    grid_h = 2 * col_h + GAP
    start_x = (PAGE_W - grid_w) / 2
    start_y = (PAGE_H - grid_h) / 2

    c = canvas.Canvas(buf, pagesize=A4)

    positions = [
        (start_x,             start_y + col_h + GAP),  # top-left
        (start_x + col_w + GAP, start_y + col_h + GAP),  # top-right
        (start_x,             start_y),                  # bottom-left
        (start_x + col_w + GAP, start_y),                # bottom-right
    ]

    # Draw cut guides
    def _cut_guides(c):
        c.setStrokeColor(colors.HexColor('#94a3b8'))
        c.setLineWidth(0.3)
        c.setDash(3, 3)
        # Vertical guide
        mid_x = PAGE_W / 2
        c.line(mid_x, MARGIN, mid_x, PAGE_H - MARGIN)
        # Horizontal guide
        mid_y = PAGE_H / 2
        c.line(MARGIN, mid_y, PAGE_W - MARGIN, mid_y)
        c.setDash()

    slot = 0
    for student_profile in students:
        student_user = student_profile.user
        profile      = student_profile
        section_obj  = profile.section
        photo_path   = profile.photo.path if profile.photo else None
        full_name    = student_user.get_full_name() or student_user.username
        roll         = profile.roll_number or '—'
        section_str  = f"{section_obj.class_group.name} - {section_obj.name}" if section_obj else '—'
        year         = section_obj.academic_year if section_obj else '—'

        if slot == 0:
            c.setFillColor(WHITE)
            c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
            _cut_guides(c)

            # Page header
            c.setFillColor(STUDENT_HEADER)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(PAGE_W / 2, PAGE_H - 8 * mm,
                                f"ID Cards — {section_obj.class_group.name} Section {section_obj.name} ({section_obj.academic_year})")

        px, py = positions[slot]
        _draw_card(
            c, px, py,
            header_color=STUDENT_HEADER,
            badge_color=STUDENT_BADGE,
            role_label="STUDENT",
            full_name=full_name,
            line1=("Roll:", roll),
            line2=("Class:", section_str),
            line3=("Year:", year),
            user_id=student_user.id,
            photo_path=photo_path,
        )

        slot += 1
        if slot == 4:
            c.showPage()
            slot = 0

    if slot > 0:
        c.showPage()

    c.save()
    buf.seek(0)
    return buf
