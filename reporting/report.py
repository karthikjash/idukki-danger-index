"""
Seasonal risk report generator (PDF + DOCX).

Builds an administrator-ready report for one locality or the whole district
from the same computed indices the dashboard shows. Two output formats:

  * PDF  - fpdf2 (pure Python)
  * DOCX - a minimal Office Open XML writer built on the stdlib zipfile
           module, so no python-docx/lxml dependency is required.

Content: headline tier, sub-scores, current weather, plain-language drivers,
7-day rainfall outlook, nearby past incidents, seasonal outlook (ENSO +
lightning) and tier guidance - formatted for submission to the District
Collector / KSDMA.
"""

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

_TIER_COLOURS = {'Low': (46, 204, 113), 'Moderate': (245, 166, 35),
                 'High': (231, 76, 60), 'Extreme': (195, 52, 94)}

# PDF fonts: embed DejaVu Sans (full Unicode) when available, otherwise fall
# back to core Helvetica (Latin-1) with any unsupported characters replaced.
_DEJAVU = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
_DEJAVU_B = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
_DEJAVU_I = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf'
PDF_FONT = 'DejaVu' if Path(_DEJAVU).exists() else 'Helvetica'


def _pdf_text(value):
    """Force a string into the font's character set for the PDF path."""
    s = str(value)
    if PDF_FONT == 'Helvetica':
        s = s.replace('—', '-').replace('–', '-').replace('’', "'").replace('‘', "'")
        s = s.replace('“', '"').replace('”', '"').replace('…', '...').replace('→', '->')
        return s.encode('latin-1', errors='replace').decode('latin-1')
    return s


def _sanitize_report(report: dict) -> dict:
    """Recursively sanitize strings for the PDF path (Latin-1 fallback)."""
    if PDF_FONT != 'Helvetica':
        return report

    def walk(node):
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            return _pdf_text(node)
        return node
    return walk(report)

# ------------------------------------------------------------------ content
def _colour_of(tier: str) -> tuple:
    return _TIER_COLOURS.get(tier, (100, 116, 139))


def _locality_rows(indices: dict, weather_meta: dict) -> list:
    """Flatten per-locality indices into stable report rows."""
    rows = []
    for name in sorted(indices.keys()):
        d = indices[name]
        w = d.get('weather', {})
        rows.append({
            'name': name,
            'tier': d.get('tier', 'Low'),
            'score': d.get('composite_score', 0.0),
            'rain_mm': w.get('rainfall_mm'),
            'wind': w.get('wind_mps'),
            'humidity': w.get('humidity_pct'),
            'cloud': w.get('cloud_cover_pct'),
            'source': d.get('data_source', 'synthetic'),
            'drivers': d.get('drivers', []),
            'env': d.get('environmental_severity', d.get('sub_scores', {})
                         .get('environmental_severity', 0)),
            'struct': d.get('structural_risk', d.get('sub_scores', {})
                            .get('structural_risk', 0)),
            'human': d.get('human_threat_level', d.get('sub_scores', {})
                           .get('human_threat_level', 0)),
        })
    return rows


def _district_summary(rows: list) -> dict:
    tiers = {'Low': 0, 'Moderate': 0, 'High': 0, 'Extreme': 0}
    total = 0.0
    worst = None
    for r in rows:
        tiers[r['tier']] = tiers.get(r['tier'], 0) + 1
        total += r['score']
        if worst is None or r['score'] > worst['score']:
            worst = r
    n = len(rows) or 1
    headline = next((t for t in ('Extreme', 'High', 'Moderate', 'Low')
                     if tiers.get(t, 0) > 0), 'Low')
    return {'headline': headline, 'avg': total / n, 'tiers': tiers,
            'worst': worst, 'generated': datetime.now().isoformat()}


def build_report(indices: dict, incidents=None, outlook=None) -> dict:
    """All content blocks for the report (shared by PDF/DOCX)."""
    rows = _locality_rows(indices, {})
    summary = _district_summary(rows)
    return {'title': 'Idukki District Monsoon Danger Report',
            'subtitle': 'Hyperlocal risk intelligence - inner Idukki panchayats',
            'generated': summary['generated'],
            'headline': summary['headline'],
            'district_avg': round(summary['avg'], 2),
            'tier_counts': summary['tiers'],
            'localities': rows,
            'worst': summary['worst'],
            'incidents': incidents,
            'outlook': outlook,
            }


