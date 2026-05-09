from django.urls import path
from . import views

urlpatterns = [
    path('student_profiles/', views.student_profiles, name='student_profiles'),
    path('student_profile/<int:student_id>/', views.student_profile_detail, name='student_profile_detail'),
]
