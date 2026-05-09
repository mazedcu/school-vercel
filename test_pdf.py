import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sms_project.settings')
django.setup()

from academics.models import Section
from accounts.models import User
from timetable.pdf_utils import generate_section_timetable_pdf, generate_teacher_timetable_pdf

# Test class-wise PDF
section = Section.objects.first()
if section:
    print(f"Generating PDF for section: {section}")
    buf = generate_section_timetable_pdf(section)
    with open('test_section_timetable.pdf', 'wb') as f:
        f.write(buf.read())
    print(f"Section PDF generated: test_section_timetable.pdf ({os.path.getsize('test_section_timetable.pdf')} bytes)")

# Test teacher-wise PDF
teacher = User.objects.filter(role='teacher').first()
if teacher:
    print(f"\nGenerating PDF for teacher: {teacher.get_full_name() or teacher.username}")
    buf = generate_teacher_timetable_pdf(teacher)
    with open('test_teacher_timetable.pdf', 'wb') as f:
        f.write(buf.read())
    print(f"Teacher PDF generated: test_teacher_timetable.pdf ({os.path.getsize('test_teacher_timetable.pdf')} bytes)")

print("\nDone!")
