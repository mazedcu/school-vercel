from django.contrib import admin
from .models import BookCategory, Book, BookCopy, BookLending


class BookCopyInline(admin.TabularInline):
    model = BookCopy
    extra = 0


@admin.register(BookCategory)
class BookCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'isbn', 'category', 'total_copies', 'available_copies')
    list_filter = ('category', 'language')
    search_fields = ('title', 'author', 'isbn')
    inlines = [BookCopyInline]


@admin.register(BookCopy)
class BookCopyAdmin(admin.ModelAdmin):
    list_display = ('book', 'copy_number', 'accession_number', 'status', 'condition')
    list_filter = ('status', 'condition')
    search_fields = ('accession_number', 'book__title')


@admin.register(BookLending)
class BookLendingAdmin(admin.ModelAdmin):
    list_display = ('book_copy', 'borrower', 'issue_date', 'due_date', 'return_date', 'status', 'fine_amount')
    list_filter = ('status', 'issue_date')
    search_fields = ('book_copy__book__title', 'borrower__username')
