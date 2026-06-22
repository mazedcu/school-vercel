from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Q

from accounts.models import User
from academics.models import Subject, Section
from timetable.models import TimetableEntry
from accounts.decorators import role_required
from .models import LessonPlan


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_teacher_subjects(user):
    """Return subjects a teacher/coordinator teaches via timetable."""
    return Subject.objects.filter(timetableentry__teacher=user).distinct()


def get_teacher_sections(user):
    """Return sections a teacher/coordinator teaches via timetable."""
    return Section.objects.filter(timetable_entries__teacher=user).distinct().select_related('class_group')


# ── List ──────────────────────────────────────────────────────────────────────

@login_required
def lesson_plan_list(request):
    user = request.user

    if user.role == User.Role.ADMIN:
        plans = LessonPlan.objects.select_related('teacher', 'subject', 'section__class_group').all()
        pending_count = plans.filter(status=LessonPlan.Status.SUBMITTED).count()

    elif user.role == User.Role.COORDINATOR:
        # Coordinator sees: their own plans + submitted plans for subjects they teach
        my_subjects = get_teacher_subjects(user)
        plans = LessonPlan.objects.select_related('teacher', 'subject', 'section__class_group').filter(
            Q(teacher=user) |
            Q(subject__in=my_subjects, status__in=[
                LessonPlan.Status.SUBMITTED,
                LessonPlan.Status.APPROVED,
                LessonPlan.Status.REJECTED,
            ])
        ).distinct()
        pending_count = plans.filter(
            subject__in=my_subjects, status=LessonPlan.Status.SUBMITTED
        ).exclude(teacher=user).count()

    else:  # Teacher
        plans = LessonPlan.objects.select_related('subject', 'section__class_group').filter(teacher=user)
        pending_count = 0

    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        plans = plans.filter(status=status_filter)

    from django.core.paginator import Paginator
    paginator = Paginator(plans, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'plans': plans,
        'status_filter': status_filter,
        'pending_count': pending_count,
        'status_choices': LessonPlan.Status.choices,
    }
    return render(request, 'lessonplan/lesson_plan_list.html', context)


# ── Create ────────────────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.TEACHER, User.Role.COORDINATOR, User.Role.ADMIN)
def lesson_plan_create(request):
    user = request.user

    # Build subject and section choices from timetable for teachers/coordinators
    if user.role == User.Role.ADMIN:
        subjects = Subject.objects.all()
        sections = Section.objects.select_related('class_group').all()
    else:
        subjects = get_teacher_subjects(user)
        sections = get_teacher_sections(user)

    if request.method == 'POST':
        action = request.POST.get('action', 'draft')  # 'draft' or 'submit'
        plan = LessonPlan(teacher=user)
        _fill_plan_from_post(plan, request.POST)
        plan.status = LessonPlan.Status.SUBMITTED if action == 'submit' else LessonPlan.Status.DRAFT
        try:
            plan.save()
            if plan.status == LessonPlan.Status.SUBMITTED:
                messages.success(request, "Lesson plan submitted for review.")
            else:
                messages.success(request, "Lesson plan saved as draft.")
            return redirect('lesson_plan_detail', pk=plan.pk)
        except Exception as e:
            messages.error(request, f"Error saving plan: {e}")

    context = {
        'subjects': subjects,
        'sections': sections,
        'form_title': 'New Lesson Plan',
        'plan': None,
    }
    return render(request, 'lessonplan/lesson_plan_form.html', context)


# ── Detail ────────────────────────────────────────────────────────────────────

@login_required
def lesson_plan_detail(request, pk):
    plan = get_object_or_404(LessonPlan, pk=pk)
    user = request.user

    # Access control
    if user.role not in [User.Role.ADMIN, User.Role.COORDINATOR] and plan.teacher != user:
        messages.error(request, "You don't have permission to view this lesson plan.")
        return redirect('lesson_plan_list')

    can_review = plan.can_review(user) and plan.status == LessonPlan.Status.SUBMITTED
    can_edit = plan.can_edit(user)

    context = {
        'plan': plan,
        'can_review': can_review,
        'can_edit': can_edit,
    }
    return render(request, 'lessonplan/lesson_plan_detail.html', context)


# ── Edit ──────────────────────────────────────────────────────────────────────

