from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class LeaveType(models.Model):
    """Admin-defined leave categories (e.g., Medical, Casual, Maternity)."""
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, help_text="Optional notes about this leave type")

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class LeavePolicy(models.Model):
    """Defines how many days of each leave type are allocated per academic year."""
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name='policies')
    academic_year = models.ForeignKey('academics.AcademicYear', on_delete=models.CASCADE, related_name='leave_policies')
    allocated_days = models.PositiveIntegerField(default=0, help_text="Number of days allocated per year")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['leave_type', 'academic_year'], name='unique_leave_policy')
        ]
        ordering = ['-academic_year__start_date', 'leave_type__name']
        verbose_name_plural = "Leave Policies"

    def __str__(self):
        return f"{self.leave_type.name} — {self.allocated_days} days ({self.academic_year.name})"


class LeaveApplication(models.Model):
    """An employee's request for leave with two-tier approval workflow."""

    class Category(models.TextChoices):
        ADVANCE = 'advance', 'Advance Leave'
        EMERGENCY = 'emergency', 'Emergency Leave'
        EARLY = 'early', 'Early Leave'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COORDINATOR_APPROVED = 'coordinator_approved', 'Coordinator Approved'
        ADMIN_APPROVED = 'admin_approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='leave_applications'
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, null=True, blank=True)
    category = models.CharField(max_length=10, choices=Category.choices)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True)
    departure_time = models.TimeField(null=True, blank=True, help_text="Required for Early Leave")
    reason = models.TextField(help_text="Reason for leave")

    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PENDING, db_index=True)

    # Coordinator review
    coordinator_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='coordinator_reviews'
    )
    coordinator_reviewed_at = models.DateTimeField(null=True, blank=True)
    coordinator_remarks = models.TextField(blank=True)

    # Admin review
    admin_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='admin_leave_reviews'
    )
    admin_reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_remarks = models.TextField(blank=True)

    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-applied_at']

    def clean(self):
        if self.category == self.Category.EARLY:
            if not self.departure_time:
                raise ValidationError("Departure time is required for Early Leave.")
            
            # Enforce 3 early leaves per month rule
            if self.start_date:
                # Count approved early leaves for this user in the same month
                approved_early_leaves = LeaveApplication.objects.filter(
                    applicant=self.applicant,
                    category=self.Category.EARLY,
                    status=self.Status.ADMIN_APPROVED,
                    start_date__year=self.start_date.year,
                    start_date__month=self.start_date.month
                ).exclude(pk=self.pk).count()
                
                if approved_early_leaves >= 3:
                    raise ValidationError("You have already used the maximum 3 Early Leaves allowed for this month.")

        else:
            # Standard leaves need end date and leave type
            if not self.leave_type:
                raise ValidationError("Leave Type is required for standard leaves.")
            if not self.end_date:
                raise ValidationError("End Date is required for standard leaves.")
            if self.end_date and self.start_date and self.end_date < self.start_date:
                raise ValidationError("End date cannot be before start date.")
            
        today = timezone.now().date()
        if self.category == self.Category.EMERGENCY and self.start_date != today:
            raise ValidationError("Emergency leave must start today.")
        if self.category == self.Category.ADVANCE and self.start_date <= today:
            raise ValidationError("Advance leave must start on a future date.")

    @property
    def total_days(self):
        """Calculate number of leave days (inclusive)."""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    def __str__(self):
        leave_name = self.leave_type.name if self.leave_type else self.get_category_display()
        return f"{self.applicant.get_full_name() or self.applicant.username} — {leave_name} ({self.get_status_display()})"
