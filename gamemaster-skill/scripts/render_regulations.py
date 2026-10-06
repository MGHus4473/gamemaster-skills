#!/usr/bin/env python3
"""Render approved regulation content to md/txt/docx/pdf or LaTeX + PDF.

Business drafting and rule verification remain the agent's responsibility.
See references/regulation-output.md for the JSON contract and dependencies.
"""
import argparse
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


STYLE_PATH = Path(__file__).resolve().parent.parent / 'assets/regulation-word-style.json'
PARAGRAPH_STYLES = {'body', 'lead', 'issuer', 'date', 'note'}


def merge_style(base, override, path='word_style'):
    if not isinstance(override, dict):
        raise ValueError(path + ' 必须是对象。')
    result = json.loads(json.dumps(base))
    for key, value in override.items():
        if key not in base:
            raise ValueError(f'不支持的样式字段：{path}.{key}')
        result[key] = merge_style(base[key], value, path + '.' + key) if isinstance(base[key], dict) else value
    return result


def resolve_word_style(d, override=None, cjk_font=None, latin_font=None):
    style = merge_style(json.loads(STYLE_PATH.read_text(encoding='utf-8')), d.get('word_style', {}))
    if override is not None:
        style = merge_style(style, override)
    if 'header_text' not in d.get('word_style', {}) and 'header_text' not in (override or {}):
        style['header_text'] = d.get('document_label', '竞赛规程')
    if cjk_font:
        style['fonts'].update(cjk=cjk_font, heading_cjk=cjk_font)
    if latin_font:
        style['fonts']['latin'] = latin_font
    def number(value, low, high, name):
        if type(value) not in (int, float) or not low <= value <= high:
            raise ValueError(f'{name} 必须为 {low} 至 {high} 的数字。')
    page = style['page']
    for key in ('width_mm', 'height_mm'):
        number(page[key], 100, 420, key)
    for key, value in page['margins_mm'].items():
        number(value, 5, 60, 'margins_mm.' + key)
    for key in ('header_mm', 'footer_mm'):
        number(page[key], 2, 40, key)
    if page['header_mm'] >= page['margins_mm']['top'] or page['footer_mm'] >= page['margins_mm']['bottom']:
        raise ValueError('页眉/页脚距离须小于对应的上/下页边距。')
    if page['width_mm']-page['margins_mm']['left']-page['margins_mm']['right'] < 60 or page['height_mm']-page['margins_mm']['top']-page['margins_mm']['bottom'] < 60:
        raise ValueError('页边距导致正文区域过小。')
    for key, value in style['fonts'].items():
        if not isinstance(value, str) or not value.strip() or re.search(r'[\x00-\x1f]', value):
            raise ValueError('字体名称须为非空单行文字：' + key)
    for key, value in style['sizes_pt'].items():
        number(value, 6, 48, 'sizes_pt.' + key)
        if value * 2 != int(value * 2):
            raise ValueError('Word字号须以0.5pt递增。')
    for section in ('paragraph', 'table'):
        number(style[section]['line_multiple'], 1, 3, section + '.line_multiple')
    number(style['paragraph']['space_after_pt'], 0, 36, 'space_after_pt')
    for key in ('first_line_chars', 'clause_level_indent_chars'):
        number(style['paragraph'][key], 0, 4, key)
    number(style['table']['padding_mm'], 0.5, 6, 'table.padding_mm')
    for key in ('header_fill', 'border_color'):
        if not isinstance(style['table'][key], str) or not re.fullmatch('[0-9A-Fa-f]{6}', style['table'][key]):
            raise ValueError('表格颜色须为6位RGB值。')
    if type(style['table']['allow_row_split']) is not bool or type(style['page_numbers']) is not bool:
        raise ValueError('分页开关须为布尔值。')
    if not isinstance(style['header_text'], str) or re.search(r'[\x00-\x1f]', style['header_text']):
        raise ValueError('页眉须为单行文本，可为空字符串。')
    return style


def walk_blocks(d):
    def walk(items):
        for block in items:
            yield block
            if block['type'] == 'appendix':
                yield from walk(block['blocks'])
    for section in d['sections']:
        yield from walk(section['blocks'])


