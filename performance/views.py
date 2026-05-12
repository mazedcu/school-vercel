"""
performance/views.py — All views for the Performance Management module.

Admin views:   cycle_list, cycle_create, cycle_detail, cycle_activate, cycle_close,
               kpi_section_add, kpi_section_delete, kpi_add, kpi_delete,
               evaluate_staff, report_html, report_pdf
Staff views:   my_evaluations, my_report_html
"""
import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from accounts.models import User
from students.models import TeacherProfile

from .models import KPI, KPIScore, KPISection, PerformanceCycle, StaffEvaluation
from .services import (
    calculate_final_score,
    get_performance_grade,
    get_staff_for_cycle,
    save_evaluation_scores,
    validate_cycle_weights,
)

logger = logging.getLogger(__name__)


# ─── ADMIN: Cycle Management ──────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def cycle_list(request):
    """Dashboard: all performance cycles with status and progress."""
    cycles = PerformanceCycle.objects.prefetch_related('evaluations').all()

    cycle_data = []
    for cycle in cycles:
        evals = cycle.evaluations.all()
        submitted = evals.filter(status=StaffEvaluation.Status.SUBMITTED).count()
        total = evals.count()
        teacher_weight = cycle.total_weight_for_role(KPISection.RoleType.TEACHER)
        coord_weight = cycle.total_weight_for_role(KPISection.RoleType.COORDINATOR)
        cycle_data.append({
            'cycle': cycle,
            'submitted': submitted,
            'total': total,
            'teacher_weight': teacher_weight,
            'coord_weight': coord_weight,
        })

    return render(request, 'performance/cycle_list.html', {'cycle_data': cycle_data})


