"""
Data for the student dashboard: today's classes, results, recent marks,
attendance and fees. Kept separate from the view so it can be tested.
"""
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum

from attendance.models import Attendance
from exams.models import StudentScore
from exams.services import period_config, year_report
from finance.models import Invoice
from students.models import StudentProfile
from timetable.models import TimetableEntry

from .overview import school_now

PRESENT = [Attendance.Status.PRESENT, Attendance.Status.LATE]
OPEN_INVOICE = [Invoice.Status.UNPAID, Invoice.Status.PARTIAL]
BALANCE = ExpressionWrapper(F('amount_due') - F('amount_paid'), output_field=DecimalField())


def _pct(part, whole):
    return round(part * 100 / whole) if whole else None


def todays_classes(section, now):
    """Today's periods for the section, each flagged as done, now or next."""
    day = now.strftime('%A').lower()
    entries = list(TimetableEntry.objects.filter(section=section, time_slot__day=day)
                   .select_related('subject', 'teacher', 'time_slot').order_by('time_slot__start_time'))
    t = now.time()
    next_found = False
    classes = []
    for e in entries:
        slot = e.time_slot
        if slot.end_time <= t:
            state = 'done'
        elif slot.start_time <= t < slot.end_time:
            state = 'now'
        elif not next_found:
            state, next_found = 'next', True
        else:
            state = 'later'
        if state == 'now':
            next_found = True
        classes.append({'entry': e, 'state': state})
    return classes


def attendance_summary(student, section, today):
    records = Attendance.objects.filter(user=student).exclude(status=Attendance.Status.NOT_APPLICABLE)
    if section:
        records = records.filter(section=section)
    counts = dict(records.values_list('status').annotate(n=Count('id')))
    present = counts.get(Attendance.Status.PRESENT, 0)
    late = counts.get(Attendance.Status.LATE, 0)
    absent = counts.get(Attendance.Status.ABSENT, 0)
    total = present + late + absent
    month = records.filter(date__year=today.year, date__month=today.month)
    return {
        'pct': _pct(present + late, total),
        'present': present, 'late': late, 'absent': absent, 'total': total,
        'absent_this_month': month.filter(status=Attendance.Status.ABSENT).count(),
        'today': records.filter(date=today).values_list('status', flat=True).first(),
    }


def fees_summary(student):
    base = Invoice.objects.filter(student=student).annotate(balance=BALANCE).prefetch_related('line_items')
    # Everything still to pay, oldest due first, then the two most recent paid invoices.
    invoices = list(base.filter(status__in=OPEN_INVOICE).order_by('due_date', 'id')) + \
        list(base.filter(status=Invoice.Status.PAID).order_by('-issued_date', '-id')[:2])
    open_q = Invoice.objects.filter(student=student, status__in=OPEN_INVOICE)
    outstanding = open_q.aggregate(t=Sum(BALANCE))['t'] or Decimal('0')
    next_due = open_q.order_by('due_date').first()
    return {'invoices': invoices, 'outstanding': outstanding, 'next_due': next_due}


def student_home(student):
    now = school_now()
    today = now.date()
    profile = StudentProfile.objects.filter(user=student).select_related('section__class_group').first()
    section = profile.section if profile else None
    report = year_report(student, viewer=student)

    recent = []
    if section:
        recent = list(
            StudentScore.objects.filter(student=student, assessment__section=section)
            .select_related('assessment__subject', 'assessment__assessment_type')
            .order_by('-assessment__date_conducted', '-id')[:6]
        )
        for s in recent:
            total = s.assessment.total_marks
            s.pct = None if s.not_applicable or not total else round(s.marks_obtained * 100 / total)

    periods = []
    if section:
        config = period_config(section)
        if config:
            periods = list(config.periods.filter(is_published=True).order_by('sequence'))

    hour = now.hour
    return {
        'now': now,
        'greeting': 'Good morning' if hour < 12 else 'Good afternoon' if hour < 17 else 'Good evening',
        'profile': profile,
        'section': section,
        'classes': todays_classes(section, now) if section else [],
        'report': report,
        'scored_subjects': [g for g in report['grades'] if g['score'] is not None],
        'recent': recent,
        'attendance': attendance_summary(student, section, today),
        'fees': fees_summary(student),
        'periods': periods,
    }
