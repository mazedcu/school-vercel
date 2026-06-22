from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class TimeSlot(models.Model):
    """Defines a specific time slot during the school day."""
    DAY_CHOICES = [
        ("monday",    "Monday"),
        ("tuesday",   "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday",  "Thursday"),
        ("friday",    "Friday"),
        ("saturday",  "Saturday"),
        ("sunday",    "Sunday"),
    ]

    day = models.CharField(max_length=10, choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['day', 'start_time'], name='unique_timeslot')
        ]
        ordering = ['day', 'start_time']

    def __str__(self):
        return f"{self.get_day_display()} {self.start_time:%I:%M %p}-{self.end_time:%I:%M %p}"


class TimetableEntry(models.Model):
    """Assigns a subject and teacher to a section in a specific time slot."""
    section = models.ForeignKey('academics.Section', on_delete=models.CASCADE, related_name='timetable_entries')
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    teacher = models.ForeignKey('accounts.User', on_delete=models.CASCADE, limit_choices_to={'role': 'teacher'})
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    room = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['section', 'time_slot'], name='unique_section_timeslot')
        ]

    def clean(self):
        super().clean()
        
        # 1. Teacher Conflict: A teacher cannot be in two places at once
        teacher_conflict = TimetableEntry.objects.filter(
            teacher=self.teacher,
            time_slot=self.time_slot
        ).exclude(pk=self.pk)
        
        if teacher_conflict.exists():
            raise ValidationError({
                'teacher': _(f"Teacher {self.teacher.username} is already assigned to another class during this time slot.")
            })

        # 2. Room Conflict (if room is provided)
        if self.room:
            room_conflict = TimetableEntry.objects.filter(
                room=self.room,
                time_slot=self.time_slot
            ).exclude(pk=self.pk)
            
            if room_conflict.exists():
                raise ValidationError({
                    'room': _(f"Room {self.room} is already booked for this time slot.")
                })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.section} - {self.subject} ({self.time_slot})"
