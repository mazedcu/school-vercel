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
from students.models import StudentProfile, ParentProfile, TeacherProfile
from timetable.models import TimeSlot, TimetableEntry
from timetable.services import generate_timetable_entry
from timetable.pdf_utils import generate_section_timetable_pdf, generate_teacher_timetable_pdf
from attendance.models import Attendance
from exams.models import AssessmentType, SubjectWeighting, WeightingComponent, AssessmentRecord, StudentScore, GradeSetting, SubjectComment
from finance.models import FeeStructure, Invoice, Payment
from exams.views import _calculate_student_grade, _get_letter_grade



@login_required
@role_required(User.Role.ADMIN)
def student_profiles(request):
    """Admin: list all students with their profile info."""

    section_filter = request.GET.get('section', '')
    sections = Section.objects.select_related('class_group').all()

    if section_filter:
        profiles = StudentProfile.objects.filter(section_id=section_filter).select_related('user', 'section__class_group')
    else:
        profiles = StudentProfile.objects.all().select_related('user', 'section__class_group')

    context = {
        'profiles': profiles,
        'sections': sections,
        'selected_section': section_filter,
    }
    return render(request, 'dashboard/student_profiles.html', context)

@login_required
def student_profile_detail(request, student_id):
    """View/Edit a student's profile. Admin can edit, student can only view their own."""
    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    profile = StudentProfile.objects.filter(user=student).first()
    is_admin = request.user.role == User.Role.ADMIN
    is_own = request.user == student

    if not is_admin and not is_own:
        return redirect('dashboard_router')

    if not profile:
        profile = StudentProfile.objects.create(user=student)

    sections = Section.objects.select_related('class_group').all()
    grade_settings = GradeSetting.objects.all()

    # Handle edit (admin only)
    if request.method == 'POST' and is_admin:
        profile.section_id = request.POST.get('section') or None
        profile.roll_number = request.POST.get('roll_number', '').strip()
        profile.address = request.POST.get('address', '').strip()
        profile.guardian_name = request.POST.get('guardian_name', '').strip()
        profile.guardian_phone = request.POST.get('guardian_phone', '').strip()
        dob = request.POST.get('date_of_birth', '').strip()
        profile.date_of_birth = dob if dob else None
        profile.biometric_id = request.POST.get('biometric_id', '').strip() or None

        # Update user fields
        student.first_name = request.POST.get('first_name', '').strip()
        student.last_name = request.POST.get('last_name', '').strip()
        student.email = request.POST.get('email', '').strip()
        student.phone = request.POST.get('phone', '').strip()
        student.save()
        profile.save()
        messages.success(request, f"Profile for {student.get_full_name() or student.username} updated.")
        return redirect('student_profile_detail', student_id=student.id)

    section = profile.section

    # Performance data
    total_att = Attendance.objects.filter(student=student).count()
    present_att = Attendance.objects.filter(student=student, status=Attendance.Status.PRESENT).count()
    att_pct = round((present_att / total_att * 100), 1) if total_att > 0 else 0

    grades = []
    overall_total = Decimal('0')
    subject_count = 0
    if section:
        subjects = Subject.objects.filter(assessmentrecord__section=section).distinct()
        for subj in subjects:
            score = _calculate_student_grade(student, subj, section)
            letter = _get_letter_grade(score, grade_settings)
            grades.append({'subject': subj, 'score': score, 'letter': letter['letter'], 'remark': letter['remark']})
            overall_total += score
            subject_count += 1
    overall_avg = round(overall_total / subject_count, 1) if subject_count > 0 else 0

    invoices = Invoice.objects.filter(student=student).order_by('-issued_date')[:5]

    # Parent info
    parent_profiles = ParentProfile.objects.filter(children=student)
    parent_users = [pp.user for pp in parent_profiles]

    context = {
        'student': student,
        'profile': profile,
        'section': section,
        'sections': sections,
        'is_admin': is_admin,
        'att_pct': att_pct,
        'att_total': total_att,
        'att_present': present_att,
        'grades': grades,
        'overall_avg': overall_avg,
        'invoices': invoices,
        'parent_users': parent_users,
    }
    return render(request, 'dashboard/student_profile_detail.html', context)


# ─── TEACHER PROFILES ────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def teacher_profiles(request):
    """Admin: list all teachers with their profile info."""
    teachers = User.objects.filter(role=User.Role.TEACHER).order_by('first_name', 'last_name')

    teacher_data = []
    for teacher in teachers:
        profile, _ = TeacherProfile.objects.get_or_create(user=teacher)
        # Count assigned sections and timetable entries
        section_count = Section.objects.filter(timetable_entries__teacher=teacher).distinct().count()
        entry_count = TimetableEntry.objects.filter(teacher=teacher).count()
        teacher_data.append({
            'teacher': teacher,
            'profile': profile,
            'section_count': section_count,
            'entry_count': entry_count,
        })

    context = {
        'teacher_data': teacher_data,
        'total_teachers': teachers.count(),
    }
    return render(request, 'dashboard/teacher_profiles.html', context)


@login_required
def teacher_profile_detail(request, teacher_id):
    """View/Edit a teacher's profile. Admin can edit, teacher can view their own."""
    teacher = get_object_or_404(User, pk=teacher_id, role=User.Role.TEACHER)
    is_admin = request.user.role == User.Role.ADMIN
    is_own = request.user == teacher

    if not is_admin and not is_own:
        return redirect('dashboard_router')

    profile, _ = TeacherProfile.objects.get_or_create(user=teacher)

    # Handle edit (admin or own)
    if request.method == 'POST':
        if not is_admin and not is_own:
            messages.error(request, "You don't have permission to edit this profile.")
            return redirect('teacher_profile_detail', teacher_id=teacher.id)

        profile.employee_id = request.POST.get('employee_id', '').strip()
        profile.qualification = request.POST.get('qualification', '').strip()
        profile.specialization = request.POST.get('specialization', '').strip()
        profile.address = request.POST.get('address', '').strip()
        exp = request.POST.get('experience_years', '0').strip()
        profile.experience_years = int(exp) if exp.isdigit() else 0
        dob = request.POST.get('date_of_birth', '').strip()
        profile.date_of_birth = dob if dob else None
        doj = request.POST.get('date_of_joining', '').strip()
        profile.date_of_joining = doj if doj else None
        profile.biometric_id = request.POST.get('biometric_id', '').strip() or None

        # Update user fields
        teacher.first_name = request.POST.get('first_name', '').strip()
        teacher.last_name = request.POST.get('last_name', '').strip()
        teacher.email = request.POST.get('email', '').strip()
        teacher.phone = request.POST.get('phone', '').strip()
        teacher.save()
        profile.save()
        messages.success(request, f"Profile for {teacher.get_full_name() or teacher.username} updated.")
        return redirect('teacher_profile_detail', teacher_id=teacher.id)

    # Teaching assignments
    timetable_entries = TimetableEntry.objects.filter(
        teacher=teacher
    ).select_related('section__class_group', 'subject', 'time_slot').order_by('time_slot__day', 'time_slot__start_time')

    my_sections = Section.objects.filter(timetable_entries__teacher=teacher).distinct().select_related('class_group')
    my_subjects = Subject.objects.filter(timetableentry__teacher=teacher).distinct()

    context = {
        'teacher': teacher,
        'profile': profile,
        'is_admin': is_admin,
        'is_own': is_own,
        'can_edit': is_admin or is_own,
        'timetable_entries': timetable_entries,
        'my_sections': my_sections,
        'my_subjects': my_subjects,
    }
    return render(request, 'dashboard/teacher_profile_detail.html', context)