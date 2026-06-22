from django.db import models
from django.utils import timezone
from accounts.models import User
from academics.models import Subject, Section


class LessonPlan(models.Model):

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    # ── Core identifiers ──────────────────────────────────────────────
    teacher = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='lesson_plans',
        limit_choices_to={'role__in': ['teacher', 'coordinator']}
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='lesson_plans')
    section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name='lesson_plans')
    date = models.DateField(help_text="Date this lesson will be delivered", db_index=True)
    duration = models.CharField(max_length=50, help_text="e.g. 45 minutes")

    # ── Plan content fields ───────────────────────────────────────────
    main_topic = models.CharField(max_length=200, help_text="The broad topic this lesson belongs to")
    lesson_title = models.CharField(max_length=200, help_text="Specific title for this lesson")
    learning_objectives = models.TextField(help_text="What students will be able to do by the end")
    prior_knowledge = models.TextField(help_text="What students already know that this lesson builds on")
    resources = models.TextField(help_text="Materials, textbooks, digital tools, etc.")
    starter = models.TextField(help_text="Warm-up or hook activity (5–10 min)")
    main_lesson = models.TextField(help_text="Core instruction / teacher-led content")
    activities = models.TextField(help_text="Student tasks and exercises")
    differentiation = models.TextField(help_text="Support for SEN / extension for higher ability")
    plenary = models.TextField(help_text="Wrap-up, review, and assessment of learning")

    # ── Workflow ──────────────────────────────────────────────────────
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT, db_index=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_lesson_plans'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_notes = models.TextField(blank=True, help_text="Coordinator feedback or rejection reason")

    # ── Meta ──────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.lesson_title} — {self.subject} ({self.date})"

    def can_edit(self, user):
        """Teacher can edit if draft or rejected and they own it."""
        return (
            user == self.teacher and
            self.status in [self.Status.DRAFT, self.Status.REJECTED]
        )

    def can_review(self, user):
        """Admin can always review. Coordinator only if they teach this subject via timetable."""
        from timetable.models import TimetableEntry
        if user.role == User.Role.ADMIN:
            return True
        if user.role == User.Role.COORDINATOR:
            return TimetableEntry.objects.filter(
                teacher=user, subject=self.subject
            ).exists()
        return False
