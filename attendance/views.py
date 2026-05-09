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
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def mark_attendance(request):

    sections = Section.objects.all()
    selected_section = None
    students_list = []
    selected_date = timezone.now().date().isoformat()

    if request.method == 'GET' and request.GET.get('section'):
        section_id = request.GET.get('section')
        selected_date = request.GET.get('date', selected_date)
        selected_section = Section.objects.filter(id=section_id).first()
        if selected_section:
            profiles = StudentProfile.objects.filter(section=selected_section).select_related('user')
            for p in profiles:
                existing = Attendance.objects.filter(student=p.user, date=selected_date).first()
                students_list.append({
                    'user': p.user,
                    'roll': p.roll_number,
                    'existing_status': existing.status if existing else '',
                })

    if request.method == 'POST':
        section_id = request.POST.get('section_id')
        date_str = request.POST.get('date')
        selected_section = Section.objects.filter(id=section_id).first()
        if selected_section:
            profiles = StudentProfile.objects.filter(section=selected_section).select_related('user')
            for p in profiles:
                status = request.POST.get(f'status_{p.user.id}', 'present')
                Attendance.objects.update_or_create(
                    student=p.user, date=date_str,
                    defaults={'section': selected_section, 'status': status, 'marked_by': request.user}
                )
            messages.success(request, f"Attendance saved for {selected_section} on {date_str}.")
        return redirect(f'/mark_attendance/?section={section_id}&date={date_str}')

    context = {
        'sections': sections,
        'selected_section': selected_section,
        'students_list': students_list,
        'selected_date': selected_date,
    }
    return render(request, 'dashboard/mark_attendance.html', context)

@login_required
@role_required(User.Role.STUDENT)
def my_attendance(request):

    records = Attendance.objects.filter(student=request.user).order_by('-date')[:30]
    total = Attendance.objects.filter(student=request.user).count()
    present = Attendance.objects.filter(student=request.user, status=Attendance.Status.PRESENT).count()
    att_pct = round((present / total * 100), 1) if total > 0 else 0

    context = {'records': records, 'att_pct': att_pct, 'total': total, 'present': present}
    return render(request, 'dashboard/my_attendance.html', context)