from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import User
from .phone import to_digits


class PhoneBackend(ModelBackend):
    """Login = telefon raqam (istalgan formatda). Ustoz ham, ota-ona ham shu raqam bilan kiradi.
    Telefonga o'xshamagan login (admin, 'diyora') oddiy username sifatida tekshiriladi."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        digits = to_digits(username)
        if not digits:
            return super().authenticate(request, username=username, password=password, **kwargs)
        if password is None:
            return None
        # Bir raqamga bir nechta hisob tushib qolgan bo'lsa (birlashtirilmagan), parol mos kelganini tanlaymiz
        for user in User.objects.filter(Q(phone_digits=digits) | Q(username=digits)).order_by('id'):
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
        User().set_password(password)  # mavjud bo'lmagan foydalanuvchida ham vaqt bir xil bo'lsin
        return None
