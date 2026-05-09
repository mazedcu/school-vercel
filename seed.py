import os
import django
import datetime

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms_project.settings")
django.setup()

from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from students.models import StudentProfile
from timetable.models import TimeSlot
from exams.models import AssessmentType

# ── Users ──
admin_user = User.objects.filter(username='admin').first()
if not admin_user:
    admin_user = User.objects.create_superuser('admin', 'admin@school.com', 'adminpass', role=User.Role.ADMIN, first_name='Principal', last_name='Admin')
    print("Admin created")

# Teachers
for i, name in enumerate(['Mr. Ahmed', 'Ms. Fatima', 'Mr. Khan'], 1):
    parts = name.split()
    u, c = User.objects.get_or_create(username=f'teacher{i}', defaults={
        'role': User.Role.TEACHER, 'first_name': parts[0].strip('.'), 'last_name': parts[1]
    })
    if c:
        u.set_password('teacherpass')
        u.save()
        print(f"Created teacher: {name}")

# Classes & Sections
for grade_num in [9, 10]:
    cg, _ = ClassGroup.objects.get_or_create(name=f'Grade {grade_num}', defaults={'display_order': grade_num})
    for sec_name in ['A', 'B']:
        Section.objects.get_or_create(name=sec_name, class_group=cg, academic_year='2026')

# Subjects
for name, code in [('Mathematics', 'MATH'), ('Science', 'SCI'), ('English', 'ENG'), ('History', 'HIST')]:
    Subject.objects.get_or_create(code=code, defaults={'name': name})

# Students (in Grade 10 A)
section_10a = Section.objects.filter(class_group__name='Grade 10', name='A').first()
for i in range(1, 6):
    u, c = User.objects.get_or_create(username=f'student{i}', defaults={
        'role': User.Role.STUDENT, 'first_name': f'Student', 'last_name': f'{i}'
    })
    if c:
        u.set_password('studentpass')
        u.save()
    if section_10a:
        StudentProfile.objects.get_or_create(user=u, defaults={'section': section_10a, 'roll_number': f'R{i:03d}'})

# Time Slots
days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
times = [('08:00', '08:45'), ('08:45', '09:30'), ('09:45', '10:30'), ('10:30', '11:15'), ('11:30', '12:15')]
for day in days:
    for start, end in times:
        TimeSlot.objects.get_or_create(day=day, start_time=start, end_time=end)

# Assessment Types
for name in ['Quiz', 'Assignment', 'Class Test', 'Mid Term', 'Final Term']:
    AssessmentType.objects.get_or_create(name=name)

print("\n=== Seed Complete ===")
print(f"Users: {User.objects.count()}")
print(f"Sections: {Section.objects.count()}")
print(f"Subjects: {Subject.objects.count()}")
print(f"Time Slots: {TimeSlot.objects.count()}")
print(f"Student Profiles: {StudentProfile.objects.count()}")
print("\nLogin credentials:")
print("  Admin:   admin / adminpass")
print("  Teacher: teacher1 / teacherpass")
print("  Student: student1 / studentpass")
