from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from accounts.decorators import role_required
from django.contrib import messages
from django.db.models import Sum, Q, ExpressionWrapper, F, DecimalField
from django.utils import timezone
from decimal import Decimal
import json
import datetime
import logging

from accounts.models import User
from finance.models import Invoice, Payment
from .models import Expense, PurchaseRequest, PurchaseOrder, InventoryItem, CapexItem

logger = logging.getLogger(__name__)


# ─── EXPENSE MANAGEMENT ──────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def manage_expenses(request):
    """Record and list expenses."""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_expense':
            try:
                Expense.objects.create(
                    date=request.POST.get('date', timezone.now().date()),
                    description=request.POST.get('description', '').strip(),
                    category=request.POST.get('category', 'other'),
                    amount=Decimal(request.POST.get('amount', '0')),
                    reference=request.POST.get('reference', '').strip(),
                    recorded_by=request.user,
                )
                messages.success(request, "Expense recorded successfully.")
            except Exception as e:
                logger.error("Failed to record expense: %s", e, exc_info=True)
                messages.error(request, str(e))

        elif action == 'delete_expense':
            eid = request.POST.get('expense_id')
            Expense.objects.filter(id=eid).delete()
            messages.success(request, "Expense deleted.")

        return redirect('manage_expenses')

    expenses = Expense.objects.all()[:100]
    context = {
        'expenses': expenses,
        'categories': Expense.Category.choices,
    }
    return render(request, 'procurement/manage_expenses.html', context)


# ─── ACCOUNT STATEMENT ───────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def account_statement(request):
    """Show income (payments) and expenses with time filters."""
    date_from = request.GET.get('from', '')
    date_to = request.GET.get('to', '')

    payments = Payment.objects.all().select_related('invoice', 'invoice__student')
    expenses = Expense.objects.all()

    if date_from:
        payments = payments.filter(payment_date__gte=date_from)
        expenses = expenses.filter(date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__lte=date_to)
        expenses = expenses.filter(date__lte=date_to)

    total_income = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    total_expenses = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    net_balance = total_income - total_expenses

    # Combined ledger entries sorted by date
    ledger = []
    for p in payments:
        ledger.append({
            'date': p.payment_date,
            'description': f"Payment from {p.invoice.student.get_full_name() or p.invoice.student.username} (Invoice {p.invoice.invoice_number})",
            'type': 'income',
            'amount': p.amount,
            'method': p.method,
        })
    for e in expenses:
        ledger.append({
            'date': e.date,
            'description': e.description,
            'type': 'expense',
            'amount': e.amount,
            'method': e.get_category_display(),
        })
    ledger.sort(key=lambda x: x['date'], reverse=True)

    context = {
        'ledger': ledger,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'net_balance': net_balance,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'procurement/account_statement.html', context)


# ─── PURCHASE REQUEST ────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER)
def purchase_requests(request):
    """Teachers and admins can create purchase requests. Admins see all."""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create_request':
            try:
                PurchaseRequest.objects.create(
                    requested_by=request.user,
                    title=request.POST.get('title', '').strip(),
                    items_detail=request.POST.get('items_detail', '').strip(),
                    item_type=request.POST.get('item_type', 'inventory'),
                    estimated_cost=Decimal(request.POST.get('estimated_cost', '0')),
                    justification=request.POST.get('justification', '').strip(),
                )
                messages.success(request, "Purchase request submitted successfully.")
            except Exception as e:
                messages.error(request, str(e))

        elif action == 'approve' and request.user.role == User.Role.ADMIN:
            pr_id = request.POST.get('pr_id')
            remarks = request.POST.get('admin_remarks', '').strip()
            pr = get_object_or_404(PurchaseRequest, id=pr_id)
            pr.status = PurchaseRequest.Status.APPROVED
            pr.admin_remarks = remarks
            pr.save()
            messages.success(request, f"Purchase request PR-{pr.pk:04d} approved.")

        elif action == 'reject' and request.user.role == User.Role.ADMIN:
            pr_id = request.POST.get('pr_id')
            remarks = request.POST.get('admin_remarks', '').strip()
            pr = get_object_or_404(PurchaseRequest, id=pr_id)
            pr.status = PurchaseRequest.Status.REJECTED
            pr.admin_remarks = remarks
            pr.save()
            messages.success(request, f"Purchase request PR-{pr.pk:04d} rejected.")

        elif action == 'create_po' and request.user.role == User.Role.ADMIN:
            pr_id = request.POST.get('pr_id')
            pr = get_object_or_404(PurchaseRequest, id=pr_id, status=PurchaseRequest.Status.APPROVED)
            po = PurchaseOrder.objects.create(
                purchase_request=pr,
                vendor_name=request.POST.get('vendor_name', '').strip(),
                vendor_contact=request.POST.get('vendor_contact', '').strip(),
                order_date=request.POST.get('order_date', timezone.now().date()),
                expected_delivery=request.POST.get('expected_delivery') or None,
                actual_cost=Decimal(request.POST.get('actual_cost', '0')),
                notes=request.POST.get('po_notes', '').strip(),
                created_by=request.user,
            )
            pr.status = PurchaseRequest.Status.ORDERED
            pr.save()
            messages.success(request, f"Purchase Order {po.po_number} created for PR-{pr.pk:04d}.")

        elif action == 'receive_po' and request.user.role == User.Role.ADMIN:
            po_id = request.POST.get('po_id')
            po = get_object_or_404(PurchaseOrder, id=po_id)
            po.is_received = True
            po.received_date = timezone.now().date()
            po.save()

            pr = po.purchase_request
            pr.status = PurchaseRequest.Status.RECEIVED
            pr.save()

            # Auto-create inventory or capex items
            if pr.item_type == PurchaseRequest.ItemType.CAPEX:
                CapexItem.objects.create(
                    name=pr.title,
                    description=pr.items_detail,
                    purchase_cost=po.actual_cost or pr.estimated_cost,
                    purchase_date=po.received_date,
                    purchase_order=po,
                )
                messages.success(request, f"PO {po.po_number} received. Capital asset added to CAPEX register.")
            else:
                InventoryItem.objects.create(
                    name=pr.title,
                    description=pr.items_detail,
                    quantity=1,
                    unit_cost=po.actual_cost or pr.estimated_cost,
                    purchase_order=po,
                )
                messages.success(request, f"PO {po.po_number} received. Item added to inventory.")

            # Auto-record as expense
            Expense.objects.create(
                date=po.received_date,
                description=f"Purchase: {pr.title} (PO: {po.po_number})",
                category=Expense.Category.CAPEX if pr.item_type == PurchaseRequest.ItemType.CAPEX else Expense.Category.SUPPLIES,
                amount=po.actual_cost or pr.estimated_cost,
                reference=po.po_number,
                recorded_by=request.user,
                purchase_order=po,
            )

        return redirect('purchase_requests')

    # Show requests based on role
    if request.user.role == User.Role.ADMIN:
        requests_list = PurchaseRequest.objects.all().select_related('requested_by')
    else:
        requests_list = PurchaseRequest.objects.filter(requested_by=request.user).select_related('requested_by')

    purchase_orders = PurchaseOrder.objects.all().select_related('purchase_request', 'purchase_request__requested_by')

    context = {
        'requests': requests_list,
        'purchase_orders': purchase_orders,
        'item_types': PurchaseRequest.ItemType.choices,
    }
    return render(request, 'procurement/purchase_requests.html', context)


