"""Bog'cha galereyasi: albom (tadbir/kun) va rasmlar. Har rasmda kimlar borligi belgilanadi — ota-ona faqat o'z farzandi
belgilangan rasmlarni ko'radi (2026-11-26). Fayllar ochiq emas: faqat ruxsat tekshiradigan view orqali beriladi."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Album(models.Model):
    branch = models.ForeignKey('org.Branch', on_delete=models.CASCADE, related_name='albums', verbose_name='Filial')
    group = models.ForeignKey('academics.Group', on_delete=models.SET_NULL, null=True, blank=True, related_name='albums', verbose_name='Guruh')
    title = models.CharField('Nomi', max_length=120)
    date = models.DateField('Sana', default=timezone.localdate)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-id']
        verbose_name = 'Albom'
        verbose_name_plural = 'Albomlar'

    def __str__(self):
        return self.title


class Photo(models.Model):
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='gallery/%Y/%m/')
    thumb = models.ImageField(upload_to='gallery/thumbs/%Y/%m/')
    children = models.ManyToManyField('accounts.Student', blank=True, related_name='gallery_photos', verbose_name='Rasmdagi bolalar')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Rasm'
        verbose_name_plural = 'Rasmlar'

    def delete_files(self):
        for f in (self.image, self.thumb):
            if f:
                f.delete(save=False)
