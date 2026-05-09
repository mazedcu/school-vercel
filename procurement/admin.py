from django.contrib import admin
from .models import Expense, PurchaseRequest, PurchaseOrder, InventoryItem, CapexItem

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'description', 'category', 'amount', 'recorded_by')
    list_filter = ('category', 'date')

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'requested_by', 'item_type', 'estimated_cost', 'status', 'created_at')
    list_filter = ('status', 'item_type')

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'purchase_request', 'vendor_name', 'actual_cost', 'is_received', 'order_date')
    list_filter = ('is_received',)

@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'quantity', 'unit', 'unit_cost', 'location')

@admin.register(CapexItem)
class CapexItemAdmin(admin.ModelAdmin):
    list_display = ('asset_id', 'name', 'category', 'purchase_cost', 'condition', 'purchase_date')
    list_filter = ('condition', 'category')