# ---------------------------------------------------------------------- PDF
class _ReportPDF(FPDF):
    def header(self):
        self.set_font(PDF_FONT, 'B', 15)
        self.set_text_color(13, 19, 31)
        self.cell(0, 10, 'Idukki District Monsoon Danger Report', new_x='LMARGIN', new_y='NEXT')
        self.set_font(PDF_FONT, '', 9)
        self.set_text_color(100, 116, 139)
        self.cell(0, 5, 'Hyperlocal risk intelligence - inner Idukki panchayats', new_x='LMARGIN', new_y='NEXT')
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_font(PDF_FONT, 'I', 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, f'Generated {datetime.now():%d %b %Y %H:%M IST}  |  page {self.page_no()}', align='C')


def build_pdf(report: dict) -> bytes:
    report = _sanitize_report(report)
    pdf = _ReportPDF(format='A4')
    pdf.set_auto_page_break(auto=True, margin=20)
    if PDF_FONT == 'DejaVu':
        pdf.add_font('DejaVu', '', _DEJAVU)
        pdf.add_font('DejaVu', 'B', _DEJAVU_B)
        pdf.add_font('DejaVu', 'I', _DEJAVU_I)
    pdf.add_page()

    # district headline
    col = _colour_of(report['headline'])
    pdf.set_fill_color(*col)
    pdf.rect(0, pdf.get_y(), 4, 18, style='F')
    pdf.set_x(10)
    pdf.set_font(PDF_FONT, 'B', 24)
    pdf.set_text_color(*col)
    pdf.cell(0, 12, f"District risk: {report['headline']}", new_x='LMARGIN', new_y='NEXT')
    pdf.set_font(PDF_FONT, '', 10)
    pdf.set_text_color(51, 65, 85)
    t = report['tier_counts']
    pdf.cell(0, 7, f"Average danger score {report['district_avg']} / 1.0   |   "
                   f"Low {t['Low']}  -  Moderate {t['Moderate']}  -  High {t['High']}  -  Extreme {t['Extreme']}",
             new_x='LMARGIN', new_y='NEXT')
    pdf.ln(4)

    for r in report['localities']:
        col = _colour_of(r['tier'])
        pdf.set_font(PDF_FONT, 'B', 13)
        pdf.set_text_color(13, 19, 31)
        pdf.cell(0, 8, f"{r['name']}  -  {r['tier']}  (score {r['score']})", new_x='LMARGIN', new_y='NEXT')
        pdf.set_draw_color(*col)
        pdf.set_line_width(0.8)
        pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 90, pdf.get_y())
        pdf.ln(2)
        src = 'LIVE observations' if r['source'] == 'live' else 'MODELLED data (live feed unavailable)'
        pdf.set_font(PDF_FONT, '', 9)
        pdf.set_text_color(71, 85, 105)
        rain = r['rain_mm'] if r['rain_mm'] is not None else 'n/a'
        pdf.cell(0, 6, f"Today: rain {rain} mm | wind {r['wind']} m/s | humidity {r['humidity']}% | "
                       f"cloud {r['cloud']}% | {src}", new_x='LMARGIN', new_y='NEXT')
        pdf.set_text_color(51, 65, 85)
        for drv in r['drivers'][:3]:
            pdf.cell(0, 6, f"   -  {drv}", new_x='LMARGIN', new_y='NEXT')
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 6, f"Sub-scores  -  environmental {r['env']} | structural {r['struct']} | "
                       f"human threat {r['human']}", new_x='LMARGIN', new_y='NEXT')
        pdf.ln(3)

    if report.get('outlook'):
        ensn = report['outlook'].get('enso', {})
        if ensn.get('available'):
            pdf.set_font(PDF_FONT, 'B', 11)
            pdf.set_text_color(13, 19, 31)
            pdf.cell(0, 8, 'Seasonal context (ENSO)', new_x='LMARGIN', new_y='NEXT')
            pdf.set_font(PDF_FONT, '', 9)
            pdf.set_text_color(51, 65, 85)
            pdf.multi_cell(0, 5, f"{ensn['phase']} (ONI {ensn['oni']:+.2f} deg C, "
                                 f"season {ensn['latest_season']}). "
                                 f"{report['outlook'].get('monsoon_outlook', {}).get('text', '')}",
                           new_x='LMARGIN', new_y='NEXT')
            pdf.ln(2)

    if report.get('incidents') is not None and not report['incidents'].empty:
        pdf.set_font(PDF_FONT, 'B', 11)
        pdf.set_text_color(13, 19, 31)
        pdf.cell(0, 8, 'Recorded incidents 2004-2025 (sample register)', new_x='LMARGIN', new_y='NEXT')
        pdf.set_font(PDF_FONT, '', 9)
        pdf.set_text_color(51, 65, 85)
        for _, inc in report['incidents'].head(12).iterrows():
            pdf.cell(0, 6, f"   {inc['year']} | {inc['incident_type']} ({inc['severity']}) - "
                           f"{inc['location']}", new_x='LMARGIN', new_y='NEXT')

    pdf.set_text_color(100, 116, 139)
    pdf.set_y(-32)
    pdf.set_font(PDF_FONT, 'I', 8)
    pdf.multi_cell(0, 4, 'Forecast tool - not a guarantee. Follow official KSDMA / district warnings. '
                         'Sources: Open-Meteo, IMD categories, NOAA CPC ONI, KSDMA incident register (sample).',
                  new_x='LMARGIN', new_y='NEXT')
    return bytes(pdf.output())


