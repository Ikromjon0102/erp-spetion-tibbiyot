from django.urls import path

from . import views

urlpatterns = [
    path('hikvision/<str:token>/', views.hikvision_push, name='hikvision_push'),
]
