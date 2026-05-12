from django.shortcuts import render, redirect
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
                a.student_id: a.status
                for a in Attendance.objects.filter(
                    student__in=[p.user for p in profiles],
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
                    student=p.user, date=date_str,
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
@role_required(User.Role.STUDENT)
def my_attendance(request):

    records = Attendance.objects.filter(student=request.user).order_by('-date')[:30]
    total = Attendance.objects.filter(student=request.user).count()
    present = Attendance.objects.filter(student=request.user, status=Attendance.Status.PRESENT).count()
    att_pct = round((present / total * 100), 1) if total > 0 else 0

    context = {'records': records, 'att_pct': att_pct, 'total': total, 'present': present}
    return render(request, 'dashboard/my_attendance.html', context)