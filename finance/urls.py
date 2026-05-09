from django.urls import path
from . import views

urlpatterns = [
    path('manage_finance/', views.manage_finance, name='manage_finance'),
]
