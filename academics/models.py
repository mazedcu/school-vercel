from django.db import models
from django.core.exceptions import ValidationError

class AcademicYear(models.Model):
    """School-wide academic year with a specific time period."""
    name = models.CharField(max_length=20, unique=True, help_text="e.g. 2026-2027")
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(
        default=False, 
        help_text="Only one academic year can be active at a time."
    )

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.start_date.strftime('%b %Y')} - {self.end_date.strftime('%b %Y')})"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("Start date cannot be after end date.")

    def save(self, *args, **kwargs):
        self.clean()
        if self.is_active:
            # Deactivate all other academic years
            AcademicYear.objects.exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)

class ClassGroup(models.Model):
    """Represents a grade level (e.g., Grade 1, Grade 2)."""
    name = models.CharField(max_length=50, unique=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['display_order']

    def __str__(self):
        return self.name


class Section(models.Model):
    """Represents a section within a class (e.g., Section A, Section B)."""
    name = models.CharField(max_length=10)
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name='sections')
    academic_year = models.CharField(max_length=10)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'class_group', 'academic_year'], name='unique_section')
        ]
        ordering = ['class_group__display_order', 'name']

    def __str__(self):
        return f"{self.class_group.name} - {self.name} ({self.academic_year})"


class Subject(models.Model):
    """Represents a subject (e.g., Mathematics, Science)."""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.code})"
