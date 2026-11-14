import secrets

ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'  # o/0, l/1/i kabi adashadigan belgilarsiz


def new_temp_password(length=8):
    return ''.join(secrets.choice(ALPHABET) for _ in range(length))


def issue_temp_password(user):
    """Bir martalik parol beradi; foydalanuvchi birinchi kirishda uni almashtirishi shart."""
    password = new_temp_password()
    user.set_password(password)
    user.must_change_password = True
    user.save()
    return password
