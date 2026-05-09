from django.urls import path
from . import views

urlpatterns = [
    path('manage_classes/', views.manage_classes, name='manage_classes'),
]
