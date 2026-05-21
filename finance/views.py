from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from accounts.decorators import role_required
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.utils import timezone
from decimal import Decimal
import datetime
import logging

logger = logging.getLogger(__name__)

from accounts.models import User
from academics.models import ClassGroup, Section, Subject
from students.models import StudentProfile, ParentProfile
from finance.models import FeeStructure, Invoice, InvoiceLineItem, Payment


@login_required
@role_required(User.Role.ADMIN, User.Role.ACCOUNTS)
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

        elif action == 'record_payment':
            invoice_id = request.POST.get('invoice')
            pay_amount = request.POST.get('pay_amount', '0')
            method = request.POST.get('method', 'cash')
            try:
                inv = Invoice.objects.get(id=invoice_id)
                Payment.objects.create(invoice=inv, amount=Decimal(pay_amount), method=method)
                messages.success(request, f"Payment of Tk.{pay_amount} recorded for Invoice {inv.invoice_number}.")
            except Exception as e:
                messages.error(request, str(e))

        elif action == 'bulk_invoice':
            bulk_class_id = request.POST.get('bulk_class_group')
            bulk_section_id = request.POST.get('bulk_section', '')
            bulk_student_id = request.POST.get('bulk_student', '')  # optional single student
            due_date = request.POST.get('bulk_due_date')
            discount_desc = request.POST.get('bulk_discount_description', '').strip()
            discount_amt = request.POST.get('bulk_discount_amount', '0')

            try:
                if not bulk_class_id:
                    messages.error(request, "Please select a class.")
                    return redirect('manage_finance')
                if not due_date:
                    messages.error(request, "Please set a due date.")
                    return redirect('manage_finance')

                class_group = ClassGroup.objects.get(id=bulk_class_id)

                # Collect fee items (up to 5)
                line_items_data = []
                for i in range(1, 6):
                    fee_id = request.POST.get(f'bulk_fee_structure_{i}')
                    if fee_id:
                        try:
                            fee = FeeStructure.objects.get(id=fee_id)
                            line_items_data.append({
                                'fee_structure': fee,
                                'description': fee.name,
                                'amount': fee.amount,
                            })
                        except FeeStructure.DoesNotExist:
                            pass

                if not line_items_data:
                    messages.error(request, "Please select at least one fee category.")
                    return redirect('manage_finance')

                # Determine target students
                if bulk_student_id:
                    # Single student mode
                    target_students = [User.objects.get(id=bulk_student_id, role=User.Role.STUDENT)]
                elif bulk_section_id:
                    student_profiles = StudentProfile.objects.filter(
                        section_id=bulk_section_id
                    ).select_related('user', 'section__class_group')
                    target_students = [sp.user for sp in student_profiles]
                else:
                    student_profiles = StudentProfile.objects.filter(
                        section__class_group=class_group
                    ).select_related('user', 'section__class_group')
                    target_students = [sp.user for sp in student_profiles]

                if not target_students:
                    messages.error(request, "No students found in the selected class/section.")
                    return redirect('manage_finance')

                # Calculate totals
                subtotal = sum(item['amount'] for item in line_items_data)
                discount = Decimal(discount_amt) if discount_amt else Decimal('0')
                amount_due = max(subtotal - discount, Decimal('0'))

                created_count = 0

                for student in target_students:
                    # Create invoice for this student
                    invoice = Invoice(
                        student=student,
                        class_group=class_group,
                        subtotal=subtotal,
                        discount_description=discount_desc,
                        discount_amount=discount,
                        amount_due=amount_due,
                        due_date=due_date,
                    )
                    invoice.save()

                    # Create line items
                    for item in line_items_data:
                        InvoiceLineItem.objects.create(
                            invoice=invoice,
                            fee_structure=item['fee_structure'],
                            description=item['description'],
                            amount=item['amount'],
                        )
                    created_count += 1

                fee_names = ', '.join([item['description'] for item in line_items_data])
                if created_count == 1:
                    student_name = target_students[0].get_full_name() or target_students[0].username
                    messages.success(
                        request,
                        f"✅ Invoice issued to {student_name} for '{fee_names}' — Tk.{amount_due}."
                    )
                else:
                    messages.success(
                        request,
                        f"✅ {created_count} invoice(s) issued for '{fee_names}' "
                        f"in {class_group.name} — Tk.{amount_due} each."
                    )
            except Exception as e:
                messages.error(request, f"Invoice error: {str(e)}")

        return redirect('manage_finance')

    fee_structures = FeeStructure.objects.all().select_related('class_group')
    invoices = Invoice.objects.all().select_related('student', 'class_group').prefetch_related('line_items').order_by('-issued_date')
    class_groups = ClassGroup.objects.all()
    students = User.objects.filter(role=User.Role.STUDENT)
    sections = Section.objects.select_related('class_group').all()

    context = {
        'fee_structures': fee_structures,
        'invoices': invoices,
        'class_groups': class_groups,
        'students': students,
        'sections': sections,
    }
    return render(request, 'dashboard/manage_finance.html', context)


