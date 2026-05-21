from django.db import models
from django.conf import settings


class Attendance(models.Model):
    """Daily attendance record for a student."""
    class Status(models.TextChoices):
        PRESENT = 'present', 'Present'
        ABSENT = 'absent', 'Absent'
        LATE = 'late', 'Late'
        NOT_APPLICABLE = 'na', 'Not Applicable'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendances')
    section = models.ForeignKey('academics.Section', on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PRESENT)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='attendances_marked', blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'date'], name='unique_user_attendance')
        ]
        ordering = ['-date']

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.get_status_display()}"
