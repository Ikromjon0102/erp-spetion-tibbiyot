import re

from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import Group
from org.scope import pick_branch, scope_groups

from . import audit
from .access import panel_required
from .forms import GroupForm


def _natural(group):
    m = re.match(r'\s*(\d+)', group.name)
    return (int(m.group(1)) if m else 999, group.name)


@panel_required('groups.view')
def groups(request):
    qs = scope_groups(Group.objects.exclude(name__startswith='Sinov-'), request.user).annotate(n=Count('students'))
    return render(request, 'panel/groups.html', {'nav': 'groups', 'groups': sorted(qs, key=_natural)})


@panel_required('groups.change')
def group_edit(request, pk=None):
    group = get_object_or_404(scope_groups(Group.objects.all(), request.user), pk=pk) if pk else None
    before = group.name if group else ''     # forma tekshirilganda obyekt o'zgaradi, shuning uchun eski nom oldindan olinadi
    form = GroupForm(request.POST or None, instance=group)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        if not group:
            saved.branch = pick_branch(request.user)
        saved.save()
        audit.log(request, "Sinfni o'zgartirdi" if group else "Sinf qo'shdi", saved, label=saved.name, target_type='group',
                  details={'nom': audit.change(before, saved.name)} if group and before != saved.name else {})
        messages.success(request, 'Saqlandi.')
        return redirect('panel:groups')
    return render(request, 'panel/group_form.html', {'nav': 'groups', 'form': form, 'group': group,
                                                     'title': group.name if group else "Yangi sinf"})
