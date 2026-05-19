from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count, Sum
from django.utils import timezone
from decimal import Decimal
import datetime

from accounts.decorators import role_required
from accounts.models import User
from .models import BookCategory, Book, BookCopy, BookLending


# ── Dashboard ──────────────────────────────────────────────────
@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER, User.Role.COORDINATOR)
def library_dashboard(request):
    """Library overview with stats and recent activity."""
    today = timezone.now().date()

    total_books = Book.objects.count()
    total_copies = BookCopy.objects.count()
    available = BookCopy.objects.filter(status='available').count()
    issued = BookCopy.objects.filter(status='issued').count()

    # Mark overdue lendings
    overdue_qs = BookLending.objects.filter(status='issued', due_date__lt=today)
    overdue_count = overdue_qs.count()
    overdue_qs.update(status='overdue')

    overdue_lendings = BookLending.objects.filter(status='overdue').select_related(
        'book_copy__book', 'borrower'
    )[:10]

    recent_lendings = BookLending.objects.select_related(
        'book_copy__book', 'borrower'
    ).order_by('-issue_date')[:10]

    popular_books = Book.objects.annotate(
        times_issued=Count('copies__lendings')
    ).order_by('-times_issued')[:5]

    context = {
        'total_books': total_books,
        'total_copies': total_copies,
        'available': available,
        'issued': issued,
        'overdue_count': BookLending.objects.filter(status='overdue').count(),
        'overdue_lendings': overdue_lendings,
        'recent_lendings': recent_lendings,
        'popular_books': popular_books,
    }
    return render(request, 'library/library_dashboard.html', context)


# ── Book Catalog ───────────────────────────────────────────────
@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER, User.Role.COORDINATOR)
def book_catalog(request):
    """Searchable, filterable book catalog."""
    query = request.GET.get('q', '')
    category_id = request.GET.get('category', '')

    books = Book.objects.select_related('category').all()
    if query:
        books = books.filter(
            Q(title__icontains=query) | Q(author__icontains=query) | Q(isbn__icontains=query)
        )
    if category_id:
        books = books.filter(category_id=category_id)

    categories = BookCategory.objects.all()
    context = {
        'books': books,
        'categories': categories,
        'query': query,
        'selected_category': category_id,
    }
    return render(request, 'library/book_catalog.html', context)


# ── Add / Edit Book ───────────────────────────────────────────
@login_required
@role_required(User.Role.ADMIN)
def add_book(request):
    """Add a new book and auto-create its copies."""
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        author = request.POST.get('author', '').strip()
        isbn = request.POST.get('isbn', '').strip() or None
        category_id = request.POST.get('category', '')
        publisher = request.POST.get('publisher', '').strip()
        edition = request.POST.get('edition', '').strip()
        language = request.POST.get('language', 'English').strip()
        shelf_location = request.POST.get('shelf_location', '').strip()
        total_copies = int(request.POST.get('total_copies', '1'))
        description = request.POST.get('description', '').strip()
        accession_prefix = request.POST.get('accession_prefix', 'LIB').strip()

        if not title or not author:
            messages.error(request, 'Title and Author are required.')
            return redirect('library_add_book')

        category = BookCategory.objects.get(id=category_id) if category_id else None

        book = Book.objects.create(
            title=title, author=author, isbn=isbn, category=category,
            publisher=publisher, edition=edition, language=language,
            shelf_location=shelf_location, total_copies=total_copies,
            description=description,
        )

        # Auto-create copies
        for i in range(1, total_copies + 1):
            BookCopy.objects.create(
                book=book,
                copy_number=i,
                accession_number=f"{accession_prefix}-{book.id:04d}-{i:02d}",
            )

        messages.success(request, f"Book '{title}' added with {total_copies} copies.")
        return redirect('library_catalog')

    categories = BookCategory.objects.all()
    return render(request, 'library/add_book.html', {'categories': categories})


@login_required
@role_required(User.Role.ADMIN)
def edit_book(request, book_id):
    """Edit an existing book."""
    book = get_object_or_404(Book, id=book_id)

    if request.method == 'POST':
        book.title = request.POST.get('title', book.title).strip()
        book.author = request.POST.get('author', book.author).strip()
        book.isbn = request.POST.get('isbn', '').strip() or None
        category_id = request.POST.get('category', '')
        book.category = BookCategory.objects.get(id=category_id) if category_id else None
        book.publisher = request.POST.get('publisher', '').strip()
        book.edition = request.POST.get('edition', '').strip()
        book.language = request.POST.get('language', 'English').strip()
        book.shelf_location = request.POST.get('shelf_location', '').strip()
        book.description = request.POST.get('description', '').strip()

        new_total = int(request.POST.get('total_copies', book.total_copies))
        old_total = book.total_copies

        book.total_copies = new_total
        book.save()

        # Create additional copies if total increased
        if new_total > old_total:
            accession_prefix = request.POST.get('accession_prefix', 'LIB').strip()
            for i in range(old_total + 1, new_total + 1):
                BookCopy.objects.create(
                    book=book,
                    copy_number=i,
                    accession_number=f"{accession_prefix}-{book.id:04d}-{i:02d}",
                )

        messages.success(request, f"Book '{book.title}' updated.")
        return redirect('library_catalog')

    categories = BookCategory.objects.all()
    return render(request, 'library/add_book.html', {'categories': categories, 'book': book, 'editing': True})