@login_required
def lesson_plan_edit(request, pk):
    plan = get_object_or_404(LessonPlan, pk=pk)
    user = request.user

    if not plan.can_edit(user):
        messages.error(request, "You cannot edit this lesson plan.")
        return redirect('lesson_plan_detail', pk=pk)

    if user.role == User.Role.ADMIN:
        subjects = Subject.objects.all()
        sections = Section.objects.select_related('class_group').all()
    else:
        subjects = get_teacher_subjects(user)
        sections = get_teacher_sections(user)

    if request.method == 'POST':
        action = request.POST.get('action', 'draft')
        _fill_plan_from_post(plan, request.POST)
        plan.status = LessonPlan.Status.SUBMITTED if action == 'submit' else LessonPlan.Status.DRAFT
        # Clear reviewer notes if re-submitting
        if plan.status == LessonPlan.Status.SUBMITTED:
            plan.reviewer_notes = ''
        plan.save()
        if plan.status == LessonPlan.Status.SUBMITTED:
            messages.success(request, "Lesson plan re-submitted for review.")
        else:
            messages.success(request, "Lesson plan saved as draft.")
        return redirect('lesson_plan_detail', pk=pk)

    context = {
        'subjects': subjects,
        'sections': sections,
        'form_title': 'Edit Lesson Plan',
        'plan': plan,
    }
    return render(request, 'lessonplan/lesson_plan_form.html', context)


# ── Review (Approve / Reject) ─────────────────────────────────────────────────

@login_required
def lesson_plan_review(request, pk):
    plan = get_object_or_404(LessonPlan, pk=pk)
    user = request.user

    if not plan.can_review(user):
        messages.error(request, "You don't have permission to review this lesson plan.")
        return redirect('lesson_plan_detail', pk=pk)

    if plan.status != LessonPlan.Status.SUBMITTED:
        messages.error(request, "This plan is not pending review.")
        return redirect('lesson_plan_detail', pk=pk)

    if request.method == 'POST':
        decision = request.POST.get('decision')
        notes = request.POST.get('reviewer_notes', '').strip()
        if decision == 'approve':
            plan.status = LessonPlan.Status.APPROVED
            plan.reviewer_notes = notes
            plan.reviewed_by = user
            plan.reviewed_at = timezone.now()
            plan.save()
            messages.success(request, "Lesson plan approved.")
        elif decision == 'reject':
            if not notes:
                messages.error(request, "Please provide a reason for rejection.")
                return redirect('lesson_plan_detail', pk=pk)
            plan.status = LessonPlan.Status.REJECTED
            plan.reviewer_notes = notes
            plan.reviewed_by = user
            plan.reviewed_at = timezone.now()
            plan.save()
            messages.warning(request, "Lesson plan rejected. The teacher will be notified.")
        return redirect('lesson_plan_detail', pk=pk)

    return redirect('lesson_plan_detail', pk=pk)


# ── Delete ────────────────────────────────────────────────────────────────────

@login_required
def lesson_plan_delete(request, pk):
    plan = get_object_or_404(LessonPlan, pk=pk)
    user = request.user

    # Admin can delete anything; teacher can only delete their own draft/rejected plans
    if user.role == User.Role.ADMIN:
        can_delete = True
    elif plan.teacher == user and plan.status in [LessonPlan.Status.DRAFT, LessonPlan.Status.REJECTED]:
        can_delete = True
    else:
        can_delete = False

    if not can_delete:
        messages.error(request, "You cannot delete this lesson plan.")
        return redirect('lesson_plan_detail', pk=pk)

    if request.method == 'POST':
        title = plan.lesson_title
        plan.delete()
        messages.success(request, f'Lesson plan "{title}" has been deleted.')
        return redirect('lesson_plan_list')

    # GET — show confirmation page
    return render(request, 'lessonplan/lesson_plan_confirm_delete.html', {'plan': plan})


# ── PDF Download ──────────────────────────────────────────────────────────────

