import os, django, re
os.environ['DJANGO_SETTINGS_MODULE'] = 'sms_project.settings'
django.setup()

from django.test import RequestFactory
from django.contrib.sessions.backends.signed_cookies import SessionStore
from accounts.models import User
from finance.views import manage_finance
from django.contrib.messages.storage.fallback import FallbackStorage

factory = RequestFactory()
req = factory.get('/manage_finance/')
req.user = User.objects.filter(role='admin').first()
req.session = SessionStore()
setattr(req, '_messages', FallbackStorage(req))

resp = manage_finance(req)
content = resp.content.decode()

# Find the bulk invoice button area
idx = content.find('Issue Bulk Invoices')
if idx > 0:
    snippet = content[max(0, idx-300):idx+50]
    print("=== BUTTON AREA ===")
    print(snippet)
else:
    print("Button text not found in rendered output!")

# Also check for submitBulkInvoice in the script
idx2 = content.find('submitBulkInvoice')
if idx2 > 0:
    print("\n=== FUNCTION DEFINITION AREA ===")
    print(content[idx2:idx2+100])
else:
    print("submitBulkInvoice not found in rendered output!")
