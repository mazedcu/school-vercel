import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.http import require_POST
from accounts.decorators import role_required
from django.contrib import messages
from django.db.models import Count, Q, Avg, Exists, OuterRef
from django.utils import timezone
from decimal import Decimal
import datetime

from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from students.models import StudentProfile, ParentProfile
from timetable.models import TimetableEntry
from timetable.pdf_utils import generate_section_timetable_pdf
from exams.models import (
    AssessmentType, AssessmentRecord, StudentScore, GradeSetting,
    SubjectComment, SubjectWeighting, WeightingComponent,
    AcademicPeriodConfig, ReportPeriod, PeriodWeighting
)
from exams.services import (
    calculate_student_grade, get_grade_details,
    get_letter_grade, calculate_period_grade,
    build_report_cards, period_config, report_card, section_profiles,
)
from exams.models import ReportRemark

logger = logging.getLogger(__name__)


def _teaches(user, section_id, subject_id):
    """True if the user teaches this subject in this section (per the timetable)."""
    return TimetableEntry.objects.filter(
        teacher=user, section_id=section_id, subject_id=subject_id
    ).exists()


def _can_manage_assessment(user, assessment):
    """Admins manage every assessment; teachers only those for classes they teach."""
    if user.role == User.Role.ADMIN:
        return True
    return _teaches(user, assessment.section_id, assessment.subject_id)


def _assessments_for(user):
    """AssessmentRecords the user may manage."""
    qs = AssessmentRecord.objects.all()
    if user.role == User.Role.ADMIN:
        return qs
    return qs.filter(Exists(TimetableEntry.objects.filter(
        teacher=user, section=OuterRef('section'), subject=OuterRef('subject'),
    )))


NOT_YOUR_CLASS = "You can only manage assessments for subjects you teach in that section."



