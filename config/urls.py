from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts import views as acc
from billing import views as billing_views
from accounts.photo_view import face_photo
from accounts import pwa
from panel import views_gallery, views_meals

admin.site.site_header = 'Tibbiyot maktabi — boshqaruv'
admin.site.site_title = 'Tibbiyot maktabi'

urlpatterns = [
    path('manifest.webmanifest', pwa.manifest, name='pwa_manifest'),
    path('sw.js', pwa.service_worker, name='pwa_sw'),
    path('admin/', admin.site.urls),
    path('panel/', include('panel.urls')),
    path('login/', acc.ThrottledLoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('parol/', acc.change_password, name='change_password'),
    path('vazifa/oqildi/', acc.homework_read, name='homework_read'),
    path('', acc.home, name='home'),
    path('oquvchi/<int:pk>/', acc.student_detail, name='student_detail'),
    path('oquvchi/<int:pk>/imtihon/', acc.student_exam, name='student_exam'),
    path('oquvchi/<int:pk>/chek/<int:pay>/', billing_views.receipt, name='receipt'),
    path('rasm/<int:pk>/', face_photo, name='face_photo'),
    path('taom/<int:pk>/rasm/', views_meals.dish_photo, name='dish_photo'),
    path('galereya/<int:pk>/', views_gallery.photo_file, name='gallery_photo'),
    path('ustoz/galereya/', include('gallery.urls')),
    path('ustoz/', include('journal.urls')),
    path('api/access/', include('access.urls')),
    path('tg/', include('tgbot.urls')),
    path('elonlar/', include('notices.urls')),
]
