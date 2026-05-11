from django.urls import path
from . import views

urlpatterns = [
    path('manage_finance/', views.manage_finance, name='manage_finance'),
    path('invoice/<int:invoice_id>/print/', views.print_invoice, name='print_invoice'),
    path('invoice/<int:invoice_id>/delete/', views.delete_invoice, name='delete_invoice'),
    path('api/students-by-class/', views.api_students_by_class, name='api_students_by_class'),
    path('api/students-by-section/', views.api_students_by_section, name='api_students_by_section'),
    path('api/invoices-by-class/', views.api_invoices_by_class, name='api_invoices_by_class'),
    path('api/fees-by-class/', views.api_fees_by_class, name='api_fees_by_class'),
]
