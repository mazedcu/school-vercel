"""
Data for the admin dashboard: what needs attention today, today's snapshot,
recent trends and money. Kept separate from the view so it can be tested.
"""
import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from academics.models import Section, Subject
from attendance.models import Attendance
from finance.models import Invoice, Payment
from leaves.models import LeaveApplication
from lessonplan.models import LessonPlan
from procurement.models import Expense, PurchaseRequest
from students.models import StudentProfile
from timetable.models import TimeSlot, TimetableEntry

PRESENT = [Attendance.Status.PRESENT, Attendance.Status.LATE]
STAFF_ROLES = [User.Role.TEACHER, User.Role.COORDINATOR]
OPEN_INVOICE = [Invoice.Status.UNPAID, Invoice.Status.PARTIAL]
BALANCE = ExpressionWrapper(F('amount_due') - F('amount_paid'), output_field=DecimalField())


def school_now():
    """Current time on the school's clock (settings.SCHOOL_TIME_ZONE, default Asia/Dhaka)."""
    tz = ZoneInfo(getattr(settings, 'SCHOOL_TIME_ZONE', 'Asia/Dhaka'))
    return timezone.now().astimezone(tz)


def _pct(part, whole):
    return round(part * 100 / whole) if whole else None


def _names(sections, limit=3):
    names = [f"{s.class_group.name} – {s.name}" for s in sections[:limit]]
    extra = len(sections) - limit
    return ", ".join(names) + (f" and {extra} more" if extra > 0 else "")


def _taka(amount):
    return f"Tk {amount:,.0f}"


def _plural(n, one, many=None):
    return one if n == 1 else (many or one + "s")


def todays_classes(now):
    """Periods and classes scheduled today, and which period is on now or next."""
    day = now.strftime('%A').lower()
    slots = list(TimeSlot.objects.filter(day=day).order_by('start_time'))
    counts = dict(
        TimetableEntry.objects.filter(time_slot__day=day)
        .values_list('time_slot').annotate(n=Count('id'))
    )
    t = now.time()
    current = next((s for s in slots if s.start_time <= t < s.end_time), None)
    upcoming = next((s for s in slots if s.start_time > t), None)
    return {
        'is_school_day': bool(slots),
        'periods': len(slots),
        'classes': sum(counts.values()),
        'sections': TimetableEntry.objects.filter(time_slot__day=day)
                                          .values('section').distinct().count(),
        'current': current,
        'current_classes': counts.get(current.id, 0) if current else 0,
        'next': upcoming,
        'finished': bool(slots) and not current and not upcoming,
    }


def student_attendance(today):
    students = User.objects.filter(role=User.Role.STUDENT, is_active=True, is_deleted=False)
    records = Attendance.objects.filter(date=today, user__in=students) \
                                .exclude(status=Attendance.Status.NOT_APPLICABLE)
    counts = dict(records.values_list('status').annotate(n=Count('id')))
    present = counts.get(Attendance.Status.PRESENT, 0)
    late = counts.get(Attendance.Status.LATE, 0)
    absent = counts.get(Attendance.Status.ABSENT, 0)
    marked = present + late + absent

    # Sections with active students but no attendance taken today
    with_students = Section.objects.filter(
        students__user__in=students
    ).distinct().select_related('class_group').order_by('class_group__name', 'name')
    marked_sections = set(Attendance.objects.filter(date=today).values_list('section_id', flat=True))
    unmarked = [s for s in with_students if s.id not in marked_sections]

    absentees = list(
        Attendance.objects.filter(date=today, status=Attendance.Status.ABSENT, user__in=students)
        .select_related('user', 'section__class_group')
        .order_by('section__class_group__name', 'section__name', 'user__first_name')[:8]
    )
    return {
        'total': students.count(),
        'present': present, 'late': late, 'absent': absent, 'marked': marked,
        'pct': _pct(present + late, marked),
        'sections_total': len(with_students),
        'sections_unmarked': unmarked,
        'absentees': absentees,
    }


def staff_attendance(today):
    staff = User.objects.filter(role__in=STAFF_ROLES, is_active=True, is_deleted=False)
    records = dict(
        Attendance.objects.filter(date=today, user__in=staff)
        .exclude(status=Attendance.Status.NOT_APPLICABLE)
        .values_list('user_id', 'status')
    )
    on_leave = set(
        LeaveApplication.objects.filter(
            status=LeaveApplication.Status.ADMIN_APPROVED, applicant__in=staff, start_date__lte=today,
        ).filter(Q(end_date__gte=today) | Q(end_date__isnull=True, start_date=today))
        .values_list('applicant_id', flat=True)
    )
    present = sum(1 for s in records.values() if s in PRESENT)
    absent_ids = {u for u, s in records.items() if s == Attendance.Status.ABSENT}
    total = staff.count()
    return {
        'total': total,
        'present': present,
        'on_leave': len(on_leave),
        'absent_without_leave': len(absent_ids - on_leave),
        'not_marked': max(total - len(records) - len(on_leave - set(records)), 0),
    }


