from django.db import models
from django.core.exceptions import ValidationError


TEACHING_ROLES = ('teacher', 'coordinator')


def _overlapping(slot, prefix='time_slot__'):
    """Lookup kwargs for slots on the same day whose times overlap `slot`."""
    return {
        f'{prefix}day': slot.day,
        f'{prefix}start_time__lt': slot.end_time,
        f'{prefix}end_time__gt': slot.start_time,
    }


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

    def clean(self):
        super().clean()
        if self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValidationError("End time must be after start time.")
            clash = TimeSlot.objects.filter(**_overlapping(self, prefix='')).exclude(pk=self.pk).first()
            if clash:
                raise ValidationError(f"Overlaps the existing period {clash}.")

    def __str__(self):
        return f"{self.get_day_display()} {self.start_time:%I:%M %p}-{self.end_time:%I:%M %p}"


class TimetableEntry(models.Model):
    """Assigns a subject and teacher to a section in a specific time slot."""
    section = models.ForeignKey('academics.Section', on_delete=models.CASCADE, related_name='timetable_entries')
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    teacher = models.ForeignKey('accounts.User', on_delete=models.CASCADE,
                                limit_choices_to={'role__in': TEACHING_ROLES})
    time_slot = models.ForeignKey(TimeSlot, on_delete=models.CASCADE)
    room = models.CharField(max_length=50, blank=True, default='')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['section', 'time_slot'], name='unique_section_timeslot')
        ]

    def clean(self):
        super().clean()
        self.room = (self.room or '').strip()
        if not (self.time_slot_id and self.section_id and self.teacher_id):
            return  # field validation reports the missing values
        slot = self.time_slot
        overlapping = TimetableEntry.objects.filter(**_overlapping(slot)).exclude(pk=self.pk) \
            .select_related('section__class_group', 'subject', 'teacher', 'time_slot')
        errors = {}

        if self.teacher.role not in TEACHING_ROLES:
            errors['teacher'] = "Only teachers and coordinators can be scheduled."

        # 1. Section: one class at a time
        clash = overlapping.filter(section_id=self.section_id).first()
        if clash:
            errors['time_slot'] = (
                f"This section already has {clash.subject.name} at {clash.time_slot}."
            )

        # 2. Teacher: cannot be in two places at once
        clash = overlapping.filter(teacher_id=self.teacher_id).first()
        if clash and 'teacher' not in errors:
            name = self.teacher.get_full_name() or self.teacher.username
            errors['teacher'] = (
                f"{name} already teaches {clash.section.class_group.name} – {clash.section.name} "
                f"({clash.subject.name}) at {clash.time_slot}."
            )

        # 3. Room: cannot be double-booked (case-insensitive)
        if self.room:
            clash = overlapping.filter(room__iexact=self.room).first()
            if clash:
                errors['room'] = (
                    f"Room {clash.room} is already used by {clash.section.class_group.name} – "
                    f"{clash.section.name} at {clash.time_slot}."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.section} - {self.subject} ({self.time_slot})"
