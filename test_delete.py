import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

from timetable.models import TimetableEntry

try:
    e = TimetableEntry.objects.get(id=5)
    print(f"Deleting entry {e}")
    e.delete()
    print("Success")
except Exception as ex:
    print(f"Failed: {ex}")
