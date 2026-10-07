#!/usr/bin/env python3
"""Offline, date-aware retrieval of reviewed badminton rule evidence, not an umpire."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import unicodedata

DATABASE = Path(__file__).resolve().parents[1] / 'references/badminton/knowledge.json'
RULE_KINDS = {'rules', 'guidance', 'rulebook'}
AUTHORITIES = {'BWF', 'CBA', 'all'}


def printed_page(source: dict, pdf_page: int):
    for segment in source.get('page_segments', []):
        if segment['pdf_start'] <= pdf_page <= segment['pdf_end']:
            return segment['printed_start'] + pdf_page - segment['pdf_start']
    return None


def iso_date(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('日期必须使用 YYYY-MM-DD')
    return date.fromisoformat(value)


def load_knowledge(path: Path = DATABASE) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported knowledge schema')
    iso_date(data['checked_on'])
    sources = {}
    for source in data['sources']:
        sid = source['id']
        if sid in sources or source['organization'] not in {'BWF', 'CBA'}:
            raise ValueError('Duplicate source or invalid authority')
        sources[sid] = source
        for field in ('checked_on', 'effective_from', 'effective_until', 'published_on'):
            if source.get(field):
                iso_date(source[field])
        if source.get('effective_until') and (not source.get('effective_from') or
                source['effective_until'] < source['effective_from']):
            raise ValueError('Invalid effective date range')
        for artifact in [source, *source.get('attachments', [])]:
            if artifact.get('cache_file'):
                name = artifact['cache_file']
                if Path(name).name != name or not re.fullmatch(r'[a-zA-Z0-9_.-]+', name):
                    raise ValueError('Cache name must be a plain filename')
                if not re.fullmatch(r'[0-9a-f]{64}', artifact.get('sha256', '')):
                    raise ValueError('Cached evidence requires SHA-256')
        if source.get('page_segments'):
            seen_pdf, seen_printed = set(), set()
            for segment in source['page_segments']:
                first, last, start = (segment[k] for k in ('pdf_start', 'pdf_end', 'printed_start'))
                if any(type(n) is not int for n in (first, last, start)) or not 1 <= first <= last <= source['pages'] or start < 1:
                    raise ValueError('Invalid scan page map')
                for pdf in range(first, last + 1):
                    printed = start + pdf - first
                    if pdf in seen_pdf or printed in seen_printed or printed in source.get('missing_printed_pages', []):
                        raise ValueError('Overlapping page map or mapping into a missing page')
                    seen_pdf.add(pdf)
                    seen_printed.add(printed)
    ids = set()
    for card in data['cards']:
        if card['id'] in ids or not card.get('citations'):
            raise ValueError('Duplicate card or missing evidence')
        ids.add(card['id'])
        cited = set()
        for citation in card['citations']:
            source = sources[citation['source']]
            cited.add(source['id'])
            if not citation['clause']:
                raise ValueError('Missing clause or section locator')
            for page in citation['pages']:
                if type(page) is not int or not source.get('pages') or not 1 <= page <= source['pages']:
                    raise ValueError('Page outside verified source')
            if source.get('verification') == 'partial_scan_reviewed':
                if card.get('review_status') != 'visually_verified' or not citation['pages']:
                    raise ValueError('Scan citation requires visual review and page locators')
                if not set(citation['pages']) <= set(source['reviewed_pdf_pages']):
                    raise ValueError('Scan citation outside visually reviewed pages')
                expected = [printed_page(source, p) for p in citation['pages']]
                if citation.get('printed_pages') != expected:
                    raise ValueError('Printed and PDF page locators disagree')
        if not set(card.get('required_sources', [])) <= cited:
            raise ValueError('Required source must have a citation')
    return data


def source_status(source: dict, on: str) -> str:
    iso_date(on)
    if source['verification'] == 'unavailable':
        return 'unavailable'
    if source.get('published_on') and source['published_on'] > on:
        return 'not_yet_published'
    if source.get('published_month') and source['published_month'] > on[:7]:
        return 'not_yet_published'
    if source['kind'] in {'historical_summary', 'historical_rulebook'}:
        return 'historical_reference'
    if source['kind'] not in RULE_KINDS or not source.get('effective_from'):
        return 'reference_only'
    if source['effective_from'] > on:
        return 'future'
    if source.get('effective_until') and source['effective_until'] < on:
        return 'superseded_in_snapshot'
    return 'in_force_in_snapshot'


def envelope(data: dict, on: str, authority: str) -> dict:
    iso_date(on)
    if authority not in AUTHORITIES:
        raise ValueError('Unknown authority')
    warnings = ['离线结果依据已核验快照及已知生效时间线；日期匹配不证明已联网确认最新规则，也不证明本赛事采用该规则。']
    if on > data['checked_on']:
        warnings.append('比赛日期晚于知识库核验日：正式使用前核对协会后续修订；未来版本按已公布计划选出。')
    if authority in {'CBA', 'all'}:
        warnings.append('已核验中国羽协2023版扫描件的选定条款，扫描件有缺页；2025规则书全文仍未取得。2023版依据不自动证明现行适用，须核对后续中国羽协文件。')
    return {'on': on, 'checked_on': data['checked_on'], 'authority': authority, 'warnings': warnings}


def status(data: dict, on: str, authority: str = 'all') -> dict:
    result = envelope(data, on, authority)
    result['sources'] = [dict(s, status=source_status(s, on)) for s in data['sources']
                         if authority == 'all' or s['organization'] == authority]
    return result


def normalized(value: str) -> str:
    return re.sub(r'[^a-z0-9\u3400-\u9fff.]+', '', unicodedata.normalize('NFKC', value).casefold())


def search(data: dict, query: str, on: str, authority: str = 'all',
           include_inactive: bool = False, limit: int = 6) -> dict:
    result = envelope(data, on, authority)
    needle = normalized(query)
    if not needle or type(limit) is not int or limit < 1:
        raise ValueError('需要非空检索词及正整数limit')
    sources = {s['id']: s for s in data['sources']}
    matches = []
    for card in data['cards']:
        citations = []
        for ref in card['citations']:
            source = sources[ref['source']]
            if authority != 'all' and source['organization'] != authority:
                continue
            citations.append(dict(ref, title=source['title'], version=source['version'],
                                  organization=source['organization'], host=source['host'],
                                  url=source['url'], checked_on=source['checked_on'],
                                  cache_file=source.get('cache_file'),
                                  verification=source['verification'],
                                  effective_from=source['effective_from'],
                                  status=source_status(source, on)))
        if not citations:
            continue
        active = [c for c in citations if c['status'] == 'in_force_in_snapshot']
        required = set(card.get('required_sources', []))
        rule_evidence = bool(active) and required <= {c['source'] for c in active}
        statuses = {c['status'] for c in citations}
        if rule_evidence:
            disposition = 'applicable_snapshot'
        elif 'future' in statuses or 'not_yet_published' in statuses:
            disposition = 'future'
        elif 'reference_only' in statuses:
            disposition = 'reference_only'
        elif 'historical_reference' in statuses:
            disposition = 'historical_reference'
        elif 'unavailable' in statuses:
            disposition = 'unavailable'
        else:
            disposition = 'superseded_in_snapshot'
        if not include_inactive and disposition in {'future', 'superseded_in_snapshot'}:
            continue
        terms = [normalized(t) for t in [card['title'], *card['keywords']]]
        score = sum(len(t) for t in terms if t and (t in needle or needle in t))
        if not score:
            continue
        # When answering for a date, do not attach an inapplicable alternative edition
        # as though it supported the current ruling. Comparison mode preserves it.
        selected = active if rule_evidence and not include_inactive else citations
        item = {k: v for k, v in card.items() if k not in {'citations', 'required_sources'}}
        reviewed = card.get('review_status') == 'visually_verified' and all(
            c['verification'] == 'partial_scan_reviewed' and c['status'] == 'historical_reference'
            for c in selected)
        item.update(status=disposition, rule_evidence=rule_evidence,
                    reviewed_edition_evidence=reviewed, citations=selected)
        matches.append((score, item))
    matches.sort(key=lambda pair: (-pair[0], pair[1]['id']))
    result.update(query=query, matches=[item for _, item in matches[:limit]])
    result['needs_primary_source'] = not any(m['rule_evidence'] or m['reviewed_edition_evidence'] for m in result['matches'])
    result['needs_applicability_check'] = not any(m['rule_evidence'] for m in result['matches'])
    result['retrieval_only'] = True
    return result


def verify_cache(data: dict, directory: Path) -> dict:
    directory = directory.resolve()
    findings = []
    for source in data['sources']:
        for artifact in [source, *source.get('attachments', [])]:
            name = artifact.get('cache_file')
            if not name:
                continue
            path = directory / name
            if path.is_symlink():
                state = 'symlink_rejected'
            elif not path.is_file():
                state = 'missing'
            else:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                state = 'verified' if digest == artifact['sha256'] else 'changed_review_required'
            findings.append({'source': source['id'], 'file': name, 'status': state})
    return {'ok': bool(findings) and all(f['status'] == 'verified' for f in findings),
            'artifacts': findings,
            'note': '哈希只验证已审阅的字节快照；不证明协会尚未修订，也不验证尚未取得的资料。'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('status', 'search'):
        sub = commands.add_parser(command)
        sub.add_argument('--on', default=date.today().isoformat(), help='比赛日期 YYYY-MM-DD')
        sub.add_argument('--authority', choices=sorted(AUTHORITIES), default='all')
        if command == 'search':
            sub.add_argument('query')
            sub.add_argument('--include-inactive', action='store_true', help='显式比较未来/已替代版本')
            sub.add_argument('--limit', type=int, default=6)
    commands.add_parser('verify-cache').add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        data = load_knowledge()
        if args.command == 'status':
            result = status(data, args.on, args.authority)
        elif args.command == 'search':
            result = search(data, args.query, args.on, args.authority, args.include_inactive, args.limit)
        else:
            result = verify_cache(data, args.directory)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.command == 'verify-cache' and not result['ok'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
