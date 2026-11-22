import re

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import Group
from org.scope import pick_branch, scope_groups

from . import audit
from .hubs import org_hub
from .access import panel_required
from .forms import GroupForm


def _natural(group):
    m = re.match(r'\s*(\d+)', group.name)
    return (int(m.group(1)) if m else 999, group.name)


@panel_required('groups.view')
@org_hub('groups')
def groups(request):
    qs = scope_groups(Group.objects.exclude(name__startswith='Sinov-'), request.user).annotate(n=Count('students'))
    return render(request, 'panel/groups.html', {'nav': 'groups', 'groups': sorted(qs, key=_natural)})


@panel_required('groups.change')
def group_edit(request, pk=None):
    group = get_object_or_404(scope_groups(Group.objects.all(), request.user), pk=pk) if pk else None
    before = group.name if group else ''
    before_price = group.monthly_price if group else None     # forma tekshirilganda obyekt o'zgaradi, shuning uchun eski nom oldindan olinadi
    form = GroupForm(request.POST or None, instance=group, branch=group.branch if group else pick_branch(request.user))
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        if not group:
            saved.branch = pick_branch(request.user)
        saved.save()
        if saved.monthly_price != before_price:
            from billing.services import recalc_current_month
            recalc_current_month(group=saved)
        audit.log(request, "Sinfni o'zgartirdi" if group else "Sinf qo'shdi", saved, label=saved.name, target_type='group',
                  details={'nom': audit.change(before, saved.name)} if group and before != saved.name else {})
        messages.success(request, 'Saqlandi.')
        return redirect('panel:groups')
    return render(request, 'panel/group_form.html', {'nav': 'groups', 'form': form, 'group': group,
                                                     'title': group.name if group else "Yangi sinf"})
