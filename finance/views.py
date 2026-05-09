from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.utils import timezone
from decimal import Decimal
import datetime

from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from students.models import StudentProfile, ParentProfile
from timetable.models import TimeSlot, TimetableEntry
from timetable.services import generate_timetable_entry
from timetable.pdf_utils import generate_section_timetable_pdf, generate_teacher_timetable_pdf
from attendance.models import Attendance
from exams.models import AssessmentType, SubjectWeighting, WeightingComponent, AssessmentRecord, StudentScore, GradeSetting, SubjectComment
from finance.models import FeeStructure, Invoice, Payment



@login_required
@role_required(User.Role.ADMIN)
def manage_finance(request):

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_fee':
            class_group_id = request.POST.get('class_group')
            name = request.POST.get('fee_name', '').strip()
            amount = request.POST.get('amount', '0')
            academic_year = request.POST.get('academic_year', '2026')
            try:
                cg = ClassGroup.objects.get(id=class_group_id)
                FeeStructure.objects.create(class_group=cg, name=name, amount=Decimal(amount), academic_year=academic_year)
                messages.success(request, f"Fee '{name}' created for {cg.name}.")
            except Exception as e:
                messages.error(request, str(e))

        elif action == 'issue_invoice':
            student_id = request.POST.get('student')
            fee_id = request.POST.get('fee_structure')
            due_date = request.POST.get('due_date')
            try:
                student = User.objects.get(id=student_id, role=User.Role.STUDENT)
                fee = FeeStructure.objects.get(id=fee_id)
                Invoice.objects.create(student=student, fee_structure=fee, amount_due=fee.amount, due_date=due_date)
                messages.success(request, f"Invoice issued to {student.username} for Rs.{fee.amount}.")
            except Exception as e:
                messages.error(request, str(e))

        elif action == 'record_payment':
            invoice_id = request.POST.get('invoice')
            pay_amount = request.POST.get('pay_amount', '0')
            method = request.POST.get('method', 'cash')
            try:
                inv = Invoice.objects.get(id=invoice_id)
                Payment.objects.create(invoice=inv, amount=Decimal(pay_amount), method=method)
                messages.success(request, f"Payment of Rs.{pay_amount} recorded for Invoice #{inv.pk}.")
            except Exception as e:
                messages.error(request, str(e))

        return redirect('manage_finance')

    fee_structures = FeeStructure.objects.all().select_related('class_group')
    invoices = Invoice.objects.all().select_related('student', 'fee_structure').order_by('-issued_date')
    class_groups = ClassGroup.objects.all()
    students = User.objects.filter(role=User.Role.STUDENT)

    context = {
        'fee_structures': fee_structures,
        'invoices': invoices,
        'class_groups': class_groups,
        'students': students,
    }
    return render(request, 'dashboard/manage_finance.html', context)