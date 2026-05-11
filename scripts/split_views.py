import ast
import os

source_file = 'dashboard/views.py'
with open(source_file, 'r', encoding='utf-8') as f:
    source_code = f.read()

mega_imports = """from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.utils import timezone
from decimal import Decimal
import datetime

from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from students.models import StudentProfile, ParentProfile
from timetable.models import TimeSlot, TimetableEntry
from timetable.services import generate_timetable_entry
from timetable.pdf_utils import generate_section_timetable_pdf, generate_teacher_timetable_pdf
from attendance.models import Attendance
from exams.models import AssessmentType, SubjectWeighting, WeightingComponent, AssessmentRecord, StudentScore, GradeSetting, SubjectComment
from finance.models import FeeStructure, Invoice, Payment

"""

routing_map = {
    'home_view': 'dashboard',
    'dashboard_router': 'dashboard',
    'admin_dashboard': 'dashboard',
    'teacher_dashboard': 'dashboard',
    'student_dashboard': 'dashboard',
    'parent_dashboard': 'dashboard',
    
    'student_profiles': 'students',
    'student_profile_detail': 'students',
    
    'timetable_gen': 'timetable',
    'view_timetable': 'timetable',
    'download_timetable_pdf': 'timetable',
    'download_teacher_timetable_pdf': 'timetable',
    'my_timetable': 'timetable',
    
    'report_settings': 'exams',
    'manage_assessments': 'exams',
    'enter_marks': 'exams',
    'view_reports': 'exams',
    'student_report': 'exams',
    'grade_settings_view': 'exams',
    'subject_comments_view': 'exams',
    '_calculate_student_grade': 'exams',
    '_get_grade_details': 'exams',
    '_get_letter_grade': 'exams',
    
    'mark_attendance': 'attendance',
    'my_attendance': 'attendance',
    
    'manage_finance': 'finance',
    
    'manage_classes': 'academics',
}

module = ast.parse(source_code)
lines = source_code.split('\n')

app_buffers = {app: mega_imports for app in set(routing_map.values())}

for node in module.body:
    if isinstance(node, ast.FunctionDef):
        func_name = node.name
        if func_name in routing_map:
            # get decorators too
            start_lineno = node.decorator_list[0].lineno if node.decorator_list else node.lineno
            end_lineno = node.end_lineno
            
            # handle comments before decorators if needed, but ast.get_source_segment is better
            func_text = '\n'.join(lines[start_lineno-1:end_lineno])
            app_buffers[routing_map[func_name]] += "\n\n" + func_text

for app, text in app_buffers.items():
    with open(f'{app}/views.py', 'w', encoding='utf-8') as f:
        f.write(text)

print("Decentralization script completed using AST.")
