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
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNPAID)
    issued_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()

    def recalculate_totals(self):
        """Recalculate subtotal and amount_due from line items."""
        from decimal import Decimal
        self.subtotal = sum(item.amount for item in self.line_items.all()) or Decimal('0.00')
        self.amount_due = max(self.subtotal - self.discount_amount, Decimal('0.00'))

    def save(self, *args, **kwargs):
        from decimal import Decimal
        # Auto-generate invoice number if not set
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()

        # Update status based on payment
        if self.amount_due > 0 and self.amount_paid >= self.amount_due:
            self.status = self.Status.PAID
        elif self.amount_paid > 0:
            self.status = self.Status.PARTIAL
        else:
            self.status = self.Status.UNPAID
        super().save(*args, **kwargs)

    def _generate_invoice_number(self):
        """Generate invoice number in format: ClassName-YYMM-NNN"""
        now = timezone.now()
        yymm = now.strftime('%y%m')

        # Get class name abbreviation (remove spaces, take first 8 chars)
        class_name = ''
        if self.class_group:
            class_name = self.class_group.name.replace(' ', '')[:8]
        else:
            # Try to derive from student's section
            try:
                profile = self.student.student_profile
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
    payment_date = models.DateField(auto_now_add=True)
    method = models.CharField(max_length=30, default='cash', help_text="e.g., cash, bank, online")
    reference = models.CharField(max_length=100, blank=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update invoice paid amount
        total_paid = self.invoice.payments.aggregate(total=models.Sum('amount'))['total'] or 0
        self.invoice.amount_paid = total_paid
        self.invoice.save()

    def __str__(self):
        return f"Payment Tk.{self.amount} for Invoice {self.invoice.invoice_number}"
