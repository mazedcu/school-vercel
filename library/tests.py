from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
import datetime

from accounts.models import User
from library.models import BookCategory, Book, BookCopy, BookLending


class LibraryTestCase(TestCase):
    def setUp(self):
        # Create users
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@example.com', password='password123', role=User.Role.ADMIN
        )
        self.student = User.objects.create_user(
            username='student', email='student@example.com', password='password123', role=User.Role.STUDENT
        )
        
        # Create a category
        self.category = BookCategory.objects.create(
            name="Fiction", description="Fiction books"
        )
        
        # Create a client
        self.client = Client()

    def test_book_creation_and_copies(self):
        """Test that adding a book correctly generates matching physical BookCopy records."""
        book = Book.objects.create(
            title="Dune",
            author="Frank Herbert",
            isbn="9780441172719",
            category=self.category,
            total_copies=3
        )
        
        # Auto-create copies manually to mimic add_book view functionality
        for i in range(1, book.total_copies + 1):
            BookCopy.objects.create(
                book=book,
                copy_number=i,
                accession_number=f"LIB-{book.id:04d}-{i:02d}"
            )
            
        self.assertEqual(book.total_copies, 3)
        self.assertEqual(book.copies.count(), 3)
        self.assertEqual(book.available_copies, 3)
        self.assertEqual(book.issued_copies, 0)

    def test_lending_and_return_workflow(self):
        """Test issuing a book copy, status updates, and return calculations."""
        book = Book.objects.create(
            title="Dune",
            author="Frank Herbert",
            category=self.category,
            total_copies=1
        )
        copy = BookCopy.objects.create(
            book=book,
            copy_number=1,
            accession_number="LIB-0001-01"
        )
        
        self.assertEqual(copy.status, BookCopy.Status.AVAILABLE)
        
        # Issue the book
        today = timezone.now().date()
        due_date = today + datetime.timedelta(days=14)
        lending = BookLending.objects.create(
            book_copy=copy,
            borrower=self.student,
            issued_by=self.admin,
            issue_date=today,
            due_date=due_date,
            fine_per_day=Decimal('5.00')
        )
        copy.status = BookCopy.Status.ISSUED
        copy.save()
        
        self.assertEqual(copy.status, BookCopy.Status.ISSUED)
        self.assertEqual(lending.status, BookLending.Status.ISSUED)
        self.assertEqual(book.available_copies, 0)
        self.assertEqual(book.issued_copies, 1)
        
        # Return the book
        lending.return_date = today
        lending.status = BookLending.Status.RETURNED
        lending.fine_amount = lending.calculate_fine()
        lending.save()
        
        copy.status = BookCopy.Status.AVAILABLE
        copy.save()
        
        self.assertEqual(copy.status, BookCopy.Status.AVAILABLE)
        self.assertEqual(lending.status, BookLending.Status.RETURNED)
        self.assertEqual(lending.fine_amount, Decimal('0.00'))

    def test_overdue_and_fine_calculation(self):
        """Test overdue calculations and fine accumulation."""
        book = Book.objects.create(
            title="Dune",
            author="Frank Herbert",
            category=self.category,
            total_copies=1
        )
        copy = BookCopy.objects.create(
            book=book,
            copy_number=1,
            accession_number="LIB-0001-01"
        )
        
        today = timezone.now().date()
        # Due 5 days ago
        due_date = today - datetime.timedelta(days=5)
        
        lending = BookLending.objects.create(
            book_copy=copy,
            borrower=self.student,
            issued_by=self.admin,
            issue_date=today - datetime.timedelta(days=19),
            due_date=due_date,
            fine_per_day=Decimal('10.00'),
            status=BookLending.Status.ISSUED
        )
        
        self.assertTrue(lending.is_overdue)
        self.assertEqual(lending.overdue_days, 5)
        self.assertEqual(lending.calculate_fine(), Decimal('50.00'))

    def test_views_require_login(self):
        """Test that accessing library views requires login."""
        response = self.client.get(reverse('library_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirects to login
        
    def test_views_access_control(self):
        """Test that non-admin/teacher/coordinator roles cannot access admin views."""
        self.client.login(username='student', password='password123')
        
        # Dashboard is restricted to staff
        response = self.client.get(reverse('library_dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirects to home/dashboard router
        
        # My Books is allowed for students
        response = self.client.get(reverse('library_my_books'))
        self.assertEqual(response.status_code, 200)
