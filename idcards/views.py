from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from accounts.decorators import role_required
from accounts.models import User
from academics.models import Section
from students.models import StudentProfile, TeacherProfile
from .pdf_utils import generate_student_id_card, generate_teacher_id_card, generate_bulk_student_cards


@login_required
@role_required(User.Role.ADMIN)
def idcard_dashboard(request):
    """Admin dashboard for ID card management."""
    sections = Section.objects.select_related('class_group').order_by('class_group__name', 'name')
    teachers = User.objects.filter(role=User.Role.TEACHER).order_by('first_name', 'last_name')

    teacher_data = []
    for t in teachers:
        profile = getattr(t, 'teacher_profile', None)
        teacher_data.append({'user': t, 'profile': profile})

    context = {
        'sections': sections,
        'teacher_data': teacher_data,
    }
    return render(request, 'dashboard/idcard_dashboard.html', context)


@login_required
@role_required(User.Role.ADMIN)
def student_id_card_pdf(request, student_id):
    """Return a single student's ID card as a PDF download."""
    student = get_object_or_404(User, pk=student_id, role=User.Role.STUDENT)
    buf = generate_student_id_card(student)
    slug = (student.get_full_name() or student.username).replace(' ', '_')
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="idcard_{slug}.pdf"'
    return response


@login_required
@role_required(User.Role.ADMIN)
def teacher_id_card_pdf(request, teacher_id):
    """Return a single teacher's ID card as a PDF download."""
    teacher = get_object_or_404(User, pk=teacher_id, role=User.Role.TEACHER)
    buf = generate_teacher_id_card(teacher)
    slug = (teacher.get_full_name() or teacher.username).replace(' ', '_')
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="idcard_{slug}.pdf"'
    return response


@login_required
@role_required(User.Role.ADMIN)
def bulk_student_id_cards(request, section_id):
    """Return all student ID cards for a section as one printable PDF."""
    section = get_object_or_404(Section, pk=section_id)
    buf = generate_bulk_student_cards(section)
    slug = f"{section.class_group.name}_{section.name}".replace(' ', '_')
    response = HttpResponse(buf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="idcards_bulk_{slug}.pdf"'
    return response