@login_required
@role_required(User.Role.ADMIN, User.Role.ACCOUNTS)
def print_invoice(request, invoice_id):
    """Render a print-ready invoice page."""
    invoice = get_object_or_404(Invoice.objects.select_related('student', 'class_group').prefetch_related('line_items', 'payments'), id=invoice_id)
    balance = invoice.amount_due - invoice.amount_paid

    context = {
        'invoice': invoice,
        'line_items': invoice.line_items.all(),
        'payments': invoice.payments.all(),
        'balance': balance,
    }
    return render(request, 'dashboard/invoice_print.html', context)


@login_required
@role_required(User.Role.ADMIN, User.Role.ACCOUNTS)
@require_POST
def delete_invoice(request, invoice_id):
    """Delete an invoice (POST only)."""
    invoice = get_object_or_404(Invoice, id=invoice_id)
    inv_num = invoice.invoice_number
    try:
        invoice.delete()
        messages.success(request, f"Invoice {inv_num} deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting invoice: {str(e)}")
    return redirect('manage_finance')


@login_required
@role_required(User.Role.ADMIN, User.Role.ACCOUNTS)
def api_students_by_class(request):
    """Return students filtered by class group (JSON)."""
    class_group_id = request.GET.get('class_group_id')
    students = []
    if class_group_id:
        profiles = StudentProfile.objects.filter(
            section__class_group_id=class_group_id
        ).select_related('user')
        for p in profiles:
            students.append({
                'id': p.user.id,
                'name': p.user.get_full_name() or p.user.username,
                'roll': p.roll_number or '',
            })
    return JsonResponse({'students': students})


@login_required
@role_required(User.Role.ADMIN, User.Role.ACCOUNTS)
def api_invoices_by_class(request):
    """Return unpaid/partial invoices filtered by class group (JSON)."""
    class_group_id = request.GET.get('class_group_id')
    invoices = Invoice.objects.exclude(status=Invoice.Status.PAID).select_related('student', 'class_group')

    if class_group_id:
        invoices = invoices.filter(class_group_id=class_group_id)

    data = []
    for inv in invoices:
        data.append({
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'student': inv.student.get_full_name() or inv.student.username,
            'amount_due': str(inv.amount_due),
            'amount_paid': str(inv.amount_paid),
            'status': inv.get_status_display(),
        })
    return JsonResponse({'invoices': data})


@login_required
@role_required(User.Role.ADMIN, User.Role.ACCOUNTS)
def api_fees_by_class(request):
    """Return fee structures filtered by class group (JSON)."""
    class_group_id = request.GET.get('class_group_id')
    fees = []
    if class_group_id:
        fee_structures = FeeStructure.objects.filter(class_group_id=class_group_id)
        for f in fee_structures:
            fees.append({
                'id': f.id,
                'name': f"{f.name} ({f.class_group.name}) - Tk.{f.amount}",
                'amount': str(f.amount),
            })
    return JsonResponse({'fees': fees})


@login_required
@role_required(User.Role.ADMIN, User.Role.ACCOUNTS)
def api_students_by_section(request):
    """Return students filtered by section (JSON)."""
    section_id = request.GET.get('section_id')
    students = []
    if section_id:
        profiles = StudentProfile.objects.filter(
            section_id=section_id
        ).select_related('user')
        for p in profiles:
            students.append({
                'id': p.user.id,
                'name': p.user.get_full_name() or p.user.username,
                'roll': p.roll_number or '',
            })
    return JsonResponse({'students': students})