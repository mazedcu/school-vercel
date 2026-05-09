import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms_project.settings")
django.setup()

from accounts.models import User

# Create superuser
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'adminpass', role=User.Role.ADMIN)
    print("Superuser created: admin / adminpass")
