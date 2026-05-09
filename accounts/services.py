from accounts.models import User
from academics.models import Section
from students.models import StudentProfile, ParentProfile
from django.core.mail import send_mail
from django.conf import settings as django_settings

def send_credential_email(email, username, password, name, role, section=None):
    """Send login credentials to a user via email."""
    if not email:
        return  # Skip if no email provided
    section_str = str(section) if section else 'Not Assigned'
    subject = f'SMS Pro — Your {role} Account Credentials'
    message = (
        f"Dear {name},\n\n"
        f"Your {role} account has been created at SMS Pro School Management System.\n\n"
        f"Login Credentials:\n"
        f"  Username: {username}\n"
        f"  Password: {password}\n"
        f"  Section: {section_str}\n\n"
        f"Login URL: http://127.0.0.1:8000/login/\n\n"
        f"Please change your password after first login.\n\n"
        f"Regards,\nSMS Pro Administration"
    )
    try:
        send_mail(subject, message, django_settings.DEFAULT_FROM_EMAIL, [email])
    except Exception:
        pass  # Silently fail in dev

def create_student_with_parent(username, password, first_name, last_name, section_id, student_email, parent_email, roll_number):
    """
    Creates a Student User, StudentProfile, Parent User, ParentProfile, links them,
    and sends emails to both.
    """
    user = User.objects.create_user(
        username=username, password=password,
        first_name=first_name, last_name=last_name,
        role=User.Role.STUDENT, email=student_email
    )

    section = Section.objects.filter(id=section_id).first() if section_id else None
    StudentProfile.objects.create(user=user, section=section, roll_number=roll_number)

    # Auto-create parent account
    parent_username = f"parent_{username}"
    parent_password = f"parent{password}"
    parent_user = User.objects.create_user(
        username=parent_username, password=parent_password,
        first_name=f"Parent of {first_name}", last_name=last_name,
        role=User.Role.PARENT, email=parent_email
    )
    parent_profile = ParentProfile.objects.create(user=parent_user)
    parent_profile.children.add(user)

    # Send credential emails
    send_credential_email(
        student_email or '', username, password,
        f"{first_name} {last_name}".strip() or username,
        'Student', section
    )
    send_credential_email(
        parent_email or '', parent_username, parent_password,
        f"Parent of {first_name} {last_name}".strip(),
        'Parent', section
    )
    
    return user, parent_user, section
