"""Maktab egasi (founder) bosh sahifasi: raqamli ko'rsatkichlar. Hisob-kitob `owner_stats.py` da."""
from django.shortcuts import render
from django.utils import timezone

from org.models import Organization

from . import owner_stats


def owner_home(request):
    today = timezone.localdate()
    month = owner_stats.parse_month(request.GET.get('oy'), today)
    try:
        org_id = int(request.GET.get('tashkilot') or 0) or None
    except ValueError:
        org_id = None
    report = owner_stats.build_report(request.user, month, today, org_id)
    return render(request, 'panel/owner.html', {
        'nav': 'dashboard', 'r': report, 'today': today, 'org_id': org_id,
        'all_orgs': Organization.objects.order_by('name'), 'month_label': f"{owner_stats.UZ_MONTHS[month.month]} {month.year}",
    })
