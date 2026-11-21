from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import User


@receiver(post_save, sender=User)
def give_default_branch(sender, instance, created, **kwargs):
    """Yangi ustoz/ma'muriyat/xodim filial ko'rsatilmaguncha asosiy filialga biriktiriladi
    (panel formalari keyin aniq filialni belgilaydi). Aks holda u hech narsani ko'ra olmasdi."""
    if created and instance.role in (User.Role.TEACHER, User.Role.ADMIN, User.Role.STAFF):
        from .models import default_branch
        branch = default_branch()
        if branch:
            instance.branches.add(branch)
