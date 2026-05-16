from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from accounts.decorators import role_required
from django.utils import timezone
from django.db.models import Sum
from decimal import Decimal
from accounts.models import User
from academics.models import Section, Subject
from students.models import StudentProfile, ParentProfile
from timetable.models import TimetableEntry
from attendance.models import Attendance
from exams.models import AssessmentRecord, GradeSetting, AcademicPeriodConfig
from finance.models import Invoice, Payment
from procurement.models import Expense, PurchaseRequest, InventoryItem, CapexItem
from exams.services import calculate_student_grade, get_letter_grade
from .models import Notice

# ─── Home & Router ───────────────────────────────────────────────────────────

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_router')
    return redirect('login')

@login_required
def dashboard_router(request):
    if request.user.role == User.Role.ADMIN:
        return redirect('admin_dashboard')
    elif request.user.role in (User.Role.TEACHER, User.Role.COORDINATOR):
        return redirect('teacher_dashboard')
    elif request.user.role == User.Role.STUDENT:
        return redirect('student_dashboard')
    elif request.user.role == User.Role.PARENT:
        return redirect('parent_dashboard')
    return redirect('home')

# ─── ADMIN Dashboard ─────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def admin_dashboard(request):
    today = timezone.now().date()
    now = timezone.now()
    total_students = User.objects.filter(role=User.Role.STUDENT).count()
    total_teachers = User.objects.filter(role=User.Role.TEACHER).count()
    total_sections = Section.objects.count()

    today_attendance = Attendance.objects.filter(date=today)
    present_today = today_attendance.filter(status=Attendance.Status.PRESENT).count()
    total_today = today_attendance.count()
    attendance_pct = round((present_today / total_today * 100), 1) if total_today > 0 else 0

    unpaid_invoices = Invoice.objects.filter(status=Invoice.Status.UNPAID).count()

    # Monthly finance data
    month_income = Payment.objects.filter(
        payment_date__year=now.year, payment_date__month=now.month
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    month_expenses = Expense.objects.filter(
        date__year=now.year, date__month=now.month
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    month_net = month_income - month_expenses

    # Procurement stats
    pending_pr_count = PurchaseRequest.objects.filter(status=PurchaseRequest.Status.PENDING).count()
    inventory_count = InventoryItem.objects.count()
    capex_count = CapexItem.objects.count()

    # Leave Management stats
    from leaves.models import LeaveApplication, LeaveType
    from leaves.views import get_current_academic_year, get_leave_balance
    
    pending_leaves = LeaveApplication.objects.filter(status=LeaveApplication.Status.COORDINATOR_APPROVED).count()
    staff_on_leave_today = LeaveApplication.objects.filter(
        status=LeaveApplication.Status.ADMIN_APPROVED,
        start_date__lte=today,
        end_date__gte=today
    ).count()

    leave_types = LeaveType.objects.all()
    current_academic_year = get_current_academic_year()
    staff = User.objects.filter(role__in=[User.Role.TEACHER, User.Role.COORDINATOR])
    staff_balances = []
    for user in staff:
        user_balances = []
        for lt in leave_types:
            allocated, used = get_leave_balance(user, lt, current_academic_year)
            user_balances.append({
                'type': lt,
                'allocated': allocated,
                'used': used,
                'remaining': allocated - used,
            })
        staff_balances.append({
            'user': user,
            'balances': user_balances,
        })

    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_sections': total_sections,
        'attendance_pct': attendance_pct,
        'unpaid_invoices': unpaid_invoices,
        'current_year': now.year,
        'current_academic_year': current_academic_year,
        'month_income': month_income,
        'month_expenses': month_expenses,
        'month_net': month_net,
        'pending_pr_count': pending_pr_count,
        'inventory_count': inventory_count,
        'capex_count': capex_count,
        'pending_leaves': pending_leaves,
        'staff_on_leave_today': staff_on_leave_today,
        'staff_balances': staff_balances,
        'leave_types': leave_types,
        'notices': Notice.objects.filter(is_active=True).order_by('-created_at')[:5],
    }
    return render(request, 'dashboard/admin_dashboard.html', context)

# ─── TEACHER Dashboard ───────────────────────────────────────────────────────

@login_required
@role_required(User.Role.TEACHER, User.Role.COORDINATOR)
def teacher_dashboard(request):
    from leaves.views import get_current_academic_year, get_leave_balance
    from leaves.models import LeaveType

    my_entries = TimetableEntry.objects.filter(teacher=request.user).select_related('section', 'subject', 'time_slot')
    my_sections = Section.objects.filter(timetable_entries__teacher=request.user).distinct()
    pending_assessments = AssessmentRecord.objects.filter(
        section__in=my_sections
    ).order_by('-date_conducted')[:5]

    current_academic_year = get_current_academic_year()
    leave_types = LeaveType.objects.all()
    my_balances = []
    for lt in leave_types:
        allocated, used = get_leave_balance(request.user, lt, current_academic_year)
        my_balances.append({
            'type': lt,
            'allocated': allocated,
            'used': used,
            'remaining': allocated - used,
        })

    from django.utils import timezone
    today = timezone.now().date()
    _, early_used = get_early_leave_balance(request.user, today.year, today.month)

    context = {
        'my_entries': my_entries,
        'my_sections': my_sections,
        'pending_assessments': pending_assessments,
        'section_count': my_sections.count(),
        'notices': Notice.objects.filter(is_active=True, target_role__in=['all', 'teacher']).order_by('-created_at')[:5],
        'my_balances': my_balances,
        'early_used': early_used,
        'early_limit': 3,
        'current_academic_year': current_academic_year,
    }
    return render(request, 'dashboard/teacher_dashboard.html', context)

# ─── STUDENT Dashboard ───────────────────────────────────────────────────────

@login_required
@role_required(User.Role.STUDENT)
def student_dashboard(request):
    profile = StudentProfile.objects.filter(user=request.user).first()
    section = profile.section if profile else None

    # Calculate attendance
    total_att = Attendance.objects.filter(student=request.user).count()
    present_att = Attendance.objects.filter(student=request.user, status=Attendance.Status.PRESENT).count()
    att_pct = round((present_att / total_att * 100), 1) if total_att > 0 else 0

    # Calculate grades per subject
    grades = []
    if section:
        subjects = Subject.objects.filter(assessmentrecord__section=section).distinct()
        for subj in subjects:
            score = calculate_student_grade(request.user, subj, section)
            grades.append({'subject': subj, 'score': score})

    # Timetable for the student's section
    timetable = []
    if section:
        timetable = TimetableEntry.objects.filter(section=section).select_related('subject', 'teacher', 'time_slot').order_by('time_slot__day', 'time_slot__start_time')

    # Invoices
    invoices = Invoice.objects.filter(student=request.user).prefetch_related('line_items').order_by('-issued_date')[:5]

    # Published periods for this student's academic year
    published_periods = []
    if section:
        config = AcademicPeriodConfig.objects.filter(academic_year=section.academic_year).first()
        if config:
            published_periods = config.periods.filter(is_published=True)

    context = {
        'profile': profile,
        'section': section,
        'att_pct': att_pct,
        'grades': grades,
        'timetable': timetable,
        'invoices': invoices,
        'published_periods': published_periods,
        'notices': Notice.objects.filter(is_active=True, target_role__in=['all', 'student_parent']).order_by('-created_at')[:5],
    }
    return render(request, 'dashboard/student_dashboard.html', context)

# ─── PARENT Dashboard ────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.PARENT)
def parent_dashboard(request):
    parent_profile = ParentProfile.objects.filter(user=request.user).first()
    children_data = []

    if parent_profile:
        for child in parent_profile.children.all():
            profile = StudentProfile.objects.filter(user=child).first()
            section = profile.section if profile else None

            # Attendance
            total_att = Attendance.objects.filter(student=child).count()
            present_att = Attendance.objects.filter(student=child, status=Attendance.Status.PRESENT).count()
            att_pct = round((present_att / total_att * 100), 1) if total_att > 0 else 0

            # Grades
            grades = []
            if section:
                grade_settings = GradeSetting.objects.all()
                subjects = Subject.objects.filter(assessmentrecord__section=section).distinct()
                for subj in subjects:
                    score = calculate_student_grade(child, subj, section)
                    letter = get_letter_grade(score, grade_settings)
                    grades.append({'subject': subj, 'score': score, 'letter': letter['letter']})

            # Fee status
            invoices = Invoice.objects.filter(student=child).prefetch_related('line_items').order_by('-issued_date')[:5]

            # Published periods
            published_periods = []
            if section:
                config = AcademicPeriodConfig.objects.filter(academic_year=section.academic_year).first()
                if config:
                    published_periods = config.periods.filter(is_published=True)

            children_data.append({
                'child': child,
                'profile': profile,
                'section': section,
                'att_pct': att_pct,
                'grades': grades,
                'invoices': invoices,
                'published_periods': published_periods,
            })

    context = {
        'parent_profile': parent_profile,
        'children_data': children_data,
        'notices': Notice.objects.filter(is_active=True, target_role__in=['all', 'student_parent']).order_by('-created_at')[:5],
    }
    return render(request, 'dashboard/parent_dashboard.html', context)


@login_required
@role_required(User.Role.ADMIN)
def manage_notices(request):
    """Admin view to create and delete school notices."""
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            Notice.objects.create(
                title=request.POST.get('title'),
                content=request.POST.get('content'),
                target_role=request.POST.get('target_role'),
                created_by=request.user
            )
            messages.success(request, "Notice posted successfully!")
        return redirect('manage_notices')

    notices = Notice.objects.all().order_by('-created_at')
    return render(request, 'dashboard/manage_notices.html', {'notices': notices})


@login_required
@role_required(User.Role.ADMIN)
@require_POST
def delete_notice(request, notice_id):
    """Delete a notice (POST only)."""
    Notice.objects.filter(id=notice_id).delete()
    messages.success(request, "Notice deleted.")
    return redirect('manage_notices')


# ─── ACADEMIC YEARS ────────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def manage_academic_years(request):
    """Admin: Create and manage Academic Years."""
    from academics.models import AcademicYear
    from django.utils.dateparse import parse_date

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'save':
            name = request.POST.get('name', '').strip()
            start_date_str = request.POST.get('start_date')
            end_date_str = request.POST.get('end_date')
            is_active = request.POST.get('is_active') == 'on'

            try:
                start_date = parse_date(start_date_str)
                end_date = parse_date(end_date_str)
                
                # Check for existing
                ay_id = request.POST.get('ay_id')
                if ay_id:
                    ay = AcademicYear.objects.get(id=ay_id)
                    ay.name = name
                    ay.start_date = start_date
                    ay.end_date = end_date
                    if is_active:
                        ay.is_active = True
                    else:
                        ay.is_active = False
                    ay.save()
                    messages.success(request, f"Academic Year '{name}' updated.")
                else:
                    AcademicYear.objects.create(
                        name=name,
                        start_date=start_date,
                        end_date=end_date,
                        is_active=is_active
                    )
                    messages.success(request, f"Academic Year '{name}' created.")
            except Exception as e:
                messages.error(request, f"Error saving Academic Year: {e}")

        elif action == 'delete':
            ay_id = request.POST.get('ay_id')
            try:
                AcademicYear.objects.get(id=ay_id).delete()
                messages.success(request, "Academic Year deleted.")
            except Exception as e:
                messages.error(request, f"Cannot delete: {e}")

        return redirect('manage_academic_years')

    years = AcademicYear.objects.all()
    context = {'years': years}
    return render(request, 'dashboard/academic_years.html', context)