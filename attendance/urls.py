from django.urls import path
from . import views

urlpatterns = [
    path('mark_attendance/', views.mark_attendance, name='mark_attendance'),
    path('my_attendance/', views.my_attendance, name='my_attendance'),
]