@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def report_settings(request):

    if request.method == 'POST':
        section_id = request.POST.get('section')
        subject_id = request.POST.get('subject')
        try:
            section = Section.objects.get(id=section_id)
            subject = Subject.objects.get(id=subject_id)
        except (Section.DoesNotExist, Subject.DoesNotExist):
            messages.error(request, "Invalid section or subject.")
            return redirect('report_settings')

        profile, created = SubjectWeighting.objects.get_or_create(
            section=section, subject=subject, academic_year=section.academic_year,
            defaults={'teacher': request.user}
        )
        # Clear old components
        profile.components.all().delete()

        total_weight = Decimal('0')
        assessment_types = AssessmentType.objects.all()
        for at in assessment_types:
            w = request.POST.get(f'weight_{at.id}', '0')
            try:
                w = Decimal(w)
            except Exception:
                w = Decimal('0')
            if w > 0:
                WeightingComponent.objects.create(weighting_profile=profile, assessment_type=at, weight_percentage=w)
                total_weight += w

        if total_weight != Decimal('100'):
            messages.warning(request, f"Weights saved but total is {total_weight}%, not 100%. Please adjust.")
        else:
            messages.success(request, f"Weights for {subject.name} in {section} saved successfully (100%).")
        return redirect('report_settings')

    sections = Section.objects.all()
    subjects = Subject.objects.all()
    assessment_types = AssessmentType.objects.all()
    existing = SubjectWeighting.objects.all().select_related('section', 'subject').prefetch_related('components__assessment_type')

    context = {
        'sections': sections,
        'subjects': subjects,
        'assessment_types': assessment_types,
        'existing_weightings': existing,
    }
    return render(request, 'dashboard/report_settings.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def manage_assessments(request):

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        section_id = request.POST.get('section')
        subject_id = request.POST.get('subject')
        assessment_type_id = request.POST.get('assessment_type')
        total_marks_str = request.POST.get('total_marks', '100').strip()
        date_conducted = request.POST.get('date_conducted', timezone.now().date().isoformat())

        # ── Validate total_marks before touching the DB ────────────────────
        try:
            total_marks = Decimal(total_marks_str)
            if total_marks <= 0:
                raise ValueError("Total marks must be greater than zero.")
        except Exception:
            messages.error(request, f"Invalid total marks value: '{total_marks_str}'. Must be a positive number.")
            return redirect('manage_assessments')

        if not title:
            messages.error(request, "Assessment title is required.")
            return redirect('manage_assessments')

        if request.user.role != User.Role.ADMIN and not _teaches(request.user, section_id, subject_id):
            messages.error(request, NOT_YOUR_CLASS)
            return redirect('manage_assessments')

        try:
            section = Section.objects.get(id=section_id)
            subject = Subject.objects.get(id=subject_id)
            assessment_type = AssessmentType.objects.get(id=assessment_type_id)
            record = AssessmentRecord.objects.create(
                section=section, subject=subject, assessment_type=assessment_type,
                title=title, total_marks=total_marks, date_conducted=date_conducted
            )
            messages.success(request, f"Assessment '{title}' created. Now enter marks.")
            return redirect(reverse('enter_marks', args=[record.id]))
        except (Section.DoesNotExist, Subject.DoesNotExist, AssessmentType.DoesNotExist):
            messages.error(request, "Invalid section, subject, or assessment type selected.")
        except Exception as e:
            logger.error("Failed to create assessment: %s", e, exc_info=True)
            messages.error(request, "An unexpected error occurred. Please try again.")
        return redirect('manage_assessments')

    if request.user.role == User.Role.ADMIN:
        sections = Section.objects.all()
        subjects = Subject.objects.all()
    else:
        sections = Section.objects.filter(timetable_entries__teacher=request.user).distinct()
        subjects = Subject.objects.filter(timetableentry__teacher=request.user).distinct()
    assessment_types = AssessmentType.objects.all()
    try:
        recent = list(
            _assessments_for(request.user)
            .select_related('section__class_group', 'subject', 'assessment_type')
            .order_by('-date_conducted')[:20]
        )
    except Exception as e:
        logger.error("Failed to load recent assessments (possible corrupt decimal data): %s", e, exc_info=True)
        recent = []
        messages.warning(request, "Some assessment records could not be loaded due to data issues. Please check and fix any assessments with invalid marks.")

    context = {
        'sections': sections,
        'subjects': subjects,
        'assessment_types': assessment_types,
        'recent_assessments': recent,
    }
    return render(request, 'dashboard/manage_assessments.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def delete_assessment(request, assessment_id):
    if request.method == 'POST':
        allowed = _assessments_for(request.user)
        if not allowed.filter(pk=assessment_id).exists():
            messages.error(request, NOT_YOUR_CLASS)
            return redirect('manage_assessments')
        try:
            assessment = get_object_or_404(allowed, pk=assessment_id)
            title = assessment.title
            assessment.delete()
            messages.success(request, f"Assessment '{title}' has been deleted successfully.")
        except Exception as e:
            # Fallback: if fetching fails due to corrupt decimal data, delete by pk directly
            deleted, _ = allowed.filter(pk=assessment_id).delete()
            if deleted:
                messages.success(request, "Assessment deleted successfully.")
            else:
                logger.error("Failed to delete assessment %s: %s", assessment_id, e, exc_info=True)
                messages.error(request, "Could not delete the assessment.")
    return redirect('manage_assessments')

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def enter_marks(request, assessment_id):

    try:
        assessment = get_object_or_404(AssessmentRecord, pk=assessment_id)
    except Exception as e:
        logger.error("Failed to load assessment %s (possible corrupt data): %s", assessment_id, e, exc_info=True)
        messages.error(request, "This assessment record could not be loaded due to data issues.")
        return redirect('manage_assessments')
    if not _can_manage_assessment(request.user, assessment):
        messages.error(request, NOT_YOUR_CLASS)
        return redirect('manage_assessments')
    profiles = section_profiles(assessment.section)   # current students, by roll number
    existing = {s.student_id: s for s in StudentScore.objects.filter(assessment=assessment)}

    if request.method == 'POST':
        saved, not_applicable, cleared = 0, 0, 0
        errors = []
        for p in profiles:
            name = p.user.get_full_name() or p.user.username
            current = existing.get(p.user_id)
            if request.POST.get(f'na_{p.user_id}') == 'on':
                StudentScore.objects.update_or_create(
                    assessment=assessment, student=p.user,
                    defaults={'marks_obtained': Decimal('0'), 'not_applicable': True},
                )
                not_applicable += 1
                continue
            marks = request.POST.get(f'marks_{p.user_id}', '').strip()
            if not marks:
                # Unticking N/A without entering a mark returns the student to "not entered".
                if current and current.not_applicable:
                    current.delete()
                    cleared += 1
                continue
            try:
                m = Decimal(marks)
                if m < 0:
                    raise ValueError("Marks cannot be negative.")
                if m > assessment.total_marks:
                    raise ValueError(f"Marks ({m}) exceed total ({assessment.total_marks}).")
                StudentScore.objects.update_or_create(
                    assessment=assessment, student=p.user,
                    defaults={'marks_obtained': m, 'not_applicable': False},
                )
                saved += 1
            except (ValueError, ArithmeticError) as e:
                errors.append(f"{name}: {e if isinstance(e, ValueError) else 'not a valid number.'}")
            except Exception as e:
                logger.warning("Could not save mark for student %s: %s", p.user_id, e)
                errors.append(f"{name}: Could not save.")
        for err in errors:
            messages.warning(request, err)
        if saved or not_applicable or cleared:
            parts = [f"{saved} mark{'s' if saved != 1 else ''} saved"]
            if not_applicable:
                parts.append(f"{not_applicable} marked N/A")
            if cleared:
                parts.append(f"{cleared} N/A cleared")
            messages.success(request, f"'{assessment.title}': " + ", ".join(parts) + ".")
        return redirect(reverse('enter_marks', args=[assessment_id]))

    students_marks = []
    for p in profiles:
        score = existing.get(p.user_id)
        marks_val, is_na = '', False
        if score:
            is_na = score.not_applicable
            try:
                # Guard against any corrupt stored decimal values
                marks_val = '' if is_na else Decimal(str(score.marks_obtained))
            except Exception:
                logger.error("Corrupt marks_obtained for student %s in assessment %s — resetting display.",
                             p.user_id, assessment_id)
                marks_val = ''
        students_marks.append({'user': p.user, 'roll': p.roll_number, 'marks': marks_val, 'na': is_na})

    context = {
        'assessment': assessment,
        'students_marks': students_marks,
        'na_count': sum(1 for s in students_marks if s['na']),
        'entered_count': sum(1 for s in students_marks if s['marks'] != ''),
    }
    return render(request, 'dashboard/enter_marks.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def view_reports(request):
    """Admin/Teacher view: list students and link to their report cards."""

    section_id = request.GET.get('section', '')
    sections = Section.objects.all()
    students = []

    if section_id:
        profiles = StudentProfile.objects.filter(section_id=section_id).select_related('user', 'section')
    else:
        profiles = StudentProfile.objects.all().select_related('user', 'section')

    for p in profiles:
        students.append({
            'user': p.user,
            'profile': p,
        })

    section_obj, periods = None, []
    if section_id:
        section_obj = sections.filter(id=section_id).first()
        config = period_config(section_obj) if section_obj else None
        if config:
            periods = list(config.periods.order_by('sequence'))

    context = {
        'sections': sections,
        'students': students,
        'selected_section': section_id,
        'section_obj': section_obj,
        'periods': periods,
    }
    return render(request, 'dashboard/view_reports.html', context)


def _can_view_student_report(viewer, student):
    """Students may only see their own report; parents only their linked children."""
    if viewer.role == User.Role.STUDENT:
        return viewer == student
    if viewer.role == User.Role.PARENT:
        return ParentProfile.objects.filter(user=viewer, children=student).exists()
    return True


@login_required
def student_report(request, student_id=None):
    """View a student's complete report card with weighted grades, letter grades, and comments."""
    viewer = request.user
    printable = request.GET.get('print', '') == '1'

    if student_id:
        student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    elif viewer.role == User.Role.STUDENT:
        student = viewer
    else:
        return redirect('view_reports')

    if not _can_view_student_report(viewer, student):
        return redirect('dashboard_router')

    card = report_card(student, viewer=viewer)
    context = _report_context(request, student, card)
    if printable:
        return render(request, 'dashboard/report_card_print.html',
                      {'cards': [card] if card else [], 'section': context['section']})
    return render(request, 'dashboard/student_report.html', context)


def _remark_permissions(user, section):
    """(can edit class teacher's remark, can edit principal's remark) for this section."""
    if user.role == User.Role.ADMIN:
        return True, True
    if section and user.role in (User.Role.TEACHER, User.Role.COORDINATOR):
        return TimetableEntry.objects.filter(teacher=user, section=section).exists(), False
    return False, False


def _report_context(request, student, card, period=None):
    section = card['section'] if card else None
    can_teacher, can_principal = _remark_permissions(request.user, section)
    empty = {'grades': [], 'overall_avg': None, 'overall_letter': get_letter_grade(None), 'gpa': None,
             'provisional': False, 'marks_limited': False, 'attendance': {'total': 0},
             'remarks': {'class_teacher': '', 'principal': ''}, 'grade_settings': []}
    return {
        'student': student,
        'section': section,
        'profile': card['profile'] if card else StudentProfile.objects.filter(user=student).first(),
        'period': period,
        **(card or empty),
        'can_edit_class_teacher_remark': can_teacher,
        'can_edit_principal_remark': can_principal,
    }


@login_required
@require_POST
def save_report_remarks(request):
    """Save the class teacher's and/or principal's remark for one student's report card."""
    student = get_object_or_404(User, pk=request.POST.get('student'), role=User.Role.STUDENT)
    profile = StudentProfile.objects.filter(user=student).select_related('section').first()
    section = profile.section if profile else None
    period = None
    if request.POST.get('period'):
        period = get_object_or_404(ReportPeriod, pk=request.POST['period'])
    can_teacher, can_principal = _remark_permissions(request.user, section)
    back = (reverse('period_report', args=[period.id, student.id]) if period
            else reverse('student_report_detail', args=[student.id]))
    if not section or not (can_teacher or can_principal):
        messages.error(request, "You can't write remarks for this student.")
        return redirect(back)

    remark, _ = ReportRemark.objects.get_or_create(
        student=student, academic_year=section.academic_year, period=period)
    if can_teacher and 'class_teacher_remark' in request.POST:
        remark.class_teacher_remark = request.POST['class_teacher_remark'].strip()
    if can_principal and 'principal_remark' in request.POST:
        remark.principal_remark = request.POST['principal_remark'].strip()
    remark.updated_by = request.user
    remark.save()
    messages.success(request, "Remarks saved.")
    return redirect(back)


@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER, User.Role.COORDINATOR)
def print_section_report_cards(request):
    """Every student's report card in a section on one printable page, one card per page."""
    section = get_object_or_404(Section.objects.select_related('class_group'), pk=request.GET.get('section'))
    period = None
    if request.GET.get('period'):
        period = get_object_or_404(ReportPeriod, pk=request.GET['period'])
    cards = build_report_cards(section, section_profiles(section), viewer=request.user, period=period)
    return render(request, 'dashboard/report_card_print.html',
                  {'cards': cards, 'section': section, 'period': period})



@login_required
@role_required(User.Role.ADMIN)
def grade_settings_view(request):
    """Admin: configure letter grade boundaries."""

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            letter = request.POST.get('letter', '').strip()
            min_s = request.POST.get('min_score', '0')
            max_s = request.POST.get('max_score', '100')
            gp = request.POST.get('grade_point', '0')
            remark = request.POST.get('remark', '').strip()
            try:
                GradeSetting.objects.create(
                    letter=letter, min_score=Decimal(min_s), max_score=Decimal(max_s),
                    grade_point=Decimal(gp), remark=remark
                )
                messages.success(request, f"Grade '{letter}' added.")
            except Exception as e:
                logger.error("Failed to create GradeSetting: %s", e, exc_info=True)
                messages.error(request, str(e))

        elif action == 'delete':
            grade_id = request.POST.get('grade_id')
            GradeSetting.objects.filter(id=grade_id).delete()
            messages.success(request, "Grade deleted.")

        return redirect('grade_settings')

    existing = GradeSetting.objects.all()
    context = {'grades': existing}
    return render(request, 'dashboard/grade_settings.html', context)

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def subject_comments_view(request):
    """Teacher: add comments for students per subject per period."""

    sections = Section.objects.all()
    subjects = Subject.objects.all()
    selected_section = None
    selected_subject = None
    selected_period = None
    available_periods = []
    students_comments = []

    # Build period list when section is selected
    section_id_param = request.GET.get('section') or request.POST.get('section_id')
    if section_id_param:
        sec = Section.objects.filter(id=section_id_param).first()
        if sec:
            # Try exact match first, then fuzzy match (e.g. "2026" contained in "2025-2026")
            config = AcademicPeriodConfig.objects.filter(academic_year=sec.academic_year).first()
            if not config:
                config = AcademicPeriodConfig.objects.filter(academic_year__contains=sec.academic_year).first()
            if config:
                available_periods = list(config.periods.order_by('sequence'))

    if request.method == 'POST':
        section_id = request.POST.get('section_id')
        subject_id = request.POST.get('subject_id')
        period_id = request.POST.get('period_id')
        section = Section.objects.filter(id=section_id).first()
        subject = Subject.objects.filter(id=subject_id).first()
        period = ReportPeriod.objects.filter(id=period_id).first() if period_id else None
        if section and subject and period:
            profiles = StudentProfile.objects.filter(section=section).select_related('user')
            for p in profiles:
                comment_text = request.POST.get(f'comment_{p.user.id}', '').strip()
                if comment_text:
                    SubjectComment.objects.update_or_create(
                        student=p.user, subject=subject, section=section,
                        academic_year=section.academic_year, period=period,
                        defaults={'comment': comment_text, 'commented_by': request.user}
                    )
            messages.success(request, f"Comments saved for {subject.name} — {period.label} in {section}.")
        elif not period:
            messages.error(request, "Please select a reporting period.")
        url = reverse('subject_comments') + f'?section={section_id}&subject={subject_id}&period={period_id or ""}'
        return redirect(url)

    if request.GET.get('section') and request.GET.get('subject') and request.GET.get('period'):
        selected_section = Section.objects.filter(id=request.GET['section']).first()
        selected_subject = Subject.objects.filter(id=request.GET['subject']).first()
        selected_period = ReportPeriod.objects.filter(id=request.GET['period']).first()
        if selected_section and selected_subject and selected_period:
            profiles = StudentProfile.objects.filter(section=selected_section).select_related('user')
            for p in profiles:
                existing = SubjectComment.objects.filter(
                    student=p.user, subject=selected_subject, section=selected_section,
                    academic_year=selected_section.academic_year, period=selected_period
                ).first()
                students_comments.append({
                    'user': p.user,
                    'roll': p.roll_number,
                    'comment': existing.comment if existing else '',
                })

    # Build JSON of all periods grouped by section ID for client-side JS
    # Handles mismatch: section.academic_year may be "2026" while config is "2025-2026"
    import json
    all_configs = AcademicPeriodConfig.objects.prefetch_related('periods').all()
    periods_by_section = {}
    for sec in sections:
        for cfg in all_configs:
            # Match if exact or if section year is contained in config year (e.g. "2026" in "2025-2026")
            if sec.academic_year == cfg.academic_year or sec.academic_year in cfg.academic_year:
                periods_by_section[str(sec.id)] = [
                    {'id': p.id, 'label': p.label}
                    for p in cfg.periods.order_by('sequence')
                ]
                break

    context = {
        'sections': sections,
        'subjects': subjects,
        'selected_section': selected_section,
        'selected_subject': selected_subject,
        'selected_period': selected_period,
        'available_periods': available_periods,
        'students_comments': students_comments,
        'periods_json': json.dumps(periods_by_section),
    }
    return render(request, 'dashboard/subject_comments.html', context)

# Grade helpers are now in exams/services.py — imported at the top of this file.
# Legacy aliases kept temporarily to avoid breaking any external references.
_calculate_student_grade = calculate_student_grade
_get_grade_details = get_grade_details
_get_letter_grade = get_letter_grade


# ─── CT PROGRESS REPORT ──────────────────────────────────────────────────────

MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]


@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER, User.Role.COORDINATOR)
def ct_progress_report(request):
    """Selection page: pick section, term (or month), class-test type and layout."""
    from exams.ct_report import detect_ct_type

    today = timezone.localdate()
    periods = list(ReportPeriod.objects.select_related('config')
                   .order_by('-config__academic_year', 'sequence'))
    current = next((p for p in periods if p.start_date <= today <= p.end_date), None)
    types = list(AssessmentType.objects.order_by('name'))
    context = {
        'sections': Section.objects.select_related('class_group').order_by('class_group__name', 'name'),
        'periods': periods,
        'current_period': current,
        'ct_types': types,
        'default_ct_type': detect_ct_type(types),
        'today': today,
        'months': [(i, MONTH_NAMES[i]) for i in range(1, 13)],
        'current_month': today.month,
        'current_year': today.year,
    }
    return render(request, 'dashboard/ct_progress_select.html', context)


