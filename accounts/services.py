from accounts.models import User
from academics.models import Section
from students.models import StudentProfile, ParentProfile
from django.core.mail import send_mail
from django.conf import settings as django_settings
import secrets
import string


def _generate_password(length=10):
    """Generate a random password for auto-created parent accounts."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def send_credential_email(email, user, password, role, section=None):
    """Send login credentials + confirmation with User ID to a user via email."""
    if not email:
        return  # Skip if no email provided
    name = user.get_full_name() or user.username
    section_str = str(section) if section else 'Not Assigned'
    subject = f'OpDevSM — Account Confirmation (User ID: {user.id})'
    message = (
        f"Dear {name},\n\n"
        f"Your {role} account has been created at OpDevSM School Management System.\n\n"
        f"═══════════════════════════════════\n"
        f"  Account Confirmation Details\n"
        f"═══════════════════════════════════\n"
        f"  User ID  : {user.id}\n"
        f"  Username : {user.username}\n"
        f"  Password : {password}\n"
        f"  Role     : {role}\n"
        f"  Section  : {section_str}\n"
        f"═══════════════════════════════════\n\n"
        f"Login URL: {django_settings.LOGIN_URL_FULL}\n\n"
        f"Please change your password after first login.\n\n"
        f"Regards,\nOpDevSM Administration"
    )
    try:
        send_mail(subject, message, django_settings.DEFAULT_FROM_EMAIL, [email])
    except Exception:
        pass  # Silently fail in dev


def create_student_with_parent(
    username, password, first_name, last_name, section_id,
    student_email, parent_email, roll_number, parent_username,
    parent_password=None
):
    """
    Creates a Student User, StudentProfile, links to existing or new Parent,
    and sends confirmation emails with User IDs to both.
    """
    # ── Create the student user ──────────────────────────────────────────
    user = User.objects.create_user(
        username=username, password=password,
        first_name=first_name, last_name=last_name,
        role=User.Role.STUDENT, email=student_email
    )

    section = Section.objects.filter(id=section_id).first() if section_id else None
    StudentProfile.objects.create(user=user, section=section, roll_number=roll_number)

    # ── Link or create parent ────────────────────────────────────────────
    actual_parent_password = None
    existing_parent = User.objects.filter(username=parent_username).first()

    if existing_parent:
        # Parent user already exists — just link the child
        parent_user = existing_parent
        parent_profile, _ = ParentProfile.objects.get_or_create(user=parent_user)
        parent_profile.children.add(user)
        actual_parent_password = None  # don't send credentials for existing parent
    else:
        # Create a new parent account
        actual_parent_password = parent_password if parent_password else _generate_password()
        parent_user = User.objects.create_user(
            username=parent_username, password=actual_parent_password,
            first_name=f"Parent of {first_name}", last_name=last_name,
            role=User.Role.PARENT, email=parent_email
        )
        parent_profile = ParentProfile.objects.create(user=parent_user)
        parent_profile.children.add(user)

    # ── Send confirmation emails ─────────────────────────────────────────
    send_credential_email(
        student_email, user, password,
        'Student', section
    )
    if actual_parent_password:
        # Only send credentials for newly created parent
        send_credential_email(
            parent_email, parent_user, actual_parent_password,
            'Parent', section
        )

    return user, parent_user, section, (existing_parent is not None)
