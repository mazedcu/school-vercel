import logging
from django.db import transaction
from accounts.models import User
from academics.models import Section
from students.models import StudentProfile, ParentProfile
from django.core.mail import send_mail
from django.conf import settings as django_settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
import secrets
import string

logger = logging.getLogger(__name__)


def _generate_password(length=10):
    """Generate a random password for auto-created parent accounts."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _build_password_reset_url(user):
    """
    Build a one-time password-reset URL for the given user.
    The link is valid for PASSWORD_RESET_TIMEOUT seconds (default 3 days).
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    base = django_settings.LOGIN_URL_FULL.rstrip('/')
    # Strip the /login/ suffix to get the site root
    if base.endswith('/login'):
        base = base[:-6]
    return f"{base}/reset/{uid}/{token}/"


def send_credential_email(email, user, password, role, section=None):
    """
    Send account-confirmation email with a secure password-set link.

    The plaintext password is NEVER included in the email — instead the user
    receives a one-time password-reset URL that lets them choose their own
    password. This prevents credential exposure if the email is intercepted
    or stored by a mail provider.

    Args:
        email:    Recipient address.
        user:     The newly created User instance.
        password: Accepted for API compatibility but intentionally NOT used.
        role:     Human-readable role name for the email body.
        section:  Optional Section instance for display purposes.
    """
    if not email:
        return  # Skip if no email provided

    name = user.get_full_name() or user.username
    section_str = str(section) if section else 'Not Assigned'
    reset_url = _build_password_reset_url(user)

    subject = f'OpDevSM — Account Created (User ID: {user.id})'
    message = (
        f"Dear {name},\n\n"
        f"Your {role} account has been created at OpDevSM School Management System.\n\n"
        f"═══════════════════════════════════\n"
        f"  Account Details\n"
        f"═══════════════════════════════════\n"
        f"  User ID  : {user.id}\n"
        f"  Username : {user.username}\n"
        f"  Role     : {role}\n"
        f"  Section  : {section_str}\n"
        f"═══════════════════════════════════\n\n"
        f"To set your password and access the system, click the link below:\n"
        f"{reset_url}\n\n"
        f"This link is valid for 3 days. After that, use 'Forgot Password'\n"
        f"on the login page to request a new link.\n\n"
        f"Login page: {django_settings.LOGIN_URL_FULL}\n\n"
        f"Regards,\nOpDevSM Administration"
    )
    try:
        send_mail(subject, message, django_settings.DEFAULT_FROM_EMAIL, [email])
    except Exception as exc:
        logger.warning(
            "Credential email to %s failed (role=%s): %s",
            email, role, exc, exc_info=True
        )
        # Swallow the error — account is created; admin can resend manually




def create_student_with_parent(
    username, password, first_name, last_name, section_id,
    student_email, parent_email, roll_number, parent_username,
    parent_password=None
):
    """
    Creates a Student User, StudentProfile, links to existing or new Parent,
    and sends confirmation emails with User IDs to both.
    """
    # Wrap DB operations in a transaction — if parent creation fails,
    # the student won't be orphaned.
    with transaction.atomic():
        # ── Create the student user ──────────────────────────────────────
        user = User.objects.create_user(
            username=username, password=password,
            first_name=first_name, last_name=last_name,
            role=User.Role.STUDENT, email=student_email
        )

        section = Section.objects.filter(id=section_id).first() if section_id else None
        StudentProfile.objects.create(user=user, section=section, roll_number=roll_number)

        # ── Link or create parent ────────────────────────────────────────
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

    # ── Send confirmation emails (outside transaction — email failure shouldn't roll back DB)
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