# --------------------------------------------------------------------- DOCX
def _docx_escape(text: str) -> str:
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _docx_paragraph(text: str, bold: bool = False, size: int = 20,
                    colour: str = '1F2937', space_after: int = 120) -> str:
    style = f'<w:b/>' if bold else ''
    return (f'<w:p><w:pPr><w:spacing w:after="{space_after}"/></w:pPr>'
            f'<w:r><w:rPr>{style}<w:sz w:val="{size * 2}"/>'
            f'<w:color w:val="{colour}"/></w:rPr>'
            f'<w:t xml:space="preserve">{_docx_escape(text)}</w:t></w:r></w:p>')


def _docx_table(headers: list, rows: list) -> str:
    def cell(text, bold=False):
        return ('<w:tc><w:tcPr><w:tcW w:w="2200" w:type="dxa"/></w:tcPr>'
                f'<w:p><w:r><w:rPr>{"<w:b/>" if bold else ""}'
                f'<w:sz w:val="18"/></w:rPr>'
                f'<w:t xml:space="preserve">{_docx_escape(str(text))}</w:t></w:r></w:p></w:tc>')

    header = ''.join(cell(h, bold=True) for h in headers)
    body = ''.join(''.join(cell(c) for c in row) for row in rows)
    return (f'<w:tbl><w:tblPr><w:tblBorders>'
            + ''.join(f'<w:{"top" if s=="t" else "bottom" if s=="b" else "left" if s=="l" else "right"} '
                      f'w:val="single" w:sz="4" w:color="D1D5DB"/>' for s in 'tblr')
            + '</w:tblBorders></w:tblPr>'
            f'<w:tr>{header}</w:tr><w:tr>{body}</w:tr></w:tbl>')


def build_docx(report: dict) -> bytes:
    """Minimal .docx writer (zip of WordprocessingML), no external deps."""
    parts = []
    parts.append(_docx_paragraph(report['title'], bold=True, size=28))
    parts.append(_docx_paragraph(report['subtitle'], size=11, colour='6B7280'))
    parts.append(_docx_paragraph(
        f"Generated: {report['generated']}  |  "
        f"District risk: {report['headline']} (avg {report['district_avg']} / 1.0)",
        size=10, colour='374151'))
    t = report['tier_counts']
    parts.append(_docx_paragraph(
        f"Low {t['Low']} | Moderate {t['Moderate']} | High {t['High']} | Extreme {t['Extreme']}",
        size=10, colour='374151'))

    rows = [[r['name'], r['tier'], r['score'], r['rain_mm'], r['source']]
            for r in report['localities']]
    parts.append(_docx_table(['Locality', 'Risk', 'Score', 'Rain mm', 'Data'], rows))
    parts.append(_docx_paragraph('', size=4))

    for r in report['localities']:
        src = 'LIVE' if r['source'] == 'live' else 'MODELLED'
        parts.append(_docx_paragraph(f"{r['name']} - {r['tier']} ({r['score']}) [{src}]",
                                     bold=True, size=12))
        for drv in r['drivers'][:3]:
            parts.append(_docx_paragraph(f"- {drv}", size=10))

    ensn = (report.get('outlook') or {}).get('enso', {})
    if ensn.get('available'):
        parts.append(_docx_paragraph('Seasonal context (ENSO)', bold=True, size=12))
        parts.append(_docx_paragraph(
            f"{ensn['phase']} (ONI {ensn['oni']:+.2f} C). "
            f"{(report.get('outlook') or {}).get('monsoon_outlook', {}).get('text', '')}",
            size=10))

    document_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                    'wordprocessingml/2006/main">'
                    '<w:body>' + ''.join(parts) +
                    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                    '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
                    '</w:sectPr></w:body></w:document>')
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                     '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>')

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', document_xml)
    return buf.getvalue()


def generate(locality: str, fmt: str, indices: dict, incidents=None, outlook=None):
    """Generate a report; locality 'all' -> district report."""
    report = build_report(indices, incidents, outlook)
    if fmt == 'pdf':
        return build_pdf(report)
    return build_docx(report)
