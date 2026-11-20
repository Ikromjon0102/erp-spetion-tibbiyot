import secrets

ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'  # o/0, l/1/i kabi adashadigan belgilarsiz


def new_temp_password(length=8):
    return ''.join(secrets.choice(ALPHABET) for _ in range(length))


def initial_password(user):
    """Boshlang'ich parol — telefonning oxirgi 4 raqami (ustoz va ota-onalar uchun bir xil qoida); birinchi kirishda almashtirish shart.
    Telefon bo'lmasa, tasodifiy bir martalik parol beriladi."""
    digits = user.phone_digits or ''
    if len(digits) < 4:
        return issue_temp_password(user)
    user.set_password(digits[-4:])
    user.must_change_password = True
    user.save()
    return digits[-4:]


def issue_temp_password(user):
    """Bir martalik parol beradi; foydalanuvchi birinchi kirishda uni almashtirishi shart."""
    password = new_temp_password()
    user.set_password(password)
    user.must_change_password = True
    user.save()
    return password