def validate(d):
    def string(x, multiline=True):
        if not isinstance(x, str) or not x.strip():
            raise ValueError('标题、段落和单元格须为非空字符串（空单元格用“—”）。')
        if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', x):
            raise ValueError('文字中含不可输出的控制字符。')
        if not multiline and any(c in x for c in '\n\r\t'):
            raise ValueError('标题、编号和表格标题须为单行文字。')
    def keys(obj, allowed):
        if not isinstance(obj, dict) or set(obj)-set(allowed):
            raise ValueError('不支持的字段或非对象：' + repr(set(obj)-set(allowed) if isinstance(obj, dict) else obj))
    def level(value):
        if type(value) is not int or value not in (1, 2, 3):
            raise ValueError('层级 level 须为 1、2 或 3。')
    keys(d, {'title','subtitle','document_label','status','pending','sections','word_style'})
    string(d.get('title'), False)
    for key in ('document_label', 'subtitle'):
        if key in d:
            string(d[key], False)
    if d.get('status') not in ('draft', 'final'):
        raise ValueError('status 必须为 draft 或 final。')
    pending = d.get('pending', [])
    if not isinstance(pending, list):
        raise ValueError('pending 必须为字符串数组。')
    for item in pending:
        string(item)
    style = resolve_word_style(d)
    content_width = style['page']['width_mm']-style['page']['margins_mm']['left']-style['page']['margins_mm']['right']
    def blocks(items, in_appendix=False):
        if not isinstance(items, list) or not items:
            raise ValueError('每节/附件 blocks 不能为空。')
        for b in items:
            if not isinstance(b, dict):
                raise ValueError('blocks 元素须为对象。')
            kind = b.get('type')
            if kind == 'paragraph':
                keys(b, {'type','text','style'}); string(b.get('text'))
                if b.get('style', 'body') not in PARAGRAPH_STYLES:
                    raise ValueError('未知段落样式；支持body/lead/issuer/date/note。')
            elif kind == 'heading':
                keys(b, {'type','text','level'}); string(b.get('text'), False); level(b.get('level'))
            elif kind == 'clause':
                keys(b, {'type','text','label','level'}); string(b.get('text'), False); string(b.get('label'), False); level(b.get('level'))
                if b['label'] != b['label'].strip() or len(b['label']) > 12:
                    raise ValueError('条目编号须无首尾空格且不超过12字符；对齐由缩进完成。')
            elif kind == 'table':
                keys(b, {'type','headers','rows','caption','column_widths_mm','allow_row_split'})
                h, rows = b.get('headers'), b.get('rows')
                if not isinstance(h, list) or not h or not isinstance(rows, list) or not rows:
                    raise ValueError('表格须有 headers 和 rows。')
                for cell in h:
                    string(cell)
                for row in rows:
                    if not isinstance(row, list) or len(row) != len(h):
                        raise ValueError('表格列数不一致。')
                    for cell in row:
                        string(cell)
                if 'caption' in b:
                    string(b['caption'], False)
                if 'column_widths_mm' in b:
                    widths = b['column_widths_mm']
                    if not isinstance(widths, list) or len(widths) != len(h) or any(type(w) not in (int,float) or not math.isfinite(w) or w < 10 for w in widths) or sum(widths) > content_width + 0.01:
                        raise ValueError('column_widths_mm 须每列至少10mm、与列数一致且总宽不超过正文宽度。')
                elif content_width / len(h) < 10:
                    raise ValueError('默认均分列宽小于10mm；请拆分表格或明确适用的页面和列宽。')
                if 'allow_row_split' in b and type(b['allow_row_split']) is not bool:
                    raise ValueError('allow_row_split 须为布尔值。')
            elif kind == 'page_break':
                keys(b, {'type'})
            elif kind == 'appendix':
                keys(b, {'type','title','blocks'}); string(b.get('title'), False)
                if in_appendix:
                    raise ValueError('附件块不接受嵌套附件；使用附件内标题。')
                blocks(b.get('blocks'), True)
            else:
                raise ValueError('不支持的块类型：' + str(kind) + '；不会静默忽略。')
    if not isinstance(d.get('sections'), list) or not d['sections']:
        raise ValueError('sections 不能为空。')
    for section in d['sections']:
        keys(section, {'heading','level','blocks'}); string(section.get('heading'), False)
        level(section.get('level', 1)); blocks(section.get('blocks'))
    if d['status'] == 'final' and (pending or re.search(r'【待确认[:：]|XXX|待填写', json.dumps(d, ensure_ascii=False))):
        raise ValueError('正式稿仍有待确认项或占位内容，请先补齐或标为 draft。')
    d = json.loads(json.dumps(d, ensure_ascii=False))
    if pending:
        d['sections'].append({'heading': '编制备注：待确认事项', 'blocks': [
            {'type': 'paragraph', 'text': f'{i+1}. {item}'} for i, item in enumerate(pending)]})
    return d


