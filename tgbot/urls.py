from django.urls import path

from . import views

urlpatterns = [path('app/', views.app, name='tg_app'), path('auth/', views.auth, name='tg_auth'),
               path('webhook/', views.webhook, name='tg_webhook')]
