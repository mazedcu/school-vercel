from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Q

from accounts.models import User
from accounts.decorators import role_required
from academics.models import AcademicYear
from .models import LeaveType, LeavePolicy, LeaveApplication

def get_current_academic_year():
    """Get the active academic year."""
    active_year = AcademicYear.objects.filter(is_active=True).first()
    return active_year


def get_leave_balance(user, leave_type, academic_year):
    """Calculate remaining leave balance for a user for a specific AcademicYear."""
    if not academic_year:
        return 0, 0

    policy = LeavePolicy.objects.filter(leave_type=leave_type, academic_year=academic_year).first()
    if not policy:
        return 0, 0  # allocated, used

    # Calculate used days from approved applications within the academic year dates
    approved_apps = LeaveApplication.objects.filter(
        applicant=user,
        leave_type=leave_type,
        status=LeaveApplication.Status.ADMIN_APPROVED,
        start_date__gte=academic_year.start_date,
        start_date__lte=academic_year.end_date,
    )

    used_days = sum(app.total_days for app in approved_apps)
    return policy.allocated_days, used_days


# ─── ADMIN: LEAVE POLICY MANAGEMENT ──────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def leave_policy(request):
    """Admin: Create/manage leave types and policies."""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_type':
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            if name:
                LeaveType.objects.get_or_create(name=name, defaults={'description': description})
                messages.success(request, f"Leave type '{name}' created.")
            else:
                messages.error(request, "Leave type name is required.")

        elif action == 'delete_type':
            type_id = request.POST.get('type_id')
            lt = LeaveType.objects.filter(id=type_id).first()
            if lt:
                lt.delete()
                messages.success(request, "Leave type deleted.")

        elif action == 'save_policy':
            leave_type_id = request.POST.get('leave_type')
            academic_year_id = request.POST.get('academic_year')
            allocated_days = request.POST.get('allocated_days', '0')
            try:
                lt = LeaveType.objects.get(id=leave_type_id)
                ay = AcademicYear.objects.get(id=academic_year_id)
                obj, created = LeavePolicy.objects.update_or_create(
                    leave_type=lt, academic_year=ay,
                    defaults={'allocated_days': int(allocated_days)}
                )
                action_word = 'created' if created else 'updated'
                messages.success(request, f"Policy for {lt.name} ({ay.name}) {action_word}: {allocated_days} days.")
            except Exception as e:
                messages.error(request, str(e))

        elif action == 'delete_policy':
            policy_id = request.POST.get('policy_id')
            LeavePolicy.objects.filter(id=policy_id).delete()
            messages.success(request, "Policy deleted.")

        return redirect('leave_policy')

    leave_types = LeaveType.objects.all()
    policies = LeavePolicy.objects.select_related('leave_type', 'academic_year').all()
    academic_years = AcademicYear.objects.all()
    context = {
        'leave_types': leave_types,
        'policies': policies,
        'academic_years': academic_years,
    }
    return render(request, 'dashboard/leave_policy.html', context)


# ─── TEACHER: APPLY FOR LEAVE ────────────────────────────────────────────────

@login_required
@role_required(User.Role.TEACHER, User.Role.COORDINATOR)
def apply_leave(request):
    """Teacher/Coordinator: Submit a new leave application."""
    leave_types = LeaveType.objects.all()
    today = timezone.now().date()
    current_year = get_current_academic_year()

    if request.method == 'POST':
        leave_type_id = request.POST.get('leave_type')
        category = request.POST.get('category')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        reason = request.POST.get('reason', '').strip()

        try:
            lt = LeaveType.objects.get(id=leave_type_id)
            from datetime import datetime
            s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            e_date = datetime.strptime(end_date, '%Y-%m-%d').date()

            # Validation
            if e_date < s_date:
                raise ValueError("End date cannot be before start date.")
            if category == 'emergency' and s_date != today:
                raise ValueError("Emergency leave must start today.")
            if category == 'advance' and s_date <= today:
                raise ValueError("Advance leave must start on a future date.")

            # Check balance
            allocated, used = get_leave_balance(request.user, lt, current_year)
            requested_days = (e_date - s_date).days + 1
            remaining = allocated - used
            if remaining <= 0:
                raise ValueError(f"No remaining {lt.name} balance. Allocated: {allocated}, Used: {used}.")
            if requested_days > remaining:
                raise ValueError(f"Requested {requested_days} days but only {remaining} days remaining.")

            if not reason:
                raise ValueError("Please provide a reason for leave.")

            LeaveApplication.objects.create(
                applicant=request.user,
                leave_type=lt,
                category=category,
                start_date=s_date,
                end_date=e_date,
                reason=reason,
            )
            messages.success(request, f"Leave application submitted successfully! ({requested_days} day(s))")
            return redirect('my_leaves')

        except LeaveType.DoesNotExist:
            messages.error(request, "Invalid leave type.")
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"Error: {e}")

        return redirect('apply_leave')

    # Build balance info for the template
    balances = []
    for lt in leave_types:
        allocated, used = get_leave_balance(request.user, lt, current_year)
        balances.append({
            'type': lt,
            'allocated': allocated,
            'used': used,
            'remaining': allocated - used,
        })

    context = {
        'leave_types': leave_types,
        'balances': balances,
        'today': today.isoformat(),
    }
    return render(request, 'dashboard/apply_leave.html', context)