def ensure_format_features(d, fmt):
    """Old PDF/TeX paths preserve the old contract and explicitly reject new layout semantics."""
    if fmt not in ('pdf', 'latex'):
        return
    advanced = ('subtitle' in d or 'word_style' in d or any(s.get('level', 1) != 1 for s in d['sections']))
    for b in walk_blocks(d):
        advanced |= b['type'] not in ('paragraph', 'table')
        advanced |= b.get('style', 'body') != 'body'
        advanced |= any(k in b for k in ('caption', 'column_widths_mm', 'allow_row_split'))
    if advanced:
        raise ValueError('此PDF/LaTeX后端尚未支持新分级条款、附件或自定义版式。请先生成Word并在本地办公软件导出PDF，或另行实现相应后端；不会删除内容降级输出。')

def label(d):
    return '草案｜待确认内容不可作为正式发布依据' if d['status'] == 'draft' else d.get('document_label', '竞赛规程')


def markdown(d, plain=False):
    def text(t):
        return t if plain else re.sub(r'([\\`*_{}\[\]()#+.!|<>~&-])', r'\\\1', t)
    def cell(t):
        return text(t).replace('\n', '<br>')
    lines = [text(d['title']) if plain else '# ' + text(d['title']), '']
    if d.get('subtitle'):
        lines += [text(d['subtitle']), '']
    lines += [text(label(d)), '']
    def blocks(items):
        for b in items:
            kind = b['type']
            if kind == 'paragraph':
                lines.extend([text(b['text']), ''])
            elif kind == 'heading':
                lines.extend([text(b['text']) if plain else '#' * (b['level'] + 1) + ' ' + text(b['text']), ''])
            elif kind == 'clause':
                # Authored numbering is semantic content, not a Markdown automatic list.
                lines.extend([text(b['label']) + ' ' + text(b['text']), ''])
            elif kind == 'page_break':
                lines.extend(['\f' if plain else '<!-- page break -->', ''])
            elif kind == 'appendix':
                lines.extend(['\f' if plain else '<!-- page break -->',
                              text(b['title']) if plain else '## ' + text(b['title']), ''])
                blocks(b['blocks'])
            elif kind == 'table':
                if b.get('caption'):
                    lines.extend([text(b['caption']), ''])
                if plain:
                    lines.extend('；'.join(f'{h}：{v}' for h, v in zip(b['headers'], row)) for row in b['rows'])
                else:
                    lines.extend(['| ' + ' | '.join(cell(x) for x in b['headers']) + ' |',
                                  '| ' + ' | '.join('---' for _ in b['headers']) + ' |'])
                    lines.extend('| ' + ' | '.join(cell(x) for x in row) + ' |' for row in b['rows'])
                lines.append('')
    for section in d['sections']:
        lines.extend([text(section['heading']) if plain else '#' * (section.get('level', 1) + 1) + ' ' + text(section['heading']), ''])
        blocks(section['blocks'])
    return '\n'.join(lines)


