from django.urls import path

from . import agent, views

urlpatterns = [
    path('hikvision/<str:token>/', views.hikvision_push, name='hikvision_push'),
    path('agent/devices/', agent.devices, name='agent_devices'),
    path('agent/manifest/<str:token>/', agent.manifest, name='agent_manifest'),
    path('agent/photo/<int:user_id>/', agent.photo, name='agent_photo'),
    path('agent/report/<str:token>/', agent.report, name='agent_report'),
]
