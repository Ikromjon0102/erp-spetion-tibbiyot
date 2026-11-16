from django.urls import path

from . import views

app_name = 'journal'
urlpatterns = [
    path('', views.teacher_home, name='teacher_home'),
    path('api/status/', views.api_status, name='api_status'),
    path('api/elonlar/', views.api_news, name='api_news'),
    path('api/dars/<int:pk>/', views.api_lesson, name='api_lesson'),
    path('api/dars/<int:pk>/saqlash/', views.api_lesson_save, name='api_lesson_save'),
    path('api/baho/<int:pk>/', views.api_grade, name='api_grade'),
    path('api/jurnal/<int:pk>/', views.api_journal, name='api_journal'),
    path('api/baho/<int:pk>/saqlash/', views.api_grade_save, name='api_grade_save'),
    path('api/baho/<int:pk>/ochirish/', views.api_grade_delete, name='api_grade_delete'),
    path('api/vazifa/<int:pk>/', views.api_hw, name='api_hw'),
    path('api/vazifa/<int:pk>/saqlash/', views.api_hw_save, name='api_hw_save'),
    path('api/vazifa/<int:pk>/<int:hid>/yangilash/', views.api_hw_update, name='api_hw_update'),
    path('api/vazifa/<int:pk>/<int:hid>/ochirish/', views.api_hw_delete, name='api_hw_delete'),
]
