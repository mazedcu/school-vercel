from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class BookCategory(models.Model):
    """Category for organizing books (e.g. Fiction, Science, History)."""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Book Categories'

    def __str__(self):
        return self.name


class Book(models.Model):
    """Represents a book title in the library catalog."""
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255)
    isbn = models.CharField(max_length=20, unique=True, blank=True, null=True, verbose_name='ISBN')
    category = models.ForeignKey(BookCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='books')
    publisher = models.CharField(max_length=200, blank=True)
    edition = models.CharField(max_length=50, blank=True)
    language = models.CharField(max_length=50, default='English')
    shelf_location = models.CharField(max_length=50, blank=True, help_text='e.g. Shelf A-3')
    total_copies = models.PositiveIntegerField(default=1)
    description = models.TextField(blank=True)
    added_date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return f"{self.title} by {self.author}"

    @property
    def available_copies(self):
        return self.copies.filter(status='available').count()

    @property
    def issued_copies(self):
        return self.copies.filter(status='issued').count()


class BookCopy(models.Model):
    """Represents a physical copy of a book."""

    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        ISSUED = 'issued', 'Issued'
        LOST = 'lost', 'Lost'
        DAMAGED = 'damaged', 'Damaged'

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='copies')
    copy_number = models.PositiveIntegerField()
    accession_number = models.CharField(max_length=30, unique=True, help_text='Unique library accession number')
    condition = models.CharField(max_length=20, default='Good')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)

    class Meta:
        ordering = ['book', 'copy_number']
        verbose_name_plural = 'Book Copies'
        constraints = [
            models.UniqueConstraint(fields=['book', 'copy_number'], name='unique_book_copy')
        ]

    def __str__(self):
        return f"{self.book.title} (Copy #{self.copy_number} - {self.accession_number})"


class BookLending(models.Model):
    """Tracks every book issue and return transaction."""

    class Status(models.TextChoices):
        ISSUED = 'issued', 'Issued'
        RETURNED = 'returned', 'Returned'
        OVERDUE = 'overdue', 'Overdue'

    book_copy = models.ForeignKey(BookCopy, on_delete=models.CASCADE, related_name='lendings')
    borrower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='book_borrowings')
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='books_issued', help_text='Staff who issued the book'
    )
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    fine_per_day = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('5.00'))
    fine_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return f"{self.book_copy.book.title} → {self.borrower.username} ({self.get_status_display()})"

    @property
    def is_overdue(self):
        if self.status == self.Status.ISSUED and timezone.now().date() > self.due_date:
            return True
        return False

    @property
    def overdue_days(self):
        if self.is_overdue:
            return (timezone.now().date() - self.due_date).days
        if self.return_date and self.return_date > self.due_date:
            return (self.return_date - self.due_date).days
        return 0

    def calculate_fine(self):
        days = self.overdue_days
        if days > 0:
            return self.fine_per_day * days
        return Decimal('0.00')
