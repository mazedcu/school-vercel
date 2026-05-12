from django.utils import timezone
from .models import Invoice

def generate_invoice_number(invoice):
    """Generate invoice number in format: ClassName-YYMM-NNN"""
    now = timezone.now()
    yymm = now.strftime('%y%m')

    # Get class name abbreviation (remove spaces, take first 8 chars)
    class_name = ''
    if invoice.class_group:
        class_name = invoice.class_group.name.replace(' ', '')[:8]
    else:
        # Try to derive from student's section
        try:
            profile = invoice.student.student_profile
            if profile and profile.section:
                class_name = profile.section.class_group.name.replace(' ', '')[:8]
        except Exception:
            class_name = 'GEN'

    prefix = f"{class_name}-{yymm}"

    # Find next serial number for this month
    last_invoice = Invoice.objects.filter(
        invoice_number__startswith=prefix
    ).order_by('-invoice_number').first()

    if last_invoice:
        try:
            last_serial = int(last_invoice.invoice_number.split('-')[-1])
            next_serial = last_serial + 1
        except (ValueError, IndexError):
            next_serial = 1
    else:
        next_serial = 1

    return f"{prefix}-{next_serial:03d}"

def update_invoice_status_and_totals(invoice):
    """Update subtotal, amount_due, amount_paid, and status based on payments and items."""
    from decimal import Decimal
    from django.db.models import Sum
    
    # Recalculate subtotal from line items
    invoice.subtotal = sum(item.amount for item in invoice.line_items.all()) or Decimal('0.00')
    invoice.amount_due = max(invoice.subtotal - invoice.discount_amount, Decimal('0.00'))
    
    # Recalculate total paid from all payments
    invoice.amount_paid = invoice.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Update status based on payment
    if invoice.amount_due > 0 and invoice.amount_paid >= invoice.amount_due:
        invoice.status = Invoice.Status.PAID
    elif invoice.amount_paid > 0:
        invoice.status = Invoice.Status.PARTIAL
    else:
        invoice.status = Invoice.Status.UNPAID
    
    return invoice