def attendance_trend(today, days=14):
    """Student attendance % for the last `days` days that have records."""
    rows = (
        Attendance.objects.filter(
            user__role=User.Role.STUDENT, date__lte=today, date__gt=today - datetime.timedelta(days=45),
        ).exclude(status=Attendance.Status.NOT_APPLICABLE)
        .values('date').annotate(total=Count('id'), present=Count('id', filter=Q(status__in=PRESENT)))
        .order_by('-date')[:days]
    )
    rows = list(reversed(rows))
    labels = [r['date'].strftime('%a %d %b') for r in rows]
    values = [_pct(r['present'], r['total']) for r in rows]
    return {
        'labels': labels,
        'values': values,
        'rows': list(zip(labels, values)),
        'average': _pct(sum(r['present'] for r in rows), sum(r['total'] for r in rows)),
    }


def money(today):
    month = Q(payment_date__year=today.year, payment_date__month=today.month)
    collected = Payment.objects.filter(month).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    spent = Expense.objects.filter(date__year=today.year, date__month=today.month) \
                           .aggregate(t=Sum('amount'))['t'] or Decimal('0')
    due_this_month = Invoice.objects.filter(due_date__year=today.year, due_date__month=today.month) \
                                    .aggregate(due=Sum('amount_due'), paid=Sum('amount_paid'))
    open_invoices = Invoice.objects.filter(status__in=OPEN_INVOICE)
    outstanding = open_invoices.aggregate(t=Sum(BALANCE))['t'] or Decimal('0')
    return {
        'collected': collected,
        'spent': spent,
        'net': collected - spent,
        'month_fees_due': due_this_month['due'] or Decimal('0'),
        'month_fees_paid': due_this_month['paid'] or Decimal('0'),
        'month_collection_pct': _pct(due_this_month['paid'] or 0, due_this_month['due'] or 0),
        'outstanding': outstanding,
        'outstanding_students': open_invoices.values('student').distinct().count(),
    }


def attention_items(today, classes, students, staff):
    """Things the principal should act on, most time-sensitive first. Only non-empty items."""
    items = []

    if classes['is_school_day'] and students['sections_unmarked']:
        n = len(students['sections_unmarked'])
        items.append({
            'level': 'warn',
            'title': f"{n} {_plural(n, 'section hasn’t', 'sections haven’t')} taken attendance today",
            'detail': _names(students['sections_unmarked']),
            'action': "Take attendance", 'url': reverse('mark_attendance'),
        })

    if staff['absent_without_leave']:
        n = staff['absent_without_leave']
        items.append({
            'level': 'warn',
            'title': f"{n} staff {_plural(n, 'member is', 'members are')} absent without approved leave",
            'detail': "Marked absent today with no approved leave on record.",
            'action': "View staff attendance", 'url': reverse('teacher_attendance_report'),
        })

    n = LeaveApplication.objects.filter(status=LeaveApplication.Status.COORDINATOR_APPROVED).count()
    if n:
        items.append({
            'level': 'act',
            'title': f"{n} leave {_plural(n, 'request is', 'requests are')} waiting for your approval",
            'detail': "Already approved by a coordinator.",
            'action': "Review leave", 'url': reverse('admin_leave_review'),
        })

    overdue = Invoice.objects.filter(status__in=OPEN_INVOICE, due_date__lt=today)
    n = overdue.count()
    if n:
        balance = overdue.aggregate(t=Sum(BALANCE))['t'] or Decimal('0')
        students_n = overdue.values('student').distinct().count()
        items.append({
            'level': 'alert',
            'title': f"{_taka(balance)} in fees is overdue",
            'detail': f"{n} {_plural(n, 'invoice')} past the due date, from {students_n} "
                      f"{_plural(students_n, 'student')}.",
            'action': "Open finance", 'url': reverse('manage_finance'),
        })

    n = LessonPlan.objects.filter(status=LessonPlan.Status.SUBMITTED).count()
    if n:
        items.append({
            'level': 'act',
            'title': f"{n} lesson {_plural(n, 'plan is', 'plans are')} waiting for review",
            'detail': "Submitted by teachers and not yet approved or returned.",
            'action': "Review lesson plans", 'url': reverse('lesson_plan_list'),
        })

    pending = PurchaseRequest.objects.filter(status=PurchaseRequest.Status.PENDING)
    n = pending.count()
    if n:
        cost = pending.aggregate(t=Sum('estimated_cost'))['t'] or Decimal('0')
        items.append({
            'level': 'act',
            'title': f"{n} purchase {_plural(n, 'request needs', 'requests need')} a decision",
            'detail': f"Estimated {_taka(cost)} in total.",
            'action': "Review purchases", 'url': reverse('purchase_requests'),
        })
    return items


def admin_overview():
    now = school_now()
    today = now.date()
    classes = todays_classes(now)
    students = student_attendance(today)
    staff = staff_attendance(today)

    hour = now.hour
    greeting = 'Good morning' if hour < 12 else 'Good afternoon' if hour < 17 else 'Good evening'
    return {
        'now': now,
        'today': today,
        'greeting': greeting,
        'classes': classes,
        'students': students,
        'staff': staff,
        'attention': attention_items(today, classes, students, staff),
        'trend': attendance_trend(today),
        'money': money(today),
        'counts': {
            'students': students['total'],
            'staff': staff['total'],
            'sections': Section.objects.count(),
            'subjects': Subject.objects.count(),
            'unassigned_students': StudentProfile.objects.filter(
                section__isnull=True, user__is_active=True, user__role=User.Role.STUDENT).count(),
        },
    }
