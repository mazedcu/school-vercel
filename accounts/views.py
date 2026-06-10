import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordResetView
from django.contrib.auth.forms import PasswordResetForm
from django.contrib import messages
from accounts.decorators import role_required
from accounts.models import User
from academics.models import Section
from students.models import ParentProfile
from .services import create_student_with_parent, send_credential_email

logger = logging.getLogger(__name__)


# ── Safe Password Reset (catches SMTP errors at EVERY level) ─────────────────

class SafePasswordResetForm(PasswordResetForm):
    """Catches SMTP errors at the lowest level — inside send_mail()."""

    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        try:
            super().send_mail(
                subject_template_name, email_template_name,
                context, from_email, to_email,
                html_email_template_name=html_email_template_name,
            )
        except Exception as exc:
            logger.error(
                "Password-reset email to %s failed: %s", to_email, exc,
                exc_info=True,
            )
            # Swallow the error — the user still sees the "check your inbox" page


class SafePasswordResetView(PasswordResetView):
    """
    Uses SafePasswordResetForm so SMTP failures never crash the page.
    Also has a belt-and-suspenders try/except around form_valid().
    """
    form_class = SafePasswordResetForm

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except Exception as exc:
            logger.error("Password-reset view failed: %s", exc, exc_info=True)
            return redirect('password_reset_done')


