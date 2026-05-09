from django.db import models
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
    date_conducted = models.DateField()

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

