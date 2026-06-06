from django.urls import path
from . import views

urlpatterns = [
    path('lesson-plans/', views.lesson_plan_list, name='lesson_plan_list'),
    path('lesson-plans/new/', views.lesson_plan_create, name='lesson_plan_create'),
    path('lesson-plans/<int:pk>/', views.lesson_plan_detail, name='lesson_plan_detail'),
    path('lesson-plans/<int:pk>/edit/', views.lesson_plan_edit, name='lesson_plan_edit'),
    path('lesson-plans/<int:pk>/review/', views.lesson_plan_review, name='lesson_plan_review'),
    path('lesson-plans/<int:pk>/pdf/', views.lesson_plan_pdf, name='lesson_plan_pdf'),
]
