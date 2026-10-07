#!/usr/bin/env python3
"""Local scan OCR and page retrieval; OCR output is unreviewed evidence, not a ruling."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import sys
import unicodedata


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _init_worker(pdf):
    global document, engine
    import pymupdf
    from rapidocr_onnxruntime import RapidOCR
    document = pymupdf.open(pdf)
    engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1,
                      det_limit_side_len=1600)


def _ocr_page(number):
    import pymupdf
    import numpy as np
    page = document[number - 1]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    pixels = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    result, _ = engine(pixels[:, :, ::-1].copy())
    lines = [{'text': text, 'confidence': float(score), 'box': box}
             for box, text, score in (result or [])]
    return {'pdf_page': number, 'review_status': 'unreviewed_ocr',
            'render_size': [pix.width, pix.height], 'lines': lines,
            'text': '\n'.join(line['text'] for line in lines)}


def build(pdf, output, workers=2, resume=False):
    import pymupdf
    pdf, output = Path(pdf).resolve(), Path(output).resolve()
    if workers < 1 or workers > 8:
        raise ValueError('workers must be between 1 and 8')
    # Never reuse another scan's OCR or overwrite a nonempty directory.
    if output.exists() and any(output.iterdir()) and not resume:
        raise ValueError('Use a new or empty output directory')
    with pymupdf.open(pdf) as doc:
        total = len(doc)
    output.mkdir(parents=True, exist_ok=True)
    pages = output / 'pages'
    pages.mkdir(exist_ok=True)
    manifest = {'schema_version': 1, 'source_filename': pdf.name,
                'source_sha256': digest(pdf), 'pdf_pages': total,
                'ocr_engine': 'rapidocr_onnxruntime', 'ocr_version': version('rapidocr_onnxruntime'),
                'status': 'incomplete', 'review_status': 'unreviewed_ocr',
                'note': 'OCR覆盖率不证明原书完整或识别正确；书页码须另行核对。'}
    manifest_path = output / 'manifest.json'
    remaining = list(range(1, total + 1))
    if resume:
        old = json.loads(manifest_path.read_text(encoding='utf-8'))
        for key in ('source_sha256', 'pdf_pages', 'ocr_engine', 'ocr_version'):
            if old[key] != manifest[key]:
                raise ValueError('Resume source or OCR version mismatch')
        remaining = []
        for number in range(1, total + 1):
            page_file = pages / f'{number:04}.json'
            if not page_file.exists():
                remaining.append(number)
                continue
            item = json.loads(page_file.read_text(encoding='utf-8'))
            if item['pdf_page'] != number or not isinstance(item['text'], str):
                raise ValueError('Invalid cached OCR page')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                             initargs=(str(pdf),)) as pool:
        for item in pool.map(_ocr_page, remaining):
            (pages / f"{item['pdf_page']:04}.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2), encoding='utf-8')
            if item['pdf_page'] % 10 == 0 or item['pdf_page'] == total:
                print(f"OCR {item['pdf_page']}/{total}", file=sys.stderr, flush=True)
    with (output / '全文-OCR待校对.md').open('w', encoding='utf-8') as stream:
        stream.write('# 扫描件OCR工作文本（待逐条对照原页）\n\n')
        for number in range(1, total + 1):
            item = json.loads((pages / f'{number:04}.json').read_text(encoding='utf-8'))
            stream.write(f"## PDF第{number}页\n\n{item['text']}\n\n")
    manifest['status'] = 'ocr_complete'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def normalize(text):
    return ''.join(unicodedata.normalize('NFKC', text).casefold().split())


def search(index, query, limit=10):
    index = Path(index)
    manifest = json.loads((index / 'manifest.json').read_text(encoding='utf-8'))
    needle = normalize(query)
    if not needle or limit < 1:
        raise ValueError('Nonempty query and positive limit required')
    matches = []
    for file in sorted((index / 'pages').glob('*.json')):
        page = json.loads(file.read_text(encoding='utf-8'))
        if needle in normalize(page['text']):
            matches.append({'pdf_page': page['pdf_page'], 'text': page['text'],
                            'review_status': 'unreviewed_ocr'})
            if len(matches) == limit:
                break
    return {'source_sha256': manifest['source_sha256'], 'index_status': manifest['status'],
            'matches': matches, 'needs_visual_review': True,
            'note': '未命中不代表书中无此规则；OCR可能漏行、错字，引用须回原页。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('build')
    scan.add_argument('pdf', type=Path)
    scan.add_argument('output', type=Path)
    scan.add_argument('--workers', type=int, default=2)
    scan.add_argument('--resume', action='store_true', help='Resume only the same scan and OCR engine version')
    find = commands.add_parser('search')
    find.add_argument('index', type=Path)
    find.add_argument('query')
    find.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    try:
        result = (build(args.pdf, args.output, args.workers, args.resume) if args.command == 'build'
                  else search(args.index, args.query, args.limit))
    except (ValueError, OSError, ImportError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
