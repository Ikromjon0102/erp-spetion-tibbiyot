"""Panelda «ish maydoni» (workspace): xodim qaysi tashkilot/filial bilan ishlayotganini tanlaydi.

Tanlov sessiyada saqlanadi (`panel_scope`: 'all' | 'org-<id>' | 'branch-<id>') va panelning HAMMA ro'yxati/hisobotiga o'zi qo'llanadi:
`org.scope.branch_ids()` tanlovni hisobga oladi, shuning uchun o'quvchilar, ustozlar, xodimlar, to'lovlar, xarajatlar... faqat tanlangan
joyniki bo'ladi. Faqat bitta filialga ruxsati bor xodimda tanlagich ko'rinmaydi.
"""
from dataclasses import dataclass, field

SESSION_KEY = 'panel_scope'


@dataclass
class Scope:
    kind: str = 'all'                 # all | org | branch
    org: object = None
    branch: object = None
    tree: list = field(default_factory=list)       # [{'org': Organization, 'branches': [Branch, ...]}] — ko'rish mumkin bo'lganlar

    @property
    def key(self):
        return 'all' if self.kind == 'all' else f'{self.kind}-{(self.branch or self.org).pk}'

    @property
    def label(self):
        if self.kind == 'branch':
            return f'{self.org.label} · {self.branch.name}'
        if self.kind == 'org':
            return self.org.label
        if len(self.tree) == 1:            # bitta tashkilot, bir nechta filial (masalan markaz direktori)
            return f"{self.tree[0]['org'].label} · barcha filiallar"
        return 'Hammasi'

    @property
    def selectable(self):
        return sum(len(o['branches']) for o in self.tree) > 1

    @property
    def multi_org(self):
        return len(self.tree) > 1

    @property
    def is_all(self):
        return self.kind == 'all'


def parse(value):
    kind, _, pk = (value or 'all').partition('-')
    if kind in ('org', 'branch') and pk.isdigit():
        return kind, int(pk)
    return 'all', None


def build_scope(user, raw):
    """Foydalanuvchi ko'ra oladigan filiallardan daraxt tuzadi va `raw` tanlovni tekshiradi (ruxsatsiz bo'lsa — 'Hammasi')."""
    from .models import Branch
    from .scope import branch_ids
    base = branch_ids(user)       # tanlov qo'llanishidan oldingi (asl) ruxsat
    qs = Branch.objects.filter(is_active=True).select_related('organization').order_by('organization__name', 'name')
    if base is not None:
        qs = qs.filter(pk__in=base)
    tree, seen = [], {}
    for b in qs:
        if b.organization_id not in seen:
            seen[b.organization_id] = {'org': b.organization, 'branches': []}
            tree.append(seen[b.organization_id])
        seen[b.organization_id]['branches'].append(b)
    scope = Scope(tree=tree)
    kind, pk = parse(raw)
    if kind == 'org' and pk in seen:
        scope.kind, scope.org = 'org', seen[pk]['org']
    elif kind == 'branch':
        for o in tree:
            for b in o['branches']:
                if b.pk == pk:
                    scope.kind, scope.org, scope.branch = 'branch', o['org'], b
    return scope


def scope_branch_ids(scope):
    """Tanlov bo'yicha filial id lari; None — cheklov yo'q (Hammasi)."""
    if scope.kind == 'branch':
        return [scope.branch.pk]
    if scope.kind == 'org':
        return [b.pk for o in scope.tree if o['org'].pk == scope.org.pk for b in o['branches']]
    return None