@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER, User.Role.COORDINATOR)
def ct_progress_report_print(request):
    """Print-ready CT progress report: one sheet per student, or a class marksheet."""
    from exams.ct_report import ct_progress, detect_ct_type, fallback_range

    section = Section.objects.select_related('class_group').filter(pk=request.GET.get('section') or None).first()
    if not section:
        messages.error(request, "Choose a section.")
        return redirect('ct_progress_report')

    try:
        if request.GET.get('period'):
            period = get_object_or_404(ReportPeriod, pk=request.GET['period'])
            start, end = period.start_date, period.end_date
            upto = request.GET.get('upto')
            if upto:
                end = min(end, datetime.date.fromisoformat(upto))
            term_label = period.label
        else:
            month, year = int(request.GET.get('month', 0)), int(request.GET.get('year', 0))
            if not 1 <= month <= 12 or year < 2000:
                raise ValueError
            term_label, start, end = fallback_range(month, year)
    except ValueError:
        messages.error(request, "Choose a term, or a valid month and year.")
        return redirect('ct_progress_report')

    if end < start:
        messages.error(request, "The “up to” date is before the start of the term.")
        return redirect('ct_progress_report')

    ct_type = None
    if request.GET.get('ct_type'):
        ct_type = AssessmentType.objects.filter(pk=request.GET['ct_type']).first()
    ct_type = ct_type or detect_ct_type()
    if not ct_type:
        messages.error(request, "No class test assessment type was found. Choose one, or create a type named “Class Test”.")
        return redirect('ct_progress_report')

    layout = 'marksheet' if request.GET.get('layout') == 'marksheet' else 'sheets'
    context = {
        'section': section,
        'term_label': term_label,
        'start': start,
        'end': end,
        'ct_type': ct_type,
        'layout': layout,
        **ct_progress(section, ct_type, start, end),
    }
    return render(request, 'dashboard/ct_progress_print.html', context)


