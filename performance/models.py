"""
performance/models.py — Staff Performance Management

Models:
  PerformanceCycle  — A named evaluation period (draft → active → closed)
  KPISection        — Logical grouping of KPIs within a cycle per role type
  KPI               — An individual indicator with weight and data source
  StaffEvaluation   — One evaluation record per (staff × cycle)
  KPIScore          — A score (0-100) per (evaluation × KPI)
"""
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class PerformanceCycle(models.Model):
    """A named evaluation period set by admin."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        ACTIVE = 'active', 'Active'
        CLOSED = 'closed', 'Closed'

    name = models.CharField(max_length=200, help_text="e.g., 'Term 1 — 2025-26 Performance Review'")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='performance_cycles_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} [{self.get_status_display()}]"

    def total_weight_for_role(self, role_type):
        """Return sum of KPI weights for this role type in this cycle."""
        from django.db.models import Sum
        result = KPI.objects.filter(
            section__cycle=self,
            section__role_type=role_type
        ).aggregate(total=Sum('max_weight'))['total']
        return result or 0


class KPISection(models.Model):
    """A logical grouping of KPIs (e.g., Timeliness, Academic Quality)."""

    class RoleType(models.TextChoices):
        TEACHER = 'teacher', 'Teacher'
        COORDINATOR = 'coordinator', 'Coordinator'

    cycle = models.ForeignKey(PerformanceCycle, on_delete=models.CASCADE, related_name='sections')
    role_type = models.CharField(max_length=15, choices=RoleType.choices)
    name = models.CharField(max_length=100, help_text="e.g., Timeliness, Academic Quality")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return f"{self.name} [{self.get_role_type_display()}] — {self.cycle.name}"


class KPI(models.Model):
    """An individual Key Performance Indicator within a section."""
    section = models.ForeignKey(KPISection, on_delete=models.CASCADE, related_name='kpis')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, help_text="Detailed description of what is measured")
    data_source = models.CharField(
        max_length=200,
        help_text="Where data comes from, e.g., 'Attendance system', 'HOD observation', 'Student survey'"
    )
    max_weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Weight as percentage, e.g. 15.00 for 15%. All KPIs for a role must total 100."
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'title']

    def __str__(self):
        return f"{self.title} ({self.max_weight}%) — {self.section.name}"


class StaffEvaluation(models.Model):
    """One evaluation per staff member per cycle."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'

    cycle = models.ForeignKey(PerformanceCycle, on_delete=models.CASCADE, related_name='evaluations')
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='evaluations_received'
    )
    evaluated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='evaluations_given'
    )
    role_type = models.CharField(max_length=15, choices=KPISection.RoleType.choices)
    overall_comment = models.TextField(blank=True, help_text="Evaluator's overall remarks")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    final_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Calculated weighted score out of 100"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['cycle', 'staff'], name='unique_staff_per_cycle')
        ]
        ordering = ['staff__first_name', 'staff__last_name']

    def __str__(self):
        return f"{self.staff.get_full_name() or self.staff.username} — {self.cycle.name}"


class KPIScore(models.Model):
    """Score given to a staff member on a specific KPI."""
    evaluation = models.ForeignKey(StaffEvaluation, on_delete=models.CASCADE, related_name='kpi_scores')
    kpi = models.ForeignKey(KPI, on_delete=models.CASCADE, related_name='scores')
    score = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Score 0–100 for this KPI"
    )
    comment = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['evaluation', 'kpi'], name='unique_kpi_score_per_eval')
        ]

    def clean(self):
        if self.score < 0 or self.score > 100:
            raise ValidationError({'score': 'Score must be between 0 and 100.'})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.kpi.title}: {self.score}/100"
