from django.urls import path

from . import views

urlpatterns = [
    path('', views.announcement_list, name='announcements'),
    path('<int:pk>/oqildi/', views.mark_read, name='announcement_read'),
]
