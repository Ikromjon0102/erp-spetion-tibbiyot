from django.urls import path

from . import views

app_name = 'gallery'
urlpatterns = [
    path('', views.home, name='home'),
    path('yangi/', views.add, name='add'),
    path('<int:pk>/', views.album, name='album'),
    path('rasm/<int:pk>/ochirish/', views.photo_delete, name='photo_delete'),
]