# ─── INVENTORY & CAPEX ───────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def inventory_capex(request):
    """View and manage inventory and CAPEX items."""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_inventory':
            try:
                InventoryItem.objects.create(
                    name=request.POST.get('name', '').strip(),
                    description=request.POST.get('description', '').strip(),
                    category=request.POST.get('category', '').strip(),
                    quantity=int(request.POST.get('quantity', '1')),
                    unit=request.POST.get('unit', 'pcs').strip(),
                    unit_cost=Decimal(request.POST.get('unit_cost', '0')),
                    location=request.POST.get('location', '').strip(),
                )
                messages.success(request, "Inventory item added.")
            except Exception as e:
                messages.error(request, str(e))

        elif action == 'add_capex':
            try:
                CapexItem.objects.create(
                    name=request.POST.get('name', '').strip(),
                    description=request.POST.get('description', '').strip(),
                    category=request.POST.get('capex_category', '').strip(),
                    purchase_cost=Decimal(request.POST.get('purchase_cost', '0')),
                    purchase_date=request.POST.get('purchase_date', timezone.now().date()),
                    location=request.POST.get('location', '').strip(),
                    condition=request.POST.get('condition', 'new'),
                    useful_life_years=int(request.POST.get('useful_life_years', '5')),
                    notes=request.POST.get('notes', '').strip(),
                )
                messages.success(request, "Capital asset registered.")
            except Exception as e:
                messages.error(request, str(e))

        elif action == 'delete_inventory':
            InventoryItem.objects.filter(id=request.POST.get('item_id')).delete()
            messages.success(request, "Inventory item deleted.")

        elif action == 'delete_capex':
            CapexItem.objects.filter(id=request.POST.get('item_id')).delete()
            messages.success(request, "Capital asset deleted.")

        return redirect('inventory_capex')

    inventory_items = InventoryItem.objects.all()
    capex_items = CapexItem.objects.all()
    # Compute value in DB instead of Python loop
    total_inventory_value = InventoryItem.objects.aggregate(
        total=Sum(
            ExpressionWrapper(F('quantity') * F('unit_cost'), output_field=DecimalField())
        )
    )['total'] or Decimal('0')
    total_capex_value = capex_items.aggregate(total=Sum('purchase_cost'))['total'] or Decimal('0')

    context = {
        'inventory_items': inventory_items,
        'capex_items': capex_items,
        'total_inventory_value': total_inventory_value,
        'total_capex_value': total_capex_value,
    }
    return render(request, 'procurement/inventory_capex.html', context)


# ─── DASHBOARD API ───────────────────────────────────────────────────────────

@login_required
@role_required(User.Role.ADMIN)
def api_monthly_finance(request):
    """Return monthly income and expense data for charts."""
    now = timezone.now()
    year = int(request.GET.get('year', now.year))

    data = {'months': [], 'income': [], 'expenses': []}
    for month in range(1, 13):
        data['months'].append(datetime.date(year, month, 1).strftime('%b'))

        income = Payment.objects.filter(
            payment_date__year=year, payment_date__month=month
        ).aggregate(total=Sum('amount'))['total'] or 0
        data['income'].append(float(income))

        expense = Expense.objects.filter(
            date__year=year, date__month=month
        ).aggregate(total=Sum('amount'))['total'] or 0
        data['expenses'].append(float(expense))

    return JsonResponse(data)