# ─── TEACHER: MY LEAVES ──────────────────────────────────────────────────────

@login_required
@role_required(User.Role.TEACHER, User.Role.COORDINATOR)
def my_leaves(request):
    """Teacher/Coordinator: View own leave balance and application history."""
    today = timezone.now().date()
    current_year = get_current_academic_year()
    leave_types = LeaveType.objects.all()

    balances = []
    for lt in leave_types:
        allocated, used = get_leave_balance(request.user, lt, current_year)
        balances.append({
            'type': lt,
            'allocated': allocated,
            'used': used,
            'remaining': allocated - used,
        })

    applications = LeaveApplication.objects.filter(applicant=request.user).select_related('leave_type')

    context = {
        'balances': balances,
        'applications': applications,
        'current_year': current_year,
    }
    return render(request, 'dashboard/my_leaves.html', context)


# ─── COORDINATOR: REVIEW PENDING APPLICATIONS ────────────────────────────────

@login_required
@role_required(User.Role.COORDINATOR, User.Role.ADMIN)
def coordinator_review(request):
    """Coordinator: Review and approve/reject pending leave applications."""
    if request.method == 'POST':
        app_id = request.POST.get('application_id')
        action = request.POST.get('action')
        remarks = request.POST.get('remarks', '').strip()

        application = get_object_or_404(LeaveApplication, id=app_id, status=LeaveApplication.Status.PENDING)

        if action == 'approve':
            application.status = LeaveApplication.Status.COORDINATOR_APPROVED
            application.coordinator_reviewed_by = request.user
            application.coordinator_reviewed_at = timezone.now()
            application.coordinator_remarks = remarks
            application.save()
            messages.success(request, f"Leave application by {application.applicant.get_full_name()} approved and forwarded to Admin.")
        elif action == 'reject':
            application.status = LeaveApplication.Status.REJECTED
            application.coordinator_reviewed_by = request.user
            application.coordinator_reviewed_at = timezone.now()
            application.coordinator_remarks = remarks
            application.save()
            messages.success(request, f"Leave application by {application.applicant.get_full_name()} rejected.")

        return redirect('coordinator_review')

    pending = LeaveApplication.objects.filter(
        status=LeaveApplication.Status.PENDING
    ).select_related('applicant', 'leave_type').order_by('-applied_at')

    context = {'pending_applications': pending}
    return render(request, 'dashboard/coordinator_review.html', context)


# ─── ADMIN: FINAL REVIEW ─────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def admin_leave_review(request):
    """Admin: Final approval/rejection of coordinator-approved leave applications."""
    if request.method == 'POST':
        app_id = request.POST.get('application_id')
        action = request.POST.get('action')
        remarks = request.POST.get('remarks', '').strip()

        application = get_object_or_404(
            LeaveApplication, id=app_id,
            status=LeaveApplication.Status.COORDINATOR_APPROVED
        )

        if action == 'approve':
            application.status = LeaveApplication.Status.ADMIN_APPROVED
            application.admin_reviewed_by = request.user
            application.admin_reviewed_at = timezone.now()
            application.admin_remarks = remarks
            application.save()
            messages.success(request, f"Leave for {application.applicant.get_full_name()} approved. Balance updated.")
        elif action == 'reject':
            application.status = LeaveApplication.Status.REJECTED
            application.admin_reviewed_by = request.user
            application.admin_reviewed_at = timezone.now()
            application.admin_remarks = remarks
            application.save()
            messages.success(request, f"Leave for {application.applicant.get_full_name()} rejected.")

        return redirect('admin_leave_review')

    # Show coordinator-approved applications waiting for admin
    awaiting = LeaveApplication.objects.filter(
        status=LeaveApplication.Status.COORDINATOR_APPROVED
    ).select_related('applicant', 'leave_type', 'coordinator_reviewed_by').order_by('-applied_at')

    # Also show recent admin decisions for reference
    recent_decisions = LeaveApplication.objects.filter(
        status__in=[LeaveApplication.Status.ADMIN_APPROVED, LeaveApplication.Status.REJECTED],
        admin_reviewed_by__isnull=False,
    ).select_related('applicant', 'leave_type').order_by('-admin_reviewed_at')[:20]

    # Build staff leave balance summary
    current_year = get_current_academic_year()
    leave_types = LeaveType.objects.all()
    staff = User.objects.filter(role__in=[User.Role.TEACHER, User.Role.COORDINATOR])
    staff_balances = []
    for user in staff:
        user_balances = []
        for lt in leave_types:
            allocated, used = get_leave_balance(user, lt, current_year)
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
        'awaiting_applications': awaiting,
        'recent_decisions': recent_decisions,
        'staff_balances': staff_balances,
        'leave_types': leave_types,
        'current_year': current_year,
    }
    return render(request, 'dashboard/admin_leave_review.html', context)
