from django.db import models
from django.conf import settings
from django.utils import timezone


class Expense(models.Model):
    """Records a school expense."""
    class Category(models.TextChoices):
        SALARY = 'salary', 'Salary'
        UTILITIES = 'utilities', 'Utilities'
        MAINTENANCE = 'maintenance', 'Maintenance'
        SUPPLIES = 'supplies', 'Supplies'
        TRANSPORT = 'transport', 'Transport'
        FOOD = 'food', 'Food & Canteen'
        EVENTS = 'events', 'Events'
        CAPEX = 'capex', 'Capital Expenditure'
        OTHER = 'other', 'Other'

    date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=300)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, help_text="Receipt/Reference number")
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='recorded_expenses')
    purchase_order = models.ForeignKey('PurchaseOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.date} - {self.description} - Rs.{self.amount}"


class PurchaseRequest(models.Model):
    """A purchase request from a teacher or admin."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        ORDERED = 'ordered', 'Purchase Ordered'
        RECEIVED = 'received', 'Received & Stocked'

    class ItemType(models.TextChoices):
        INVENTORY = 'inventory', 'Inventory / Consumable'
        CAPEX = 'capex', 'Capital Asset (CAPEX)'

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='purchase_requests')
    title = models.CharField(max_length=200, help_text="Brief description of what is needed")
    items_detail = models.TextField(help_text="Detailed list of items, quantities, specifications")
    item_type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.INVENTORY)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2)
    justification = models.TextField(blank=True, help_text="Why is this purchase needed?")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    admin_remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"PR-{self.pk:04d} | {self.title} ({self.get_status_display()})"


class PurchaseOrder(models.Model):
    """A purchase order generated after admin approves a request."""
    purchase_request = models.OneToOneField(PurchaseRequest, on_delete=models.CASCADE, related_name='purchase_order')
    po_number = models.CharField(max_length=30, unique=True, blank=True)
    vendor_name = models.CharField(max_length=200)
    vendor_contact = models.CharField(max_length=100, blank=True)
    order_date = models.DateField(default=timezone.now)
    expected_delivery = models.DateField(null=True, blank=True)
    actual_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    is_received = models.BooleanField(default=False)
    received_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-order_date']

    def save(self, *args, **kwargs):
        if not self.po_number:
            now = timezone.now()
            prefix = f"PO-{now.strftime('%y%m')}"
            last = PurchaseOrder.objects.filter(po_number__startswith=prefix).order_by('-po_number').first()
            if last:
                try:
                    serial = int(last.po_number.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    serial = 1
            else:
                serial = 1
            self.po_number = f"{prefix}-{serial:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.po_number} | {self.vendor_name}"


class InventoryItem(models.Model):
    """Tracks inventory (consumable) items in stock."""
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    quantity = models.IntegerField(default=0)
    unit = models.CharField(max_length=30, default='pcs', help_text="e.g. pcs, kg, liters")
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_items')
    location = models.CharField(max_length=100, blank=True, help_text="Storage location")
    added_date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    @property
    def total_value(self):
        return self.quantity * self.unit_cost

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"


class CapexItem(models.Model):
    """Tracks capital expenditure assets."""
    asset_id = models.CharField(max_length=30, unique=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True, help_text="e.g. Furniture, Electronics, Vehicle")
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2)
    purchase_date = models.DateField(default=timezone.now)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.SET_NULL, null=True, blank=True, related_name='capex_items')
    location = models.CharField(max_length=100, blank=True)
    condition = models.CharField(max_length=20, default='good', choices=[
        ('new', 'New'), ('good', 'Good'), ('fair', 'Fair'), ('poor', 'Poor'), ('disposed', 'Disposed')
    ])
    useful_life_years = models.IntegerField(default=5)
    notes = models.TextField(blank=True)
    added_date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-purchase_date']

    def save(self, *args, **kwargs):
        if not self.asset_id:
            now = timezone.now()
            prefix = f"AST-{now.strftime('%y')}"
            last = CapexItem.objects.filter(asset_id__startswith=prefix).order_by('-asset_id').first()
            if last:
                try:
                    serial = int(last.asset_id.split('-')[-1]) + 1
                except (ValueError, IndexError):
                    serial = 1
            else:
                serial = 1
            self.asset_id = f"{prefix}-{serial:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.asset_id} | {self.name} - Rs.{self.purchase_cost}"
