from django.db import models
from django.conf import settings
from django.utils import timezone


class FeeStructure(models.Model):
    """Defines fee amounts for a class group."""
    class_group = models.ForeignKey('academics.ClassGroup', on_delete=models.CASCADE, related_name='fee_structures')
    name = models.CharField(max_length=100, help_text="e.g., Tuition Fee, Lab Fee")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    academic_year = models.CharField(max_length=10)

    def __str__(self):
        return f"{self.name} - {self.class_group.name} ({self.academic_year}) - Tk.{self.amount}"


class Invoice(models.Model):
    """A fee invoice issued to a student. Supports multiple fee line items and discount."""
    class Status(models.TextChoices):
        UNPAID = 'unpaid', 'Unpaid'
        PAID = 'paid', 'Paid'
        PARTIAL = 'partial', 'Partially Paid'

    invoice_number = models.CharField(max_length=30, unique=True, blank=True, db_index=True)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='invoices')
    class_group = models.ForeignKey('academics.ClassGroup', on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Sum of all line items before discount")
    discount_description = models.CharField(max_length=200, blank=True, help_text="e.g., Sibling Discount, Merit Scholarship")
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Subtotal minus discount")
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNPAID, db_index=True)
    issued_date = models.DateField(auto_now_add=True, db_index=True)
    due_date = models.DateField()

    def recalculate_totals(self):
        """Recalculate subtotal and amount_due using service."""
        from .services import update_invoice_status_and_totals
        update_invoice_status_and_totals(self)

    def save(self, *args, **kwargs):
        from .services import generate_invoice_number, update_invoice_status_and_totals
        # Auto-generate invoice number if not set
        if not self.invoice_number:
            self.invoice_number = generate_invoice_number(self)

        # Update status and totals (only if already exists, otherwise no line items yet)
        if self.pk:
            update_invoice_status_and_totals(self)
        super().save(*args, **kwargs)


    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.student.username} - {self.get_status_display()}"


class InvoiceLineItem(models.Model):
    """A single fee line on an invoice."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items')
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.SET_NULL, null=True, blank=True)
    description = models.CharField(max_length=200, help_text="Fee description")
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.description} - Tk.{self.amount}"


class Payment(models.Model):
    """A payment record against an invoice."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(auto_now_add=True, db_index=True)
    method = models.CharField(max_length=30, default='cash', help_text="e.g., cash, bank, online")
    reference = models.CharField(max_length=100, blank=True)

    # Note: Invoice recalculation is handled by the post_save signal below.
    # Do NOT add a custom save() here — it would conflict with the signal.

    def __str__(self):
        return f"Payment Tk.{self.amount} for Invoice {self.invoice.invoice_number}"


# ─── SIGNALS ──────────────────────────────────────────────────────────────────
# Keep invoice totals and status in sync when line items or payments are
# added/changed (e.g., via Django Admin or bulk operations).

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from finance.services import update_invoice_status_and_totals


@receiver([post_save, post_delete], sender=InvoiceLineItem)
def sync_invoice_on_lineitem_change(sender, instance, **kwargs):
    """Recalculate invoice totals whenever a line item is added or removed."""
    invoice = instance.invoice
    if invoice.pk:
        update_invoice_status_and_totals(invoice)
        Invoice.objects.filter(pk=invoice.pk).update(
            subtotal=invoice.subtotal,
            amount_due=invoice.amount_due,
            status=invoice.status,
        )


@receiver([post_save, post_delete], sender=Payment)
def sync_invoice_on_payment_change(sender, instance, **kwargs):
    """Recalculate invoice status whenever a payment is added or removed."""
    invoice = instance.invoice
    if invoice.pk:
        update_invoice_status_and_totals(invoice)
        Invoice.objects.filter(pk=invoice.pk).update(
            amount_paid=invoice.amount_paid,
            status=invoice.status,
        )