def pdf(d, target, font):
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, CondPageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    if not font or not Path(font).is_file():
        raise ValueError('PDF 需要中文 TTF 字体，请用 --font-file 指定。')
    pdfmetrics.registerFont(TTFont('RegCJK', font))
    glyphs = pdfmetrics.getFont('RegCJK').face.charToGlyph
    # Standard PDF Helvetica includes Windows-1252 punctuation (e.g. em dash).
    def latin(c):
        try:
            return len(c.encode('cp1252')) == 1
        except UnicodeEncodeError:
            return False
    missing = sorted({c for c in json.dumps(d, ensure_ascii=False) if not latin(c) and ord(c) not in glyphs})
    if missing:
        raise ValueError('所选中文字体缺少字符：' + ''.join(missing))
    body = ParagraphStyle('body', fontName='RegCJK', fontSize=11, leading=18, wordWrap='CJK', spaceAfter=7)
    heading = ParagraphStyle('heading', parent=body, fontSize=14, leading=21, spaceBefore=12)
    title = ParagraphStyle('title', parent=body, fontSize=19, leading=29, alignment=1, spaceAfter=16)
    cellstyle = ParagraphStyle('cell', parent=body, fontSize=9, leading=14, spaceAfter=0)
    def p(t, style=body):
        # Some CJK fallback fonts intentionally omit Latin glyphs and digits.
        from itertools import groupby
        text = ''.join('<font name="Helvetica">'+html.escape(''.join(chars))+'</font>'
                       if is_latin else html.escape(''.join(chars))
                       for is_latin, chars in groupby(t, lambda c: c != '\n' and latin(c)))
        return Paragraph(text.replace('\n', '<br/>'), style)
    story = [p(d['title'], title), p(label(d)), Spacer(1, 6)]
    for s in d['sections']:
        story.append(CondPageBreak(90))
        story.append(p(s['heading'], heading))
        for b in s['blocks']:
            if b['type'] == 'paragraph':
                story.append(p(b['text']))
            else:
                data = [[p(x, cellstyle) for x in row] for row in [b['headers']] + b['rows']]
                t = LongTable(data, colWidths=[(A4[0]-108)/len(b['headers'])]*len(b['headers']), repeatRows=1)
                t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.4,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eeeeee')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
                story += [t, Spacer(1, 8)]
    def footer(c, doc):
        c.setFont('Helvetica', 9)
        c.drawCentredString(A4[0]/2, 28, str(doc.page))
    SimpleDocTemplate(str(target), pagesize=A4, leftMargin=54, rightMargin=54, topMargin=48, bottomMargin=48, title=d['title']).build(story, onFirstPage=footer, onLaterPages=footer)


def tex_escape(s):
    chars = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(chars.get(c, c) for c in s).replace('\n', r'\newline ')


def latex(d, font):
    if not re.fullmatch(r'[\w .-]+', font):
        raise ValueError('中文字体名称只接受文字、数字、空格、点和连字符。')
    e = tex_escape
    lines = [r'\documentclass[UTF8,fontset=none,12pt,a4paper]{ctexart}',
             r'\usepackage[margin=22mm]{geometry}', r'\usepackage{longtable,array}',
             r'\setCJKmainfont{' + font + r'}', r'\setCJKsansfont{' + font + r'}',
             r'\setCJKmonofont{' + font + r'}', r'\setlength{\parindent}{0pt}',
             r'\xeCJKDeclareCharClass{Default}{"2013}', r'\xeCJKDeclareCharClass{Default}{"2014}',
             r'\setlength{\parskip}{0.5em}', r'\emergencystretch=3em',
             r'\begin{document}', r'\begin{center}\LARGE ' + e(d['title']) + r'\end{center}', e(label(d))]
    for s in d['sections']:
        lines.append(r'\section*{' + e(s['heading']) + '}')
        for b in s['blocks']:
            if b['type'] == 'paragraph':
                lines += [e(b['text']), '']
            else:
                n = len(b['headers'])
                width = f'{0.92/n:.5f}\\textwidth-2\\tabcolsep'
                cols = '|'.join(r'>{\raggedright\arraybackslash}p{\dimexpr ' + width + r'\relax}' for _ in range(n))
                row = lambda cells: ' & '.join(e(x) for x in cells) + r' \\ \hline'
                lines += [r'\begin{longtable}{|' + cols + r'|}\hline', row(b['headers']), r'\endfirsthead', r'\hline', row(b['headers']), r'\endhead']
                lines += [row(r) for r in b['rows']]
                lines.append(r'\end{longtable}')
    return '\n'.join(lines + [r'\end{document}', ''])


