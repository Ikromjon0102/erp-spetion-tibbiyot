"""Hisobotlarni Excel (.xlsx) va PDF ko'rinishiga chiqarish."""
import os
from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SCHOOL = "Spetion — tibbiyotga ixtisoslashgan xususiy maktab"


def money(v):
    return f'{int(Decimal(v)):,}'.replace(',', ' ')


def display(value, kind):
    """Ekran va PDF uchun matn."""
    if value is None or value == '':
        return ''
    if kind == 'money':
        return money(value)
    if kind == 'date' and isinstance(value, date):
        return f'{value:%d.%m.%Y}'
    if kind == 'pct':
        return f'{Decimal(value).normalize():f}%'
    return str(value)


def xlsx_bytes(report):
    wb = Workbook()
    ws = wb.active
    ws.title = report['title'][:30]
    green, thin = PatternFill('solid', fgColor='166534'), Side(style='thin', color='C9D6CD')
    ncols = len(report['headers'])
    ws.cell(1, 1, f"{SCHOOL}").font = Font(size=10, color='666666')
    ws.cell(2, 1, report['title']).font = Font(size=15, bold=True)
    ws.cell(3, 1, report['subtitle']).font = Font(size=10, color='666666')
    for c, h in enumerate(report['headers'], 1):
        cell = ws.cell(5, c, h)
        cell.font, cell.fill = Font(bold=True, color='FFFFFF'), green
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    row_no = 6
    for r in report['rows']:
        for c, (value, kind) in enumerate(zip(r, report['kinds']), 1):
            cell = ws.cell(row_no, c, float(value) if isinstance(value, Decimal) and kind != 'pct' else (float(value) if isinstance(value, Decimal) else value))
            cell.border = Border(bottom=thin)
            if kind == 'money':
                cell.number_format, cell.alignment = '#,##0', Alignment(horizontal='right')
            elif kind == 'date':
                cell.number_format = 'DD.MM.YYYY'
            elif kind == 'pct':
                cell.number_format = '0.##"%"'
        row_no += 1
    if report['totals']:
        for c, (value, kind) in enumerate(zip(report['totals'], report['kinds']), 1):
            cell = ws.cell(row_no, c, float(value) if isinstance(value, Decimal) else value)
            cell.font, cell.fill = Font(bold=True), PatternFill('solid', fgColor='ECF6EF')
            if kind == 'money':
                cell.number_format, cell.alignment = '#,##0', Alignment(horizontal='right')
        row_no += 1
    if report['summary']:
        row_no += 1
        for label, value in report['summary']:
            ws.cell(row_no, 1, label).font = Font(bold=True)
            cell = ws.cell(row_no, 2, float(value))
            cell.number_format = '#,##0'
            row_no += 1
    for c in range(1, ncols + 1):
        width = max([len(str(report['headers'][c - 1]))] + [len(display(r[c - 1], report['kinds'][c - 1])) for r in report['rows']] + [8])
        ws.column_dimensions[get_column_letter(c)].width = min(width + 3, 46)
    ws.freeze_panes = 'A6'
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


_FONT = None


def _fonts():
    """Unicode (o', g', kirill) uchun tizim shriftini topadi; bo'lmasa Helvetica."""
    global _FONT
    if _FONT:
        return _FONT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    candidates = [
        ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('/usr/share/fonts/dejavu/DejaVuSans.ttf', '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf'),
        ('/Library/Fonts/Arial.ttf', '/Library/Fonts/Arial Bold.ttf'),
    ]
    for regular, bold in candidates:
        if os.path.exists(regular) and os.path.exists(bold):
            pdfmetrics.registerFont(TTFont('AppSans', regular))
            pdfmetrics.registerFont(TTFont('AppSans-Bold', bold))
            _FONT = ('AppSans', 'AppSans-Bold')
            return _FONT
    _FONT = ('Helvetica', 'Helvetica-Bold')
    return _FONT


def pdf_bytes(report):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    regular, bold = _fonts()
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=report['title'])
    grey = ParagraphStyle('g', fontName=regular, fontSize=8.5, textColor=colors.HexColor('#666666'))
    title = ParagraphStyle('t', fontName=bold, fontSize=16, spaceAfter=2)
    cell = ParagraphStyle('c', fontName=regular, fontSize=8, leading=10)
    cell_b = ParagraphStyle('cb', fontName=bold, fontSize=8, leading=10)
    head = ParagraphStyle('h', fontName=bold, fontSize=8, leading=10, textColor=colors.white)

    def para(text, kind, style):
        p = Paragraph(str(text).replace('&', '&amp;').replace('<', '&lt;'), style)
        if kind in ('money', 'int', 'pct'):
            p.style = ParagraphStyle('r', parent=style, alignment=2)
        return p

    data = [[Paragraph(h, head) for h in report['headers']]]
    for r in report['rows']:
        data.append([para(display(v, k), k, cell) for v, k in zip(r, report['kinds'])])
    if report['totals']:
        data.append([para(display(v, k), k, cell_b) for v, k in zip(report['totals'], report['kinds'])])
    usable = landscape(A4)[0] - 24 * mm
    weights = [3 if k == 'text' else 1.4 for k in report['kinds']]
    widths = [usable * w / sum(weights) for w in weights]
    table = Table(data, colWidths=widths, repeatRows=1)
    style = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#166534')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
             ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F8F4')]),
             ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#C9D6CD')),
             ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]
    if report['totals']:
        style.append(('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ECF6EF')))
    table.setStyle(TableStyle(style))
    story = [Paragraph(SCHOOL, grey), Paragraph(report['title'], title), Paragraph(report['subtitle'], grey), Spacer(1, 8)]
    story.append(table if report['rows'] else Paragraph("Ma'lumot yo'q", grey))
    for label, value in report['summary']:
        story += [Spacer(1, 4), Paragraph(f'<b>{label}:</b> {money(value)} so\'m', ParagraphStyle('s', fontName=regular, fontSize=9))]

    def footer(canvas, doc_):
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(colors.HexColor('#888888'))
        canvas.drawRightString(landscape(A4)[0] - 12 * mm, 7 * mm, f'{doc_.page}-bet')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