@login_required
def lesson_plan_pdf(request, pk):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    import io

    plan = get_object_or_404(LessonPlan, pk=pk)
    user = request.user

    # Only approved plans can be downloaded (admin/coord/teacher who owns it)
    if plan.status != LessonPlan.Status.APPROVED:
        messages.error(request, "Only approved lesson plans can be downloaded.")
        return redirect('lesson_plan_detail', pk=pk)

    if user.role not in [User.Role.ADMIN, User.Role.COORDINATOR] and plan.teacher != user:
        messages.error(request, "You don't have permission to download this plan.")
        return redirect('lesson_plan_detail', pk=pk)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    PRIMARY = colors.HexColor('#4f46e5')
    LIGHT_BG = colors.HexColor('#f8fafc')
    BORDER = colors.HexColor('#e2e8f0')
    DARK = colors.HexColor('#0f172a')
    MUTED = colors.HexColor('#64748b')

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', fontSize=18, fontName='Helvetica-Bold',
                                  textColor=PRIMARY, spaceAfter=4, alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('Subtitle', fontSize=10, fontName='Helvetica',
                                     textColor=MUTED, spaceAfter=14, alignment=TA_CENTER)
    section_header = ParagraphStyle('SectionHeader', fontSize=10, fontName='Helvetica-Bold',
                                     textColor=colors.white, spaceAfter=0)
    body_style = ParagraphStyle('Body', fontSize=9, fontName='Helvetica',
                                 textColor=DARK, leading=14, spaceAfter=0)
    label_style = ParagraphStyle('Label', fontSize=8, fontName='Helvetica-Bold',
                                  textColor=MUTED, spaceAfter=2)

    story = []

    # ── Title block ──
    story.append(Paragraph("LESSON PLAN", title_style))
    story.append(Paragraph(
        f"{plan.lesson_title}",
        ParagraphStyle('LessonTitle', fontSize=14, fontName='Helvetica-Bold',
                       textColor=DARK, alignment=TA_CENTER, spaceAfter=4)
    ))
    story.append(Paragraph(
        f"Subject: {plan.subject.name} &nbsp;|&nbsp; {plan.section} &nbsp;|&nbsp; {plan.date.strftime('%d %B %Y')}",
        subtitle_style
    ))
    story.append(HRFlowable(width='100%', thickness=2, color=PRIMARY, spaceAfter=10))

    # ── Meta info table ──
    meta_data = [
        [Paragraph('<b>Teacher</b>', body_style), Paragraph(plan.teacher.get_full_name() or plan.teacher.username, body_style),
         Paragraph('<b>Subject</b>', body_style), Paragraph(plan.subject.name, body_style)],
        [Paragraph('<b>Class / Section</b>', body_style), Paragraph(str(plan.section), body_style),
         Paragraph('<b>Date</b>', body_style), Paragraph(plan.date.strftime('%d %B %Y'), body_style)],
        [Paragraph('<b>Main Topic</b>', body_style), Paragraph(plan.main_topic, body_style),
         Paragraph('<b>Duration</b>', body_style), Paragraph(plan.duration, body_style)],
    ]
    meta_table = Table(meta_data, colWidths=[3.5*cm, 6.5*cm, 3.5*cm, 4.5*cm])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BG),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
        ('INNERGRID', (0, 0), (-1, -1), 0.3, BORDER),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    def section_block(title, content):
        """Returns a styled section with a purple header and content."""
        header = Table(
            [[Paragraph(f"  {title}", section_header)]],
            colWidths=[18*cm]
        )
        header.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), PRIMARY),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))

        # Wrap content in a table for background
        content_table = Table(
            [[Paragraph(content.replace('\n', '<br/>') if content else '—', body_style)]],
            colWidths=[18*cm]
        )
        content_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.white),
            ('BOX', (0, 0), (-1, -1), 0.5, BORDER),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        return [header, content_table, Spacer(1, 8)]

    # ── Content sections ──
    for flowable in section_block("📘 Learning Objectives", plan.learning_objectives):
        story.append(flowable)
    for flowable in section_block("🧠 Prior Knowledge", plan.prior_knowledge):
        story.append(flowable)
    for flowable in section_block("📦 Resources", plan.resources):
        story.append(flowable)
    for flowable in section_block("🚀 Starter Activity", plan.starter):
        story.append(flowable)
    for flowable in section_block("📖 Main Lesson", plan.main_lesson):
        story.append(flowable)
    for flowable in section_block("✏️ Activities", plan.activities):
        story.append(flowable)
    for flowable in section_block("🎯 Differentiation", plan.differentiation):
        story.append(flowable)
    for flowable in section_block("🏁 Plenary", plan.plenary):
        story.append(flowable)

    # ── Approval stamp ──
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width='100%', thickness=1, color=BORDER, spaceAfter=8))
    if plan.reviewed_by:
        approved_text = (
            f"✅ Approved by {plan.reviewed_by.get_full_name() or plan.reviewed_by.username} "
            f"on {plan.reviewed_at.strftime('%d %B %Y at %H:%M')}"
        )
    else:
        approved_text = "✅ Approved"
    story.append(Paragraph(approved_text, ParagraphStyle(
        'Approved', fontSize=9, fontName='Helvetica', textColor=colors.HexColor('#059669'),
        alignment=TA_CENTER
    )))

    doc.build(story)
    buffer.seek(0)
    filename = f"lesson_plan_{plan.pk}_{plan.date}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── Helper ────────────────────────────────────────────────────────────────────

def _fill_plan_from_post(plan, post):
    plan.subject_id = post.get('subject') or None
    plan.section_id = post.get('section') or None
    plan.date = post.get('date') or None
    plan.duration = post.get('duration', '').strip()
    plan.main_topic = post.get('main_topic', '').strip()
    plan.lesson_title = post.get('lesson_title', '').strip()
    plan.learning_objectives = post.get('learning_objectives', '').strip()
    plan.prior_knowledge = post.get('prior_knowledge', '').strip()
    plan.resources = post.get('resources', '').strip()
    plan.starter = post.get('starter', '').strip()
    plan.main_lesson = post.get('main_lesson', '').strip()
    plan.activities = post.get('activities', '').strip()
    plan.differentiation = post.get('differentiation', '').strip()
    plan.plenary = post.get('plenary', '').strip()