def compile_tex(source, engine, bundle=None):
    exe = shutil.which(engine) if engine else shutil.which('xelatex') or shutil.which('tectonic')
    if not exe:
        raise ValueError('缺少 XeLaTeX/Tectonic；已保留 .tex，尚未完成渲染。')
    if 'tectonic' in Path(exe).name:
        cmd = [exe, '--untrusted', '--only-cached', '--keep-logs', '--outdir', str(source.parent), str(source)]
        if bundle:
            if not Path(bundle).is_file():
                raise ValueError('离线编译只接受已有本地宏包文件，不访问远程bundle。')
            cmd[1:1] = ['--bundle', bundle]
    else:
        cmd = [exe, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', '-output-directory', str(source.parent), str(source)]
    log = source.with_suffix('.build.log')
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=240, cwd=source.parent)
    except subprocess.TimeoutExpired as ex:
        def decode(x):
            return x.decode('utf-8', errors='replace') if isinstance(x, bytes) else x or ''
        log.write_text(decode(ex.stdout) + decode(ex.stderr), encoding='utf-8')
        raise ValueError(f'LaTeX 编译超时，源文件与日志已保留：{log}') from ex
    log.write_text(r.stdout + r.stderr, encoding='utf-8')
    if r.returncode or not source.with_suffix('.pdf').exists():
        raise ValueError(f'LaTeX 编译失败，源文件与日志已保留：{log}')
    if 'Missing character:' in r.stdout + r.stderr + (source.with_suffix('.log').read_text(errors='replace') if source.with_suffix('.log').exists() else ''):
        raise ValueError(f'LaTeX 出现缺字，须更换字体后交付；检查 {log}')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('--format', required=True, choices=['md', 'txt', 'docx', 'pdf', 'latex'])
    p.add_argument('--output', required=True, type=Path, help='目标文件；latex 使用 .tex 后缀，同时生成同名 .pdf')
    p.add_argument('--font-file', default=os.environ.get('GAMEMASTER_FONT_FILE'))
    p.add_argument('--cjk-font', default=None, help='Word中文字体覆盖；LaTeX默认Droid Sans Fallback')
    p.add_argument('--latin-font', default=None, help='Word西文字体覆盖')
    p.add_argument('--style-profile', type=Path, help='Word样式JSON覆盖，优先于输入word_style')
    p.add_argument('--tex-engine', default=None)
    p.add_argument('--tex-bundle', default=None, help='可选 Tectonic 本地宏包路径；默认仅使用离线缓存')
    a = p.parse_args()
    suffix = '.tex' if a.format == 'latex' else '.'+a.format
    if a.output.suffix.lower() != suffix:
        p.error(f'输出后缀须为 {suffix}')
    targets = [a.output] + ([a.output.with_suffix('.pdf')] if a.format == 'latex' else [])
    if any(x.exists() for x in targets):
        p.error('目标文件已存在，请换用新版本文件名。')
    try:
        raw = json.loads(a.input.read_text(encoding='utf-8'))
        if not isinstance(raw, dict):
            raise ValueError('文档JSON须为对象。')
        if (a.style_profile or a.latin_font) and a.format != 'docx':
            raise ValueError('--style-profile/--latin-font 仅适用于Word；不会静默忽略。')
        if a.format == 'docx':
            override = json.loads(a.style_profile.read_text(encoding='utf-8')) if a.style_profile else None
            word_style = resolve_word_style(raw, override, a.cjk_font, a.latin_font)
            # User layout must govern width validation, including layouts wider than defaults.
            raw = dict(raw, word_style=word_style)
        d = validate(raw)
        ensure_format_features(d, a.format)
        if a.format == 'docx':
            d['_word_style'] = word_style
        a.output = a.output.resolve()
        a.output.parent.mkdir(parents=True, exist_ok=True)
        if a.format in ('md','txt'):
            a.output.write_text(markdown(d, a.format == 'txt'), encoding='utf-8')
        elif a.format == 'pdf':
            pdf(d, a.output, a.font_file)
        elif a.format == 'docx':
            with tempfile.TemporaryDirectory(prefix='gamemaster-docx-') as tmp:
                data = Path(tmp)/'document.json'
                data.write_text(json.dumps(d, ensure_ascii=False), encoding='utf-8')
                subprocess.run(['node', str(Path(__file__).with_name('render_regulations.cjs')), str(data), str(a.output)], check=True, timeout=60)
        else:
            a.output.write_text(latex(d, a.cjk_font or 'Droid Sans Fallback'), encoding='utf-8')
            compile_tex(a.output, a.tex_engine, a.tex_bundle)
        print(json.dumps({'format': a.format, 'files': [str(x.resolve()) for x in targets]}, ensure_ascii=False))
    except (ValueError, KeyError, TypeError, ImportError, OSError, subprocess.SubprocessError) as ex:
        print(f'生成失败：{ex}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