@login_required
@role_required(User.Role.ADMIN)
def manage_users(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'create_user')

        if action == 'delete_user':
            uid = request.POST.get('user_id')
            target = get_object_or_404(User, pk=uid)
            if target == request.user:
                messages.error(request, "You cannot delete your own account.")
            elif target.role == User.Role.ADMIN:
                messages.error(request, "Cannot delete the Admin/Principal account.")
            elif target.is_deleted:
                messages.error(request, "User is already in the recycle bin.")
            else:
                uname = target.username
                target.soft_delete()
                messages.success(request, f"User '{uname}' moved to the recycle bin. You can restore or permanently delete from Recycle Bin.")
            return redirect('manage_users')

        # ── Create a new user ────────────────────────────────────────────────
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', User.Role.STUDENT)
        section_id = request.POST.get('section', '')
        student_email = request.POST.get('student_email', '').strip()
        parent_email = request.POST.get('parent_email', '').strip()
        roll_number = request.POST.get('roll_number', '').strip()
        parent_username = request.POST.get('parent_username', '').strip()

        # ── Validation ───────────────────────────────────────────────────────
        if not username or not password:
            messages.error(request, "Username and password are required.")
        elif not first_name:
            messages.error(request, "First name is required.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
        elif role == User.Role.ADMIN:
            # Block creation of additional admin accounts
            messages.error(request, "Only one Admin/Principal account is allowed. Cannot create another admin.")
        else:
            if role == User.Role.STUDENT:
                # Validate mandatory student fields
                if not student_email:
                    messages.error(request, "Student email is required.")
                elif not parent_username:
                    messages.error(request, "Parent username is required.")
                elif not parent_email:
                    messages.error(request, "Guardian/Parent email is required.")
                else:
                    # Check: if parent_username is same as student username
                    if parent_username == username:
                        messages.error(request, "Parent username cannot be the same as the student username.")
                    else:
                        # Check: if parent_username exists but is NOT a parent role
                        existing = User.objects.filter(username=parent_username).first()
                        if existing and existing.role != User.Role.PARENT:
                            messages.error(request, f"Username '{parent_username}' already exists as a {existing.get_role_display()}, not a parent.")
                        else:
                            parent_password = request.POST.get('parent_password', '').strip() or None
                            user, parent_user, section, parent_existed = create_student_with_parent(
                                username, password, first_name, last_name, section_id,
                                student_email, parent_email, roll_number, parent_username,
                                parent_password=parent_password
                            )
                            section_name = section if section else "Unassigned"
                            if parent_existed:
                                messages.success(request, f"Student '{username}' (ID: {user.id}) created in {section_name}. Linked to existing parent '{parent_user.username}'. Confirmation email sent to student.")
                            else:
                                messages.success(request, f"Student '{username}' (ID: {user.id}) created in {section_name}. Parent account '{parent_user.username}' (ID: {parent_user.id}) auto-created. Confirmation emails sent.")
            elif role == User.Role.TEACHER:
                if not student_email:
                    messages.error(request, "Email address is required.")
                else:
                    user = User.objects.create_user(
                        username=username, password=password,
                        first_name=first_name, last_name=last_name,
                        role=role, email=student_email
                    )
                    # Send confirmation email with user ID
                    send_credential_email(student_email, user, password, 'Teacher')
                    messages.success(request, f"Teacher '{username}' (ID: {user.id}) created. Confirmation email sent.")
            else:
                user = User.objects.create_user(
                    username=username, password=password,
                    first_name=first_name, last_name=last_name,
                    role=role, email=student_email
                )
                # Send confirmation email with user ID
                send_credential_email(student_email, user, password, user.get_role_display())
                messages.success(request, f"User '{username}' (ID: {user.id}) created as {user.get_role_display()}. Confirmation email sent.")

        return redirect('manage_users')

    from django.core.paginator import Paginator

    # Fetch active (non-deleted) users
    users_qs = User.objects.filter(is_deleted=False).prefetch_related('parent_profile__children', 'parents__user').all().order_by('role', 'username')
    
    paginator = Paginator(users_qs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    sections = Section.objects.select_related('class_group').all()

    # Build user data with parent connections
    user_data = []
    for u in page_obj:
        parent_of = ''
        child_of = ''
        if u.role == User.Role.PARENT:
            if hasattr(u, 'parent_profile'):
                parent_of = ", ".join([c.get_full_name() or c.username for c in u.parent_profile.children.all()])
        if u.role == User.Role.STUDENT:
            child_of = ", ".join([p.user.get_full_name() or p.user.username for p in u.parents.all()])
        user_data.append({'user': u, 'parent_of': parent_of, 'child_of': child_of})

    # Filter out admin and parent roles from role choices for the create form
    roles_for_create = [(val, label) for val, label in User.Role.choices if val not in [User.Role.ADMIN, User.Role.PARENT]]

    context = {
        'user_data': user_data,
        'page_obj': page_obj,
        'all_users': users_qs,
        'sections': sections,
        'roles': roles_for_create,
        'recycle_bin_count': User.objects.filter(is_deleted=True).count(),
    }
    return render(request, 'dashboard/manage_users.html', context)


@login_required
@role_required(User.Role.ADMIN)
def parent_profiles(request):
    """Admin: list all parents."""
    parents = User.objects.filter(role=User.Role.PARENT).prefetch_related(
        'parent_profile__children'
    ).order_by('username')
    
    parent_data = []
    for p in parents:
        profile = getattr(p, 'parent_profile', None)
        if not profile:
            profile = ParentProfile.objects.create(user=p)
        parent_data.append({
            'user': p,
            'children': profile.children.all()
        })
        
    context = {'parent_data': parent_data}
    return render(request, 'dashboard/parent_profiles.html', context)


@login_required
@role_required(User.Role.ADMIN)
def parent_profile_detail(request, parent_id):
    """Admin: edit parent profile."""
    parent = get_object_or_404(User, pk=parent_id, role=User.Role.PARENT)
    profile, _ = ParentProfile.objects.get_or_create(user=parent)
    
    if request.method == 'POST':
        new_username = request.POST.get('username', '').strip()
        if new_username and new_username != parent.username:
            if User.objects.filter(username=new_username).exists():
                messages.error(request, f"Username '{new_username}' is already taken.")
            else:
                parent.username = new_username

        parent.first_name = request.POST.get('first_name', '').strip()
        parent.last_name = request.POST.get('last_name', '').strip()
        parent.email = request.POST.get('email', '').strip()
        parent.phone = request.POST.get('phone', '').strip()
        parent.save()

        # Handle password change (admin only)
        new_password = request.POST.get('new_password', '').strip()
        if new_password:
            parent.set_password(new_password)
            parent.save()
            messages.info(request, f"Password for parent '{parent.username}' has been changed.")

        messages.success(request, f"Profile for parent '{parent.username}' updated.")
        return redirect('parent_profile_detail', parent_id=parent.id)
        
    context = {
        'parent': parent,
        'profile': profile,
        'children': profile.children.all()
    }
    return render(request, 'dashboard/parent_profile_detail.html', context)


# ── Recycle Bin ──────────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def recycle_bin(request):
    """List soft-deleted users and allow restore or permanent delete."""
    from django.core.paginator import Paginator

    deleted_users = User.objects.filter(is_deleted=True).order_by('-deleted_at')
    paginator = Paginator(deleted_users, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {'page_obj': page_obj, 'total': deleted_users.count()}
    return render(request, 'dashboard/recycle_bin.html', context)


@login_required
@role_required(User.Role.ADMIN)
def restore_user(request, user_id):
    """Restore a soft-deleted user from the recycle bin."""
    if request.method == 'POST':
        target = get_object_or_404(User, pk=user_id, is_deleted=True)
        target.restore()
        messages.success(request, f"User '{target.username}' has been restored successfully.")
    return redirect('recycle_bin')


@login_required
@role_required(User.Role.ADMIN)
def permanent_delete_user(request, user_id):
    """Permanently delete a user that is already in the recycle bin."""
    if request.method == 'POST':
        target = get_object_or_404(User, pk=user_id, is_deleted=True)
        if target == request.user:
            messages.error(request, "You cannot permanently delete your own account.")
        elif target.role == User.Role.ADMIN:
            messages.error(request, "Cannot permanently delete the Admin/Principal account.")
        else:
            uname = target.username
            target.delete()
            messages.success(request, f"User '{uname}' has been permanently deleted.")
    return redirect('recycle_bin')
