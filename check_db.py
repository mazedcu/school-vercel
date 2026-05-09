import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

from timetable.models import TimetableEntry, TimeSlot

print(f"Total entries: {TimetableEntry.objects.count()}")
for e in TimetableEntry.objects.all():
    print(f"ID: {e.id}, {e.section} - {e.subject}")

print(f"\nTotal slots: {TimeSlot.objects.count()}")
for s in TimeSlot.objects.all():
    print(f"ID: {s.id}, {s.get_day_display()} {s.start_time}")
