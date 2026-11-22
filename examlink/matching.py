"""ERP o'quvchilarini exam o'quvchilari bilan sinf + ism bo'yicha juftlash (taklif; tasdiqni xodim beradi)."""
import re
from difflib import SequenceMatcher

THRESHOLD = 0.85
_APOS = re.compile(r"[ʻʼ‘’`´'\"]")


def normalize(name):
    """Imlo variantlarini tenglashtiradi: o'/g' belgilari, dj→j, x→h, q→k, so'zlar tartibi."""
    s = _APOS.sub('', (name or '').lower())
    s = s.replace('dj', 'j').replace('x', 'h').replace('q', 'k').replace('sh', 's').replace('ch', 'c')
    return ' '.join(sorted(re.findall(r'[a-z]+', s)))


def similarity(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def grade_of(label):
    m = re.match(r'\s*(\d+)', label or '')
    return int(m.group(1)) if m else None


def propose(erp_students, exam_students, threshold=THRESHOLD):
    """erp_students: [(id, full_name, group_name)], exam_students: [{'id','full_name','class_name',...}].
    Har ikki tomon bir martadan ishlatiladi (eng yuqori o'xshashlik avval). Qaytaradi:
    [{'erp': id, 'exam': dict, 'score': float, 'same_grade': bool}] — o'xshashlik kamayish tartibida."""
    cands = []
    for eid, ename, egroup in erp_students:
        g = grade_of(egroup)
        for x in exam_students:
            score = similarity(ename, x['full_name'])
            if score >= threshold:
                cands.append((score, g is not None and g == grade_of(x['class_name']), eid, x))
    cands.sort(key=lambda c: (-c[1], -c[0]))     # avval sinf mos kelganlar
    used_erp, used_exam, out = set(), set(), []
    for score, same, eid, x in cands:
        if eid in used_erp or x['id'] in used_exam:
            continue
        used_erp.add(eid)
        used_exam.add(x['id'])
        out.append({'erp': eid, 'exam': x, 'score': round(score, 2), 'same_grade': same})
    out.sort(key=lambda p: -p['score'])
    return out
