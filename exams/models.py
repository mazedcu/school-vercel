from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

class AssessmentType(models.Model):
    """Admin-defined assessment categories (e.g., Quiz, Assignment, Final Term)."""
    name = models.CharField(max_length=50, unique=True)
    
    def __str__(self):
        return self.name

class SubjectWeighting(models.Model):
    """
    Teacher-defined weighting for a specific subject and class.
    """
    section = models.ForeignKey('academics.Section', on_delete=models.CASCADE)
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    teacher = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'})
    academic_year = models.CharField(max_length=10)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['section', 'subject', 'academic_year'], name='unique_subject_weighting')
        ]

    def __str__(self):
        return f"{self.subject} weighting for {self.section} ({self.academic_year})"

class WeightingComponent(models.Model):
    """The individual weights for the SubjectWeighting."""
    weighting_profile = models.ForeignKey(SubjectWeighting, on_delete=models.CASCADE, related_name='components')
    assessment_type = models.ForeignKey(AssessmentType, on_delete=models.CASCADE)
    weight_percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="e.g., 20.00 for 20%")

    def __str__(self):
        return f"{self.assessment_type.name}: {self.weight_percentage}%"

class AssessmentRecord(models.Model):
    """An instance of a test (e.g., 'Chapter 1 Quiz')."""
    section = models.ForeignKey('academics.Section', on_delete=models.CASCADE)
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    assessment_type = models.ForeignKey(AssessmentType, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    total_marks = models.DecimalField(max_digits=6, decimal_places=2)
    date_conducted = models.DateField(db_index=True)

    def __str__(self):
        return f"{self.title} - {self.section} ({self.subject})"

class StudentScore(models.Model):
    """Marks obtained by a student in a specific AssessmentRecord."""
    assessment = models.ForeignKey(AssessmentRecord, on_delete=models.CASCADE, related_name='scores')
    student = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'role': 'student'})
    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['assessment', 'student'], name='unique_student_score')
        ]

    def clean(self):
        if self.marks_obtained > self.assessment.total_marks:
            raise ValidationError({'marks_obtained': _("Marks obtained cannot be greater than total marks.")})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.username}: {self.marks_obtained}/{self.assessment.total_marks} in {self.assessment.title}"


class GradeSetting(models.Model):
    """Admin-defined grade boundaries (e.g., A+ = 90-100)."""
    letter = models.CharField(max_length=5, help_text="e.g., A+, A, B+, B")
    min_score = models.DecimalField(max_digits=5, decimal_places=2, help_text="Minimum percentage")
    max_score = models.DecimalField(max_digits=5, decimal_places=2, help_text="Maximum percentage")
    grade_point = models.DecimalField(max_digits=3, decimal_places=1, default=0, help_text="GPA point value")
    remark = models.CharField(max_length=50, blank=True, help_text="e.g., Excellent, Good, Needs Improvement")

    class Meta:
        ordering = ['-min_score']

    def __str__(self):
        return f"{self.letter} ({self.min_score}% - {self.max_score}%) — {self.remark}"


class SubjectComment(models.Model):
    """Teacher comment on a student's performance in a specific subject."""
    student = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'role': 'student'}, related_name='subject_comments')
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    section = models.ForeignKey('academics.Section', on_delete=models.CASCADE)
    academic_year = models.CharField(max_length=10)
    comment = models.TextField(help_text="Teacher's remark for this student in this subject")
    commented_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='comments_given')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['student', 'subject', 'section', 'academic_year'], name='unique_subject_comment')
        ]

    def __str__(self):
        return f"Comment for {self.student.username} in {self.subject.name}"


# ─── PERIOD-BASED REPORTING ──────────────────────────────────────────────────

class AcademicPeriodConfig(models.Model):
    """School-wide reporting mode for an academic year."""
    class Mode(models.TextChoices):
        QUARTERLY = 'quarterly', 'Quarterly (4 Reports)'
        TERM = 'term', 'Term (2 Reports — Mid & Final)'

    academic_year = models.CharField(max_length=10, unique=True, help_text="e.g. 2026")
    mode = models.CharField(max_length=10, choices=Mode.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='period_configs'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-academic_year']

    def __str__(self):
        return f"{self.academic_year} — {self.get_mode_display()}"


class ReportPeriod(models.Model):
    """An individual reporting period (e.g., Q1, Mid-Term) with date range."""
    config = models.ForeignKey(AcademicPeriodConfig, on_delete=models.CASCADE, related_name='periods')
    label = models.CharField(max_length=50, help_text="e.g. 1st Quarter, Mid-Term")
    sequence = models.PositiveIntegerField(help_text="Display order: 1, 2, 3, 4")
    start_date = models.DateField()
    end_date = models.DateField()
    is_published = models.BooleanField(default=False, help_text="If checked, visible to students/parents")

    class Meta:
        ordering = ['config', 'sequence']
        constraints = [
            models.UniqueConstraint(fields=['config', 'sequence'], name='unique_period_sequence')
        ]

    def __str__(self):
        return f"{self.label} ({self.start_date} — {self.end_date})"


class PeriodWeighting(models.Model):
    """Assessment type weights for a specific reporting period.
    If subject is NULL, the weight is the default for all subjects.
    If subject is set, it overrides the default for that specific subject.
    """
    period = models.ForeignKey(ReportPeriod, on_delete=models.CASCADE, related_name='weightings')
    assessment_type = models.ForeignKey(AssessmentType, on_delete=models.CASCADE)
    subject = models.ForeignKey(
        'academics.Subject', on_delete=models.CASCADE, null=True, blank=True,
        help_text="Leave blank for default weights. Set for subject-specific override."
    )
    weight_percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="e.g. 20.00 for 20%")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['period', 'assessment_type', 'subject'], name='unique_period_subject_weight')
        ]

    def __str__(self):
        subj = f" [{self.subject.name}]" if self.subject else ""
        return f"{self.period.label}{subj} — {self.assessment_type.name}: {self.weight_percentage}%"