@login_required
@role_required(User.Role.ADMIN)
def cycle_create(request):
    """Create a new performance cycle."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        if not name or not start_date or not end_date:
            messages.error(request, "All fields are required.")
        elif start_date >= end_date:
            messages.error(request, "Start date must be before end date.")
        else:
            cycle = PerformanceCycle.objects.create(
                name=name,
                start_date=start_date,
                end_date=end_date,
                created_by=request.user
            )
            messages.success(request, f"Cycle '{name}' created. Now build your KPI framework.")
            return redirect(reverse('performance_cycle_detail', args=[cycle.id]))

    return render(request, 'performance/cycle_create.html')


@login_required
@role_required(User.Role.ADMIN)
def cycle_detail(request, cycle_id):
    """
    KPI Builder: view/add/delete sections and KPIs for this cycle.
    Also shows the list of staff to be evaluated.
    """
    cycle = get_object_or_404(PerformanceCycle, pk=cycle_id)
    sections = cycle.sections.prefetch_related('kpis').all()

    teacher_weight = cycle.total_weight_for_role(KPISection.RoleType.TEACHER)
    coord_weight = cycle.total_weight_for_role(KPISection.RoleType.COORDINATOR)

    teachers, coordinators = get_staff_for_cycle(cycle)

    # Fetch evaluations for quick status display
    eval_map = {
        e.staff_id: e
        for e in StaffEvaluation.objects.filter(cycle=cycle).select_related('staff')
    }

    teacher_rows = [{'user': t, 'eval': eval_map.get(t.id)} for t in teachers]
    coord_rows = [{'user': c, 'eval': eval_map.get(c.id)} for c in coordinators]

    context = {
        'cycle': cycle,
        'sections': sections,
        'teacher_weight': teacher_weight,
        'coord_weight': coord_weight,
        'teacher_rows': teacher_rows,
        'coord_rows': coord_rows,
        'role_choices': KPISection.RoleType.choices,
        'is_editable': cycle.status == PerformanceCycle.Status.DRAFT,
    }
    return render(request, 'performance/cycle_detail.html', context)


@login_required
@role_required(User.Role.ADMIN)
@require_POST
def cycle_activate(request, cycle_id):
    """Activate a cycle — validates weights first, then freezes the KPI structure."""
    cycle = get_object_or_404(PerformanceCycle, pk=cycle_id)

    if cycle.status != PerformanceCycle.Status.DRAFT:
        messages.error(request, "Only draft cycles can be activated.")
        return redirect(reverse('performance_cycle_detail', args=[cycle.id]))

    errors = validate_cycle_weights(cycle)
    if errors:
        for role, total in errors.items():
            messages.error(
                request,
                f"{role.title()} KPI weights sum to {total}% — must be exactly 100% to activate."
            )
        return redirect(reverse('performance_cycle_detail', args=[cycle.id]))

    cycle.status = PerformanceCycle.Status.ACTIVE
    cycle.save()
    messages.success(request, f"Cycle '{cycle.name}' is now active. KPI structure is locked.")
    return redirect(reverse('performance_cycle_detail', args=[cycle.id]))


@login_required
@role_required(User.Role.ADMIN)
@require_POST
def cycle_close(request, cycle_id):
    """Close a cycle — no more evaluations can be submitted."""
    cycle = get_object_or_404(PerformanceCycle, pk=cycle_id)
    cycle.status = PerformanceCycle.Status.CLOSED
    cycle.save()
    messages.success(request, f"Cycle '{cycle.name}' has been closed.")
    return redirect(reverse('performance_cycle_list'))


# ─── ADMIN: KPI Builder ────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
@require_POST
def kpi_section_add(request, cycle_id):
    """Add a KPI section to a cycle."""
    cycle = get_object_or_404(PerformanceCycle, pk=cycle_id)

    if cycle.status != PerformanceCycle.Status.DRAFT:
        messages.error(request, "Cannot modify an active or closed cycle.")
        return redirect(reverse('performance_cycle_detail', args=[cycle.id]))

    name = request.POST.get('section_name', '').strip()
    role_type = request.POST.get('role_type', '')
    order = request.POST.get('order', 0)

    if not name or role_type not in [r[0] for r in KPISection.RoleType.choices]:
        messages.error(request, "Section name and role type are required.")
    else:
        KPISection.objects.create(cycle=cycle, name=name, role_type=role_type, order=order)
        messages.success(request, f"Section '{name}' added.")

    return redirect(reverse('performance_cycle_detail', args=[cycle.id]))


@login_required
@role_required(User.Role.ADMIN)
@require_POST
def kpi_section_delete(request, section_id):
    """Delete a KPI section and all its KPIs."""
    section = get_object_or_404(KPISection, pk=section_id)
    cycle_id = section.cycle_id

    if section.cycle.status != PerformanceCycle.Status.DRAFT:
        messages.error(request, "Cannot modify an active or closed cycle.")
    else:
        section.delete()
        messages.success(request, "Section deleted.")

    return redirect(reverse('performance_cycle_detail', args=[cycle_id]))


@login_required
@role_required(User.Role.ADMIN)
@require_POST
def kpi_add(request, section_id):
    """Add a KPI to a section."""
    section = get_object_or_404(KPISection, pk=section_id)
    cycle_id = section.cycle_id

    if section.cycle.status != PerformanceCycle.Status.DRAFT:
        messages.error(request, "Cannot modify an active or closed cycle.")
        return redirect(reverse('performance_cycle_detail', args=[cycle_id]))

    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    data_source = request.POST.get('data_source', '').strip()
    max_weight_raw = request.POST.get('max_weight', '').strip()
    order = request.POST.get('order', 0)

    if not title or not data_source or not max_weight_raw:
        messages.error(request, "Title, data source, and weight are required.")
    else:
        try:
            max_weight = Decimal(max_weight_raw)
            if max_weight <= 0:
                raise ValueError
        except Exception:
            messages.error(request, "Weight must be a positive number.")
            return redirect(reverse('performance_cycle_detail', args=[cycle_id]))

        KPI.objects.create(
            section=section,
            title=title,
            description=description,
            data_source=data_source,
            max_weight=max_weight,
            order=order,
        )
        messages.success(request, f"KPI '{title}' added ({max_weight}%).")

    return redirect(reverse('performance_cycle_detail', args=[cycle_id]))


@login_required
@role_required(User.Role.ADMIN)
@require_POST
def kpi_delete(request, kpi_id):
    """Delete a KPI."""
    kpi = get_object_or_404(KPI, pk=kpi_id)
    cycle_id = kpi.section.cycle_id

    if kpi.section.cycle.status != PerformanceCycle.Status.DRAFT:
        messages.error(request, "Cannot modify an active or closed cycle.")
    else:
        kpi.delete()
        messages.success(request, "KPI deleted.")

    return redirect(reverse('performance_cycle_detail', args=[cycle_id]))


# ─── ADMIN: Evaluate Staff ─────────────────────────────────────────────────────

@login_required
def evaluate_staff(request, cycle_id, staff_id):
    """
    Score form for a specific staff member.
    Admin can evaluate anyone.
    Coordinators can only evaluate regular teachers (not other coordinators).
    """
    cycle = get_object_or_404(PerformanceCycle, pk=cycle_id)
    staff = get_object_or_404(User, pk=staff_id)

    # Access control: admin can evaluate anyone;
    # coordinators can only evaluate regular teachers (not other coordinators or admins).
    viewer_is_coordinator = (
        request.user.role == User.Role.TEACHER and
        TeacherProfile.objects.filter(user=request.user, is_coordinator=True).exists()
    )
    viewer_is_admin = request.user.role == User.Role.ADMIN

    if not viewer_is_admin and not viewer_is_coordinator:
        messages.error(request, "Access denied.")
        return redirect(reverse('dashboard_router'))

    staff_is_coordinator = TeacherProfile.objects.filter(user=staff, is_coordinator=True).exists()
    if viewer_is_coordinator and (staff.role != User.Role.TEACHER or staff_is_coordinator):
        messages.error(request, "Coordinators can only evaluate regular teachers.")
        return redirect(reverse('performance_cycle_detail', args=[cycle_id]))

    if cycle.status == PerformanceCycle.Status.DRAFT:
        return redirect(reverse('performance_cycle_detail', args=[cycle.id]))

    # Determine role_type for this staff member
    is_coordinator = TeacherProfile.objects.filter(user=staff, is_coordinator=True).exists()
    role_type = KPISection.RoleType.COORDINATOR if is_coordinator else KPISection.RoleType.TEACHER

    evaluation, _ = StaffEvaluation.objects.get_or_create(
        cycle=cycle,
        staff=staff,
        defaults={'evaluated_by': request.user, 'role_type': role_type}
    )

    # Ensure evaluator is set if it was just retrieved without one
    if not evaluation.evaluated_by:
        evaluation.evaluated_by = request.user
        evaluation.save(update_fields=['evaluated_by'])

    if request.method == 'POST':
        if cycle.status == PerformanceCycle.Status.CLOSED:
            messages.error(request, "This cycle is closed. No changes can be made.")
            return redirect(reverse('performance_evaluate', args=[cycle.id, staff.id]))

        action = request.POST.get('action', 'save')
        overall_comment = request.POST.get('overall_comment', '').strip()

        saved_count, errors = save_evaluation_scores(evaluation, request.POST)

        for err in errors:
            messages.warning(request, err)

        # Recalculate final score
        evaluation.overall_comment = overall_comment
        evaluation.evaluated_by = request.user

        if action == 'submit':
            evaluation.status = StaffEvaluation.Status.SUBMITTED
            evaluation.submitted_at = timezone.now()
            final = calculate_final_score(evaluation)
            evaluation.final_score = final

        evaluation.save()
        messages.success(request, f"Evaluation {'submitted' if action == 'submit' else 'saved as draft'} for {staff.get_full_name() or staff.username}.")

        if action == 'submit':
            return redirect(reverse('performance_cycle_detail', args=[cycle.id]))

    # Build context: group KPIs by section with existing scores
    sections = cycle.sections.filter(role_type=role_type).prefetch_related('kpis')
    score_map = {ks.kpi_id: ks for ks in evaluation.kpi_scores.select_related('kpi').all()}

    section_data = []
    for section in sections:
        kpi_rows = []
        for kpi in section.kpis.all():
            ks = score_map.get(kpi.id)
            kpi_rows.append({
                'kpi': kpi,
                'score': ks.score if ks else '',
                'comment': ks.comment if ks else '',
            })
        section_data.append({'section': section, 'kpis': kpi_rows})

    # Live total from saved scores
    current_score = calculate_final_score(evaluation)

    context = {
        'cycle': cycle,
        'staff': staff,
        'evaluation': evaluation,
        'section_data': section_data,
        'role_type': role_type,
        'current_score': current_score,
        'grade_info': get_performance_grade(current_score),
        'is_closed': cycle.status == PerformanceCycle.Status.CLOSED,
    }
    return render(request, 'performance/evaluate.html', context)


# ─── Report Views ─────────────────────────────────────────────────────────────

@login_required
def report_html(request, cycle_id, staff_id):
    """Print-ready HTML report."""
    cycle = get_object_or_404(PerformanceCycle, pk=cycle_id)
    staff = get_object_or_404(User, pk=staff_id)

    # Access control: admin sees all; staff sees only their own
    if request.user.role != User.Role.ADMIN and request.user.id != staff_id:
        messages.error(request, "Access denied.")
        return redirect(reverse('dashboard_router'))

    evaluation = get_object_or_404(StaffEvaluation, cycle=cycle, staff=staff)

    sections = cycle.sections.filter(role_type=evaluation.role_type).prefetch_related('kpis')
    score_map = {ks.kpi_id: ks for ks in evaluation.kpi_scores.select_related('kpi').all()}

    section_data = []
    for section in sections:
        kpi_rows = []
        section_max = Decimal('0')
        section_earned = Decimal('0')
        for kpi in section.kpis.all():
            ks = score_map.get(kpi.id)
            score = ks.score if ks else Decimal('0')
            earned = (score * kpi.max_weight) / Decimal('100')
            section_max += kpi.max_weight
            section_earned += earned
            kpi_rows.append({
                'kpi': kpi,
                'score': score,
                'earned': round(earned, 2),
                'comment': ks.comment if ks else '',
            })
        section_data.append({
            'section': section,
            'kpis': kpi_rows,
            'section_max': section_max,
            'section_earned': round(section_earned, 2),
        })

    grade_info = get_performance_grade(evaluation.final_score)

    context = {
        'cycle': cycle,
        'staff': staff,
        'evaluation': evaluation,
        'section_data': section_data,
        'grade_info': grade_info,
        'now': timezone.now(),
    }
    return render(request, 'performance/report_print.html', context)


@login_required
def report_pdf(request, cycle_id, staff_id):
    """Download PDF performance report."""
    cycle = get_object_or_404(PerformanceCycle, pk=cycle_id)
    staff = get_object_or_404(User, pk=staff_id)

    if request.user.role != User.Role.ADMIN and request.user.id != staff_id:
        messages.error(request, "Access denied.")
        return redirect(reverse('dashboard_router'))

    evaluation = get_object_or_404(StaffEvaluation, cycle=cycle, staff=staff)

    try:
        from .pdf_utils import generate_performance_report_pdf
        buffer = generate_performance_report_pdf(evaluation)
        filename = f"performance_{staff.username}_{cycle.id}.pdf"
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        logger.error(f"PDF generation failed for evaluation {evaluation.id}: {e}", exc_info=True)
        messages.error(request, f"PDF generation failed: {e}")
        return redirect(reverse('performance_report_html', args=[cycle.id, staff.id]))


# ─── Staff: Self-View ──────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.TEACHER)
def my_evaluations(request):
    """Teacher/Coordinator views their own evaluation history."""
    evaluations = StaffEvaluation.objects.filter(
        staff=request.user
    ).select_related('cycle').order_by('-cycle__start_date')

    eval_data = []
    for ev in evaluations:
        eval_data.append({
            'evaluation': ev,
            'grade_info': get_performance_grade(ev.final_score),
        })

    return render(request, 'performance/my_evaluations.html', {'eval_data': eval_data})
