from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import role_required
from accounts.models import User
from academics.models import Section
from students.models import ParentProfile
from .services import create_student_with_parent

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
            else:
                uname = target.username
                target.delete()
                messages.success(request, f"User '{uname}' deleted.")
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

        if not username or not password:
            messages.error(request, "Username and password are required.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, f"Username '{username}' already exists.")
        else:
            if role == User.Role.STUDENT:
                user, parent_user, section = create_student_with_parent(
                    username, password, first_name, last_name, section_id,
                    student_email, parent_email, roll_number
                )
                section_name = section if section else "Unassigned"
                messages.success(request, f"Student '{username}' created in {section_name}. Parent account '{parent_user.username}' auto-created. Credential emails sent.")
            else:
                user = User.objects.create_user(
                    username=username, password=password,
                    first_name=first_name, last_name=last_name,
                    role=role, email=student_email
                )
                messages.success(request, f"User '{username}' created as {user.get_role_display()}.")

        return redirect('manage_users')

    users = User.objects.all().order_by('role', 'username')
    sections = Section.objects.select_related('class_group').all()

    # Build user data with parent connections
    user_data = []
    for u in users:
        parent_of = ''
        child_of = ''
        if u.role == User.Role.PARENT:
            pp = ParentProfile.objects.filter(user=u).first()
            if pp:
                parent_of = ", ".join([c.get_full_name() or c.username for c in pp.children.all()])
        if u.role == User.Role.STUDENT:
            parents = ParentProfile.objects.filter(children=u)
            child_of = ", ".join([p.user.get_full_name() or p.user.username for p in parents])
        user_data.append({'user': u, 'parent_of': parent_of, 'child_of': child_of})

    context = {
        'user_data': user_data,
        'all_users': users,
        'sections': sections,
        'roles': User.Role.choices,
    }
    return render(request, 'dashboard/manage_users.html', context)
