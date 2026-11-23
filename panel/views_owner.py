"""Maktab egasi (founder) bosh sahifasi: raqamli ko'rsatkichlar. Hisob-kitob `owner_stats.py` da.
Ko'rsatilayotgan narsa tanlangan ish maydoniga (Hammasi / tashkilot / filial) bog'liq."""
from django.shortcuts import render
from django.utils import timezone

from . import owner_stats


def owner_home(request):
    today = timezone.localdate()
    month = owner_stats.parse_month(request.GET.get('oy'), today)
    period = 'yil' if request.GET.get('davr') == 'yil' else 'oy'
    report = owner_stats.build_report(request.user, month, today)
    g = report['grand']
    suffix = 'y' if period == 'yil' else 'm'
    kpi = {'income': g[f'income_{suffix}'], 'expense': g[f'expense_{suffix}'], 'profit': g[f'profit_{suffix}']}
    month_label = f"{owner_stats.UZ_MONTHS[month.month]} {month.year}"
    from finance.salary import reminders
    paydays = reminders(request.user, today)
    return render(request, 'panel/owner.html', {
        'nav': 'dashboard', 'r': report, 'today': today, 'period': period, 'kpi': kpi, 'month_label': month_label,
        'paydays': paydays, 'paydays_multi': len({p['org'].pk for p in paydays}) > 1,
        'period_label': "O'quv yili (1-sentabrdan)" if period == 'yil' else month_label,
    })
