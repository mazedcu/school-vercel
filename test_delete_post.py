import os
import django
from django.test import Client

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

from accounts.models import User
from timetable.models import TimetableEntry
from django.conf import settings

settings.ALLOWED_HOSTS.append('testserver')

# Get an admin user
admin_user = User.objects.filter(role='admin').first()
if not admin_user:
    print("No admin user found")
    exit()

# Get an entry to delete
entry = TimetableEntry.objects.first()
if not entry:
    print("No timetable entry found to delete")
    exit()

print(f"Attempting to delete entry {entry.id}")

client = Client()
client.force_login(admin_user)

response = client.post('/timetable_gen/', {
    'action': 'delete_entry',
    'entry_id': entry.id
}, HTTP_HOST='testserver')

print(f"Response status: {response.status_code}")
print(f"Response URL: {response.url if hasattr(response, 'url') else 'No URL'}")

# Check if it was deleted
still_exists = TimetableEntry.objects.filter(id=entry.id).exists()
print(f"Entry still exists? {still_exists}")

try:
    for msg in response.wsgi_request._messages:
        print(f"Message: {msg.message}")
except:
    pass
