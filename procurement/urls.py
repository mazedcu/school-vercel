from django.urls import path
from . import views

urlpatterns = [
    path('expenses/', views.manage_expenses, name='manage_expenses'),
    path('account-statement/', views.account_statement, name='account_statement'),
    path('purchase-requests/', views.purchase_requests, name='purchase_requests'),
    path('inventory/', views.inventory_capex, name='inventory_capex'),
    path('api/monthly-finance/', views.api_monthly_finance, name='api_monthly_finance'),
]
