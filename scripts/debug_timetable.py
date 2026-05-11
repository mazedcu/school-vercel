import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

from timetable.models import TimetableEntry, TimeSlot
from academics.models import Section

print("--- All Time Slots ---")
for ts in TimeSlot.objects.all().order_by('day', 'start_time'):
    print(f"ID: {ts.id} | {ts.day} | {ts.start_time} - {ts.end_time}")

print("\n--- All Timetable Entries ---")
for e in TimetableEntry.objects.all():
    print(f"ID: {e.id} | Section: {e.section} | Subject: {e.subject} | Teacher: {e.teacher} | TimeSlot: {e.time_slot.day} {e.time_slot.start_time}-{e.time_slot.end_time}")
