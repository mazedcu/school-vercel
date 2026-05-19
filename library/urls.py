from django.urls import path
from . import views

urlpatterns = [
    path('', views.library_dashboard, name='library_dashboard'),
    path('catalog/', views.book_catalog, name='library_catalog'),
    path('add-book/', views.add_book, name='library_add_book'),
    path('edit-book/<int:book_id>/', views.edit_book, name='library_edit_book'),
    path('delete-book/<int:book_id>/', views.delete_book, name='library_delete_book'),
    path('categories/', views.manage_categories, name='library_categories'),
    path('issue/', views.issue_book, name='library_issue'),
    path('return/<int:lending_id>/', views.return_book, name='library_return'),
    path('history/', views.lending_history, name='library_history'),
    path('my-books/', views.my_books, name='library_my_books'),
]
