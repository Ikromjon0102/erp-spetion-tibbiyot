from .models import AuditLog


def log(request, verb, target=None, label='', details=None, target_type=''):
    """Faoliyat jurnaliga yozadi. `target` — model obyekti bo'lsa, turi va identifikatori o'zi olinadi."""
    user = request.user if request.user.is_authenticated else None
    if target is not None:
        target_type = target_type or target.__class__.__name__.lower()
        label = label or str(target)
    return AuditLog.objects.create(
        actor=user, actor_name=(user.get_full_name() or user.username) if user else '',
        verb=verb, target_type=target_type, target_id=getattr(target, 'pk', None), target_label=label[:200],
        details=details or {}, ip=request.META.get('REMOTE_ADDR') or None)


def changes(before, after, labels):
    """{maydon: (eski, yangi)} — faqat o'zgarganlar, o'qiladigan nomlar bilan."""
    return {labels[k]: {'eski': str(before[k] or '—'), 'yangi': str(after[k] or '—')} for k in labels if before[k] != after[k]}


def change(old, new):
    return {'eski': str(old), 'yangi': str(new)}


def lines(details):
    """Jurnal tafsilotini o'qiladigan qatorlarga aylantiradi: [(nom, matn)]."""
    out = []
    for key, value in (details or {}).items():
        if isinstance(value, dict) and 'eski' in value:
            text = f"{value['eski']} → {value['yangi']}"
        elif isinstance(value, (list, tuple)):
            text = ', '.join(str(v) for v in value) or '—'
        else:
            text = str(value)
        out.append((key, text))
    return out
