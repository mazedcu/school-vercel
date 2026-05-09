from django.shortcuts import render, redirect, get_object_or_404
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



@login_required
@role_required(User.Role.ADMIN)
def manage_classes(request):

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_class':
            name = request.POST.get('class_name', '').strip()
            order = request.POST.get('display_order', '0')
            if name:
                ClassGroup.objects.get_or_create(name=name, defaults={'display_order': int(order)})
                messages.success(request, f"Class '{name}' created.")

        elif action == 'add_section':
            class_id = request.POST.get('class_group')
            sec_name = request.POST.get('section_name', '').strip()
            year = request.POST.get('academic_year', '2026')
            if class_id and sec_name:
                cg = ClassGroup.objects.get(id=class_id)
                Section.objects.get_or_create(name=sec_name, class_group=cg, academic_year=year)
                messages.success(request, f"Section '{sec_name}' added to {cg.name}.")

        elif action == 'add_subject':
            subj_name = request.POST.get('subject_name', '').strip()
            subj_code = request.POST.get('subject_code', '').strip()
            if subj_name and subj_code:
                Subject.objects.get_or_create(code=subj_code, defaults={'name': subj_name})
                messages.success(request, f"Subject '{subj_name}' ({subj_code}) created.")

        elif action == 'add_timeslot':
            day = request.POST.get('day')
            start = request.POST.get('start_time')
            end = request.POST.get('end_time')
            if day and start and end:
                TimeSlot.objects.get_or_create(day=day, start_time=start, end_time=end)
                messages.success(request, f"Time slot {day} {start}-{end} created.")

        return redirect('manage_classes')

    class_groups = ClassGroup.objects.prefetch_related('sections').all()
    subjects = Subject.objects.all()
    time_slots = TimeSlot.objects.all()

    context = {
        'class_groups': class_groups,
        'subjects': subjects,
        'time_slots': time_slots,
        'day_choices': TimeSlot.DAY_CHOICES,
    }
    return render(request, 'dashboard/manage_classes.html', context)