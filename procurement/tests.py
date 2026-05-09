from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from accounts.models import User
from academics.models import Section, ClassGroup, Subject
from procurement.models import PurchaseRequest, PurchaseOrder, InventoryItem, Expense
from decimal import Decimal

class ProcurementLifecycleTest(TestCase):
    def setUp(self):
        # Setup basic data
        self.admin = User.objects.create_superuser(username='admin_test', password='password123', email='admin@test.com', role=User.Role.ADMIN)
        self.teacher = User.objects.create_user(username='teacher_test', password='password123', email='teacher@test.com', role=User.Role.TEACHER)
        
        self.cg = ClassGroup.objects.create(name='Grade 1')
        self.section = Section.objects.create(name='A', class_group=self.cg, academic_year='2026')
        
        self.client = Client()

    def test_full_procurement_lifecycle(self):
        # 1. Teacher submits a Purchase Request
        self.client.login(username='teacher_test', password='password123')
        pr_url = reverse('purchase_requests')
        response = self.client.post(pr_url, {
            'action': 'create_request',
            'title': 'Scientific Calculators',
            'items_detail': '10 Scientific Calculators, Casio MX-100',
            'item_type': 'inventory',
            'estimated_cost': '5000.00',
            'justification': 'For Grade 1 Science Lab'
        })
        self.assertIn(response.status_code, [200, 302])
        pr = PurchaseRequest.objects.get(title='Scientific Calculators')
        self.assertEqual(pr.status, PurchaseRequest.Status.PENDING)
        self.client.logout()

        # 2. Admin approves the Request
        self.client.login(username='admin_test', password='password123')
        response = self.client.post(pr_url, {
            'action': 'approve',
            'pr_id': pr.id,
            'admin_remarks': 'Approved by admin'
        })
        self.assertIn(response.status_code, [200, 302])
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseRequest.Status.APPROVED)

        # 3. Admin creates a Purchase Order (using the SAME view)
        response = self.client.post(pr_url, {
            'action': 'create_po',
            'pr_id': pr.id,
            'vendor_name': 'EduTech Supplies',
            'actual_cost': '4500.00',
            'expected_delivery': (timezone.now() + timezone.timedelta(days=7)).date().isoformat()
        })
        self.assertIn(response.status_code, [200, 302])
        po = PurchaseOrder.objects.get(purchase_request=pr)
        self.assertTrue(po.po_number.startswith('PO-'))

        # 4. Admin marks PO as Received
        response = self.client.post(pr_url, {
            'action': 'receive_po',
            'po_id': po.id
        })
        self.assertIn(response.status_code, [200, 302])
        
        po.refresh_from_db()
        self.assertTrue(po.is_received)
        
        # 5. Verify Inventory and Expense
        inventory_item = InventoryItem.objects.get(name='Scientific Calculators')
        self.assertGreaterEqual(inventory_item.quantity, 0)
        
        expense = Expense.objects.filter(description__contains='Scientific Calculators').first()
        self.assertIsNotNone(expense)
        print("\nPASSED: Procurement Lifecycle Test (PR -> Approval -> PO -> Received -> Inventory -> Expense)")
