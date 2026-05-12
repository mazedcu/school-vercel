from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from accounts.models import User
from academics.models import ClassGroup, Section
from finance.models import FeeStructure, Invoice, InvoiceLineItem, Payment

class FinanceTestCase(TestCase):
    def setUp(self):
        # Create a class group
        self.class_group = ClassGroup.objects.create(name="Grade 10", display_order=10)
        
        # Create a section
        self.section = Section.objects.create(
            name="A", 
            class_group=self.class_group, 
            academic_year="2025-26"
        )
        
        # Create a student
        self.student = User.objects.create_user(
            username="test_student",
            password="password123",
            role=User.Role.STUDENT,
            first_name="Test",
            last_name="Student"
        )
        
        # Create fee structures
        self.tuition_fee = FeeStructure.objects.create(
            class_group=self.class_group,
            name="Tuition Fee",
            amount=Decimal('5000.00'),
            academic_year="2025-26"
        )
        self.lab_fee = FeeStructure.objects.create(
            class_group=self.class_group,
            name="Lab Fee",
            amount=Decimal('1000.00'),
            academic_year="2025-26"
        )

    def test_invoice_creation_and_numbering(self):
        """Test that invoices are created with correct serial numbers and totals."""
        invoice = Invoice.objects.create(
            student=self.student,
            class_group=self.class_group,
            due_date=timezone.now().date() + timezone.timedelta(days=30)
        )
        
        # Check invoice number format (Grade10-YYMM-001)
        self.assertTrue(invoice.invoice_number.startswith("Grade10"))
        self.assertTrue(invoice.invoice_number.endswith("-001"))
        
        # Add line items
        InvoiceLineItem.objects.create(
            invoice=invoice,
            fee_structure=self.tuition_fee,
            description=self.tuition_fee.name,
            amount=self.tuition_fee.amount
        )
        InvoiceLineItem.objects.create(
            invoice=invoice,
            fee_structure=self.lab_fee,
            description=self.lab_fee.name,
            amount=self.lab_fee.amount
        )
        
        # Recalculate (manually triggered because save() was called on LineItem creation, 
        # but the signals or manual trigger in model.save handles it on invoice save)
        invoice.recalculate_totals()
        invoice.save()
        
        self.assertEqual(invoice.subtotal, Decimal('6000.00'))
        self.assertEqual(invoice.amount_due, Decimal('6000.00'))
        self.assertEqual(invoice.status, Invoice.Status.UNPAID)

    def test_payment_updates_invoice(self):
        """Test that making a payment updates the invoice status."""
        invoice = Invoice.objects.create(
            student=self.student,
            class_group=self.class_group,
            due_date=timezone.now().date() + timezone.timedelta(days=30)
        )
        InvoiceLineItem.objects.create(
            invoice=invoice,
            description="Fee",
            amount=Decimal('1000.00')
        )
        invoice.recalculate_totals()
        invoice.save()
        
        # Make a partial payment
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal('400.00'),
            method='cash'
        )
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal('400.00'))
        self.assertEqual(invoice.status, Invoice.Status.PARTIAL)
        
        # Make another payment to complete
        Payment.objects.create(
            invoice=invoice,
            amount=Decimal('600.00'),
            method='online'
        )
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal('1000.00'))
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    def test_discount_calculation(self):
        """Test that discounts are correctly applied to amount_due."""
        invoice = Invoice.objects.create(
            student=self.student,
            class_group=self.class_group,
            due_date=timezone.now().date() + timezone.timedelta(days=30),
            discount_amount=Decimal('500.00'),
            discount_description="Scholarship"
        )
        InvoiceLineItem.objects.create(
            invoice=invoice,
            description="Fee",
            amount=Decimal('2000.00')
        )
        invoice.recalculate_totals()
        invoice.save()
        
        self.assertEqual(invoice.subtotal, Decimal('2000.00'))
        self.assertEqual(invoice.amount_due, Decimal('1500.00'))
