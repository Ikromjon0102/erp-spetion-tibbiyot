from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts import views as acc
from billing import views as billing_views
from accounts.photo_view import face_photo

admin.site.site_header = 'Tibbiyot maktabi — boshqaruv'
admin.site.site_title = 'Tibbiyot maktabi'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('panel/', include('panel.urls')),
    path('login/', acc.ThrottledLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('parol/', acc.change_password, name='change_password'),
    path('vazifa/oqildi/', acc.homework_read, name='homework_read'),
    path('', acc.home, name='home'),
    path('oquvchi/<int:pk>/', acc.student_detail, name='student_detail'),
    path('oquvchi/<int:pk>/chek/<int:pay>/', billing_views.receipt, name='receipt'),
    path('rasm/<int:pk>/', face_photo, name='face_photo'),
    path('ustoz/', include('journal.urls')),
    path('api/access/', include('access.urls')),
    path('tg/', include('tgbot.urls')),
    path('elonlar/', include('notices.urls')),
]