@login_required
def my_ct_progress(request, student_id=None):
    """
    A student's own class test progress (or a parent's child's): for one month,
    a term, or any date range. Staff can open it for any student.
    """
    from exams.ct_report import ct_progress, detect_ct_type, month_end

    viewer = request.user
    if student_id:
        student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    elif viewer.role == User.Role.STUDENT:
        student = viewer
    else:
        return redirect('dashboard_router')
    if not _can_view_student_report(viewer, student):
        return redirect('dashboard_router')

    profile = StudentProfile.objects.filter(user=student).select_related('section__class_group').first()
    section = profile.section if profile else None
    today = timezone.localdate()
    periods = []
    if section:
        config = period_config(section)
        if config:
            periods = list(config.periods.order_by('sequence'))

    view = request.GET.get('view', 'month')
    error = None
    start = end = None
    label = ''
    selected_period = None
    month_value = request.GET.get('month') or today.strftime('%Y-%m')
    from_value = request.GET.get('from', '')
    to_value = request.GET.get('to', '')
    try:
        if view == 'term' and periods:
            selected_period = next((p for p in periods if str(p.id) == request.GET.get('period')), None) \
                or next((p for p in periods if p.start_date <= today <= p.end_date), None) or periods[-1]
            start, end, label = selected_period.start_date, selected_period.end_date, selected_period.label
        elif view == 'range':
            start = datetime.date.fromisoformat(from_value) if from_value else today.replace(day=1)
            end = datetime.date.fromisoformat(to_value) if to_value else today
            if end < start:
                error = "The end date is before the start date."
            label = f"{start:%-d %b} to {end:%-d %b %Y}"
            from_value, to_value = start.isoformat(), end.isoformat()
        else:
            view = 'month'
            year, month = (int(x) for x in month_value.split('-'))
            start, end = datetime.date(year, month, 1), month_end(year, month)
            label = f"{MONTH_NAMES[month]} {year}"
    except ValueError:
        error = "Choose a valid month or dates."

    ct_type = detect_ct_type()
    entry, report = None, {}
    if section and ct_type and start and not error:
        report = ct_progress(section, ct_type, start, end)
        entry = next((s for s in report['students'] if s['student'] == student), None)

    context = {
        'student': student,
        'profile': profile,
        'section': section,
        'periods': periods,
        'view': view,
        'selected_period': selected_period,
        'month_value': month_value,
        'from_value': from_value,
        'to_value': to_value,
        'label': label,
        'start': start,
        'end': end,
        'error': error,
        'ct_type': ct_type,
        'entry': entry,
        'class_avg': report.get('class_avg'),
        'grade_settings': report.get('grade_settings', []),
        'unmarked': report.get('unmarked', []),
    }
    if request.GET.get('print') == '1' and entry:
        return render(request, 'dashboard/ct_progress_print.html', {
            **context, 'students': [entry], 'layout': 'sheets', 'single_student': True,
            'term_label': label,
        })
    return render(request, 'dashboard/my_ct_progress.html', context)