@login_required
@role_required(User.Role.ADMIN)
def delete_book(request, book_id):
    """Delete a book and all its copies."""
    book = get_object_or_404(Book, id=book_id)
    if request.method == 'POST':
        title = book.title
        book.delete()
        messages.success(request, f"Book '{title}' deleted.")
        return redirect('library_catalog')
    return redirect('library_catalog')


# ── Categories ─────────────────────────────────────────────────
@login_required
@role_required(User.Role.ADMIN)
def manage_categories(request):
    """CRUD for book categories."""
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add':
            name = request.POST.get('name', '').strip()
            desc = request.POST.get('description', '').strip()
            if name:
                BookCategory.objects.get_or_create(name=name, defaults={'description': desc})
                messages.success(request, f"Category '{name}' created.")

        elif action == 'delete':
            cat_id = request.POST.get('category_id')
            if cat_id:
                cat = get_object_or_404(BookCategory, id=cat_id)
                cat.delete()
                messages.success(request, f"Category deleted.")

        return redirect('library_categories')

    categories = BookCategory.objects.annotate(book_count=Count('books')).all()
    return render(request, 'library/manage_categories.html', {'categories': categories})


# ── Issue Book ─────────────────────────────────────────────────
@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER, User.Role.COORDINATOR)
def issue_book(request):
    """Issue an available book copy to a user."""
    if request.method == 'POST':
        copy_id = request.POST.get('book_copy')
        borrower_id = request.POST.get('borrower')
        due_days = int(request.POST.get('due_days', '14'))
        fine_per_day = request.POST.get('fine_per_day', '5.00')

        copy = get_object_or_404(BookCopy, id=copy_id)
        borrower = get_object_or_404(User, id=borrower_id)

        if copy.status != 'available':
            messages.error(request, 'This copy is not available for lending.')
            return redirect('library_issue')

        today = timezone.now().date()
        BookLending.objects.create(
            book_copy=copy,
            borrower=borrower,
            issued_by=request.user,
            issue_date=today,
            due_date=today + datetime.timedelta(days=due_days),
            fine_per_day=Decimal(fine_per_day),
        )
        copy.status = 'issued'
        copy.save()

        messages.success(request, f"'{copy.book.title}' issued to {borrower.username} for {due_days} days.")
        return redirect('library_dashboard')

    available_copies = BookCopy.objects.filter(status='available').select_related('book')
    borrowers = User.objects.filter(
        role__in=[User.Role.STUDENT, User.Role.TEACHER]
    ).order_by('username')

    context = {
        'available_copies': available_copies,
        'borrowers': borrowers,
    }
    return render(request, 'library/issue_book.html', context)


# ── Return Book ────────────────────────────────────────────────
@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER, User.Role.COORDINATOR)
def return_book(request, lending_id):
    """Mark a book as returned and auto-calculate fine."""
    lending = get_object_or_404(BookLending, id=lending_id)

    if request.method == 'POST':
        today = timezone.now().date()
        lending.return_date = today
        lending.status = BookLending.Status.RETURNED
        lending.fine_amount = lending.calculate_fine()
        lending.save()

        copy = lending.book_copy
        copy.status = 'available'
        copy.save()

        msg = f"'{copy.book.title}' returned by {lending.borrower.username}."
        if lending.fine_amount > 0:
            msg += f" Fine: Tk.{lending.fine_amount}"
        messages.success(request, msg)
        return redirect('library_history')

    return render(request, 'library/return_confirm.html', {'lending': lending})


# ── Lending History ────────────────────────────────────────────
@login_required
@role_required(User.Role.ADMIN, User.Role.TEACHER, User.Role.COORDINATOR)
def lending_history(request):
    """Full lending log with filters."""
    status_filter = request.GET.get('status', '')
    query = request.GET.get('q', '')

    lendings = BookLending.objects.select_related('book_copy__book', 'borrower', 'issued_by').all()

    if status_filter:
        lendings = lendings.filter(status=status_filter)
    if query:
        lendings = lendings.filter(
            Q(book_copy__book__title__icontains=query) | Q(borrower__username__icontains=query)
        )

    context = {
        'lendings': lendings[:100],
        'status_filter': status_filter,
        'query': query,
    }
    return render(request, 'library/lending_history.html', context)


# ── My Books (Student / Teacher) ──────────────────────────────
@login_required
def my_books(request):
    """View own current and past borrowings."""
    current = BookLending.objects.filter(
        borrower=request.user, status__in=['issued', 'overdue']
    ).select_related('book_copy__book')

    past = BookLending.objects.filter(
        borrower=request.user, status='returned'
    ).select_related('book_copy__book').order_by('-return_date')[:20]

    context = {
        'current': current,
        'past': past,
    }
    return render(request, 'library/my_books.html', context)
