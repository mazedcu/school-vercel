"""
Base PDF utilities for the school management system.
Contains shared styles, colors, and layout helpers for ReportLab.
"""
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ── Shared Colour Palette ──────────────────────────────────────────────────
PRIMARY_DARK = colors.HexColor('#312e81')  # Indigo 900
PRIMARY      = colors.HexColor('#4338ca')  # Indigo 700
SUCCESS      = colors.HexColor('#059669')  # Emerald 600
WARNING      = colors.HexColor('#d97706')  # Amber 600
DANGER       = colors.HexColor('#dc2626')  # Red 600
TEXT_MAIN    = colors.HexColor('#0f172a')  # Slate 900
TEXT_MUTED   = colors.HexColor('#64748b')  # Slate 500
BG_LIGHT     = colors.HexColor('#f8fafc')  # Slate 50
BORDER       = colors.HexColor('#e2e8f0')  # Slate 200

def get_base_styles():
    """Return a dictionary of common ReportLab styles."""
    styles = getSampleStyleSheet()
    
    # Custom Title
    styles.add(ParagraphStyle(
        'MainTitle', parent=styles['Title'],
        fontSize=18, textColor=PRIMARY_DARK, spaceAfter=4 * mm,
        alignment=TA_CENTER, fontName='Helvetica-Bold'
    ))
    
    # Custom Subtitle
    styles.add(ParagraphStyle(
        'SubTitle', parent=styles['Normal'],
        fontSize=10, textColor=TEXT_MUTED, spaceAfter=8 * mm,
        alignment=TA_CENTER
    ))
    
    # Table Header
    styles.add(ParagraphStyle(
        'TableHeader', parent=styles['Normal'],
        fontSize=9, textColor=colors.white, fontName='Helvetica-Bold',
        alignment=TA_CENTER
    ))
    
    # Table Cell
    styles.add(ParagraphStyle(
        'TableCell', parent=styles['Normal'],
        fontSize=8, textColor=TEXT_MAIN, alignment=TA_CENTER
    ))
    
    return styles

def draw_footer(canvas, doc, school_name="OpDevSM School Management System"):
    """Standard footer with page number and school name."""
    canvas.saveState()
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(TEXT_MUTED)
    
    # Page number
    page_num = canvas.getPageNumber()
    text = f"Page {page_num} | {school_name}"
    
    # Centered at bottom
    canvas.drawCentredString(doc.width / 2 + doc.leftMargin, 10 * mm, text)
    canvas.restoreState()