@login_required
@role_required(User.Role.ADMIN)
def period_setup(request):
    """Admin: configure reporting mode, period date ranges, and weights."""
    assessment_types = AssessmentType.objects.all()
    configs = AcademicPeriodConfig.objects.prefetch_related(
        'periods__weightings__assessment_type'
    ).all()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_config':
            academic_year = request.POST.get('academic_year', '').strip()
            mode = request.POST.get('mode')
            if not academic_year or not mode:
                messages.error(request, "Please fill in all fields.")
                return redirect('period_setup')

            if AcademicPeriodConfig.objects.filter(academic_year=academic_year).exists():
                messages.error(request, f"Configuration for {academic_year} already exists. Delete it first to recreate.")
                return redirect('period_setup')

            config = AcademicPeriodConfig.objects.create(
                academic_year=academic_year, mode=mode, created_by=request.user
            )

            if mode == AcademicPeriodConfig.Mode.QUARTERLY:
                period_count = 4
                default_labels = ['1st Quarter', '2nd Quarter', '3rd Quarter', '4th Quarter']
            else:
                period_count = 2
                default_labels = ['Mid-Term', 'Final-Term']

            for i in range(period_count):
                start_date = request.POST.get(f'start_date_{i+1}', '')
                end_date = request.POST.get(f'end_date_{i+1}', '')
                label = request.POST.get(f'label_{i+1}', default_labels[i]).strip() or default_labels[i]

                if not start_date or not end_date:
                    messages.error(request, "Please provide dates for all periods.")
                    config.delete()
                    return redirect('period_setup')

                ReportPeriod.objects.create(
                    config=config,
                    label=label,
                    sequence=i + 1,
                    start_date=start_date,
                    end_date=end_date,
                )

            messages.success(request, f"Reporting periods for {academic_year} created successfully!")

        elif action == 'save_weights':
            period_id = request.POST.get('period_id')
            period = get_object_or_404(ReportPeriod, id=period_id)
            period.weightings.filter(subject__isnull=True).delete()

            total_weight = Decimal('0')
            for at in assessment_types:
                w = request.POST.get(f'weight_{period_id}_{at.id}', '0')
                try:
                    w = Decimal(w)
                except Exception:
                    w = Decimal('0')
                if w > 0:
                    PeriodWeighting.objects.create(
                        period=period, assessment_type=at, weight_percentage=w
                    )
                    total_weight += w

            if total_weight != Decimal('100'):
                messages.warning(request, f"Default weights for '{period.label}' saved but total is {total_weight}%, not 100%.")
            else:
                messages.success(request, f"Default weights for '{period.label}' saved (100%). ✅")

        elif action == 'save_subject_weights':
            period_id = request.POST.get('period_id')
            subject_id = request.POST.get('subject_id')
            period = get_object_or_404(ReportPeriod, id=period_id)
            subject = get_object_or_404(Subject, id=subject_id)
            period.weightings.filter(subject=subject).delete()

            total_weight = Decimal('0')
            for at in assessment_types:
                w = request.POST.get(f'sw_{period_id}_0_{at.id}', '0')
                try:
                    w = Decimal(w)
                except Exception:
                    w = Decimal('0')
                if w > 0:
                    PeriodWeighting.objects.create(
                        period=period, assessment_type=at, subject=subject, weight_percentage=w
                    )
                    total_weight += w

            if total_weight == Decimal('0'):
                messages.success(request, f"Subject override for '{subject.name}' in '{period.label}' removed (using defaults).")
            elif total_weight != Decimal('100'):
                messages.warning(request, f"Weights for '{subject.name}' in '{period.label}' saved but total is {total_weight}%, not 100%.")
            else:
                messages.success(request, f"Weights for '{subject.name}' in '{period.label}' saved (100%). ✅")

        elif action == 'toggle_publish':
            period_id = request.POST.get('period_id')
            period = get_object_or_404(ReportPeriod, id=period_id)
            period.is_published = not period.is_published
            period.save()
            status = 'published' if period.is_published else 'unpublished'
            messages.success(request, f"'{period.label}' is now {status}.")

        elif action == 'delete_config':
            config_id = request.POST.get('config_id')
            AcademicPeriodConfig.objects.filter(id=config_id).delete()
            messages.success(request, "Configuration deleted.")

        return redirect('period_setup')

    subjects = Subject.objects.all()
    context = {
        'configs': configs,
        'assessment_types': assessment_types,
        'modes': AcademicPeriodConfig.Mode.choices,
        'subjects': subjects,
    }
    return render(request, 'dashboard/period_setup.html', context)


