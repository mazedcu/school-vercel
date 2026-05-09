from django.contrib import admin
from .models import FeeStructure, Invoice, InvoiceLineItem, Payment

@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ('name', 'class_group', 'amount', 'academic_year')

class InvoiceLineItemInline(admin.TabularInline):
    model = InvoiceLineItem
    extra = 0

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'student', 'class_group', 'subtotal', 'discount_amount', 'amount_due', 'amount_paid', 'status', 'due_date')
    list_filter = ('status', 'class_group')
    search_fields = ('invoice_number', 'student__username', 'student__first_name', 'student__last_name')
    inlines = [InvoiceLineItemInline, PaymentInline]

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount', 'payment_date', 'method')
