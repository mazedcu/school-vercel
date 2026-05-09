from django.db import models
from django.conf import settings


class FeeStructure(models.Model):
    """Defines fee amounts for a class group."""
    class_group = models.ForeignKey('academics.ClassGroup', on_delete=models.CASCADE, related_name='fee_structures')
    name = models.CharField(max_length=100, help_text="e.g., Tuition Fee, Lab Fee")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    academic_year = models.CharField(max_length=10)

    def __str__(self):
        return f"{self.name} - {self.class_group.name} ({self.academic_year}) - Rs.{self.amount}"


class Invoice(models.Model):
    """A fee invoice issued to a student."""
    class Status(models.TextChoices):
        UNPAID = 'unpaid', 'Unpaid'
        PAID = 'paid', 'Paid'
        PARTIAL = 'partial', 'Partially Paid'

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='invoices')
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UNPAID)
    issued_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()

    def save(self, *args, **kwargs):
        if self.amount_paid >= self.amount_due:
            self.status = self.Status.PAID
        elif self.amount_paid > 0:
            self.status = self.Status.PARTIAL
        else:
            self.status = self.Status.UNPAID
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invoice #{self.pk} - {self.student.username} - {self.get_status_display()}"


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
        return f"Payment Rs.{self.amount} for Invoice #{self.invoice.pk}"