@login_required
def period_report_select(request, student_id=None):
    """Show available published periods for report generation."""
    viewer = request.user

    if student_id:
        student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    elif viewer.role == User.Role.STUDENT:
        student = viewer
    else:
        return redirect('view_reports')

    if not _can_view_student_report(viewer, student):
        return redirect('dashboard_router')

    profile = StudentProfile.objects.filter(user=student).first()
    section = profile.section if profile else None

    configs = []
    if section:
        # Try exact match first
        config = AcademicPeriodConfig.objects.filter(academic_year=section.academic_year).first()
        # Fallback: try partial match (e.g. section="2026" matches config="2025-26")
        if not config:
            config = AcademicPeriodConfig.objects.filter(
                academic_year__icontains=section.academic_year
            ).first()
        if not config:
            # Last resort: show all configs so the user isn't stuck
            all_configs = AcademicPeriodConfig.objects.all()
            for c in all_configs:
                if viewer.role in [User.Role.ADMIN, User.Role.TEACHER]:
                    periods = c.periods.all()
                else:
                    periods = c.periods.filter(is_published=True)
                configs.append({'config': c, 'periods': periods})
        else:
            if viewer.role in [User.Role.ADMIN, User.Role.TEACHER]:
                periods = config.periods.all()
            else:
                periods = config.periods.filter(is_published=True)
            configs.append({'config': config, 'periods': periods})

    context = {
        'student': student,
        'profile': profile,
        'section': section,
        'configs': configs,
    }
    return render(request, 'dashboard/period_report_select.html', context)


@login_required
def period_report(request, period_id, student_id):
    """View a student's report card for a specific period."""
    viewer = request.user
    period = get_object_or_404(ReportPeriod.objects.select_related('config'), id=period_id)
    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    printable = request.GET.get('print', '') == '1'

    if not _can_view_student_report(viewer, student):
        return redirect('dashboard_router')

    if viewer.role not in [User.Role.ADMIN, User.Role.TEACHER] and not period.is_published:
        messages.error(request, "This report period is not yet published.")
        return redirect('dashboard_router')

    card = report_card(student, viewer=viewer, period=period)
    context = _report_context(request, student, card, period=period)

    if printable:
        return render(request, 'dashboard/report_card_print.html',
                      {'cards': [card] if card else [], 'section': context['section'], 'period': period})
    return render(request, 'dashboard/period_report.html', context)


# _calculate_period_grade is now in exams/services.py as calculate_period_grade.
# Alias kept for any external code that may reference it.
_calculate_period_grade = calculate_period_grade
