from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from accounts.decorators import role_required
from django.contrib import messages
from django.utils import timezone

from accounts.models import User
from academics.models import Section
from students.models import StudentProfile
from attendance.models import Attendance



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
            # Pre-fetch all attendance for the date in one query (avoids N+1)
            existing_attendance = {
                a.user_id: a.status
                for a in Attendance.objects.filter(
                    user__in=[p.user for p in profiles],
                    date=selected_date
                )
            }
            for p in profiles:
                students_list.append({
                    'user': p.user,
                    'roll': p.roll_number,
                    'existing_status': existing_attendance.get(p.user_id, ''),
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
                    user=p.user, date=date_str,
                    defaults={'section': selected_section, 'status': status, 'marked_by': request.user}
                )
            messages.success(request, f"Attendance saved for {selected_section} on {date_str}.")
        url = reverse('mark_attendance') + f'?section={section_id}&date={date_str}'
        return redirect(url)

    context = {
        'sections': sections,
        'selected_section': selected_section,
        'students_list': students_list,
        'selected_date': selected_date,
    }
    return render(request, 'dashboard/mark_attendance.html', context)

@login_required
def student_attendance_report(request, student_id=None):
    if student_id:
        if request.user.role not in [User.Role.ADMIN, User.Role.TEACHER]:
            messages.error(request, "Access denied.")
            return redirect('dashboard_router')
        student = get_object_or_404(User, id=student_id, role=User.Role.STUDENT)
    else:
        if request.user.role not in [User.Role.STUDENT, User.Role.TEACHER, User.Role.COORDINATOR]:
            return redirect('dashboard_router')
        student = request.user

    selected_month = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    days_data = []
    present_count = 0
    absent_count = 0
    late_count = 0
    total_days = 0

    try:
        year_str, month_str = selected_month.split('-')
        year, month = int(year_str), int(month_str)
        import calendar
        import datetime
        num_days = calendar.monthrange(year, month)[1]

        records = Attendance.objects.filter(user=student, date__year=year, date__month=month)
        record_dict = {r.date.day: r for r in records}

        na_count = 0
        for day in range(1, num_days + 1):
            date_obj = datetime.date(year, month, day)
            rec = record_dict.get(day)
            
            if rec:
                if rec.status == Attendance.Status.PRESENT: present_count += 1
                elif rec.status == Attendance.Status.ABSENT: absent_count += 1
                elif rec.status == Attendance.Status.LATE: late_count += 1
                elif rec.status == Attendance.Status.NOT_APPLICABLE: na_count += 1

            days_data.append({
                'day': day,
                'date': date_obj,
                'status': rec.status if rec else None,
                'display': rec.get_status_display() if rec else 'Not Marked'
            })
        total_days = num_days - na_count
    except ValueError:
        messages.error(request, "Invalid month format.")

    context = {
        'student': student,
        'selected_month': selected_month,
        'days_data': days_data,
        'present_count': present_count,
        'absent_count': absent_count,
        'late_count': late_count,
        'total_days': total_days,
    }
    return render(request, 'dashboard/student_attendance_report.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def attendance_report(request):
    sections = Section.objects.all()
    selected_section = None
    report_data = []
    
    # Default to current month (YYYY-MM)
    selected_month = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    selected_student_id = request.GET.get('student', '')
    all_profiles = StudentProfile.objects.select_related('user', 'section').all()
    
    if request.method == 'GET' and request.GET.get('section'):
        section_id = request.GET.get('section')
        selected_section = Section.objects.filter(id=section_id).first()
        
        if selected_section and selected_month:
            try:
                year_str, month_str = selected_month.split('-')
                year, month = int(year_str), int(month_str)
                
                profiles = StudentProfile.objects.filter(section=selected_section).select_related('user')
                
                if selected_student_id:
                    profiles = profiles.filter(user_id=selected_student_id)
                
                # Fetch all attendance for this section's students in the selected month
                attendances = Attendance.objects.filter(
                    user__in=[p.user for p in profiles],
                    date__year=year,
                    date__month=month
                )
                
                # Group by student
                att_dict = {}
                for p in profiles:
                    att_dict[p.user.id] = {'present': 0, 'absent': 0, 'late': 0, 'na': 0, 'total': 0}
                    
                for att in attendances:
                    if att.user_id in att_dict:
                        if att.status in att_dict[att.user_id]:
                            att_dict[att.user_id][att.status] += 1
                        if att.status != Attendance.Status.NOT_APPLICABLE:
                            att_dict[att.user_id]['total'] += 1
                        
                for p in profiles:
                    stats = att_dict[p.user.id]
                    report_data.append({
                        'user': p.user,
                        'roll': p.roll_number,
                        'present': stats['present'],
                        'absent': stats['absent'],
                        'late': stats['late'],
                        'na': stats['na'],
                        'total': stats['total'],
                    })
            except ValueError:
                messages.error(request, "Invalid month format.")
                
    context = {
        'sections': sections,
        'selected_section': selected_section,
        'selected_month': selected_month,
        'report_data': report_data,
        'all_profiles': all_profiles,
        'selected_student_id': selected_student_id,
    }
    return render(request, 'dashboard/attendance_report.html', context)

@login_required
@role_required(User.Role.ADMIN)
def mark_teacher_attendance(request):
    teachers = User.objects.filter(role__in=[User.Role.TEACHER, User.Role.COORDINATOR]).order_by('first_name', 'last_name')
    selected_date = timezone.now().date().isoformat()
    teachers_list = []

    if request.method == 'GET':
        selected_date = request.GET.get('date', selected_date)
        existing_attendance = {
            a.user_id: a.status
            for a in Attendance.objects.filter(
                user__in=teachers,
                date=selected_date
            )
        }
        for t in teachers:
            teachers_list.append({
                'user': t,
                'existing_status': existing_attendance.get(t.id, ''),
            })

    if request.method == 'POST':
        date_str = request.POST.get('date')
        for t in teachers:
            status = request.POST.get(f'status_{t.id}', 'present')
            Attendance.objects.update_or_create(
                user=t, date=date_str,
                defaults={'status': status, 'marked_by': request.user, 'section': None}
            )
        messages.success(request, f"Teacher attendance saved for {date_str}.")
        url = reverse('mark_teacher_attendance') + f'?date={date_str}'
        return redirect(url)

    context = {
        'teachers_list': teachers_list,
        'selected_date': selected_date,
    }
    return render(request, 'dashboard/mark_teacher_attendance.html', context)

@login_required
@role_required(User.Role.ADMIN)
def teacher_attendance_report(request):
    report_data = []
    selected_month = request.GET.get('month', timezone.now().strftime('%Y-%m'))
    teachers = User.objects.filter(role__in=[User.Role.TEACHER, User.Role.COORDINATOR]).order_by('first_name')
    selected_teacher_id = request.GET.get('teacher', '')
    
    if selected_month:
        try:
            year_str, month_str = selected_month.split('-')
            year, month = int(year_str), int(month_str)
            
            if selected_teacher_id:
                teachers = teachers.filter(id=selected_teacher_id)
            
            attendances = Attendance.objects.filter(
                user__in=teachers,
                date__year=year,
                date__month=month
            )
            
            att_dict = {}
            for t in teachers:
                att_dict[t.id] = {'present': 0, 'absent': 0, 'late': 0, 'na': 0, 'total': 0}
                
            for att in attendances:
                if att.user_id in att_dict:
                    if att.status in att_dict[att.user_id]:
                        att_dict[att.user_id][att.status] += 1
                    if att.status != Attendance.Status.NOT_APPLICABLE:
                        att_dict[att.user_id]['total'] += 1
                    
            for t in teachers:
                stats = att_dict[t.id]
                report_data.append({
                    'user': t,
                    'present': stats['present'],
                    'absent': stats['absent'],
                    'late': stats['late'],
                    'na': stats['na'],
                    'total': stats['total'],
                })
        except ValueError:
            messages.error(request, "Invalid month format.")
            
    context = {
        'selected_month': selected_month,
        'report_data': report_data,
        'all_teachers': User.objects.filter(role__in=[User.Role.TEACHER, User.Role.COORDINATOR]),
        'selected_teacher_id': selected_teacher_id,
    }
    return render(request, 'dashboard/teacher_attendance_report.html', context)