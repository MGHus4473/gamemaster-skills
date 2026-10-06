#!/usr/bin/env python3
"""Prepare and verify offline publication packets. This module has no network transport."""
import argparse
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from urllib.parse import parse_qsl, urlsplit

FLAGS = ('ISZXC', 'ISCJC', 'ISGSMD', 'ISGSCQ', 'ISJMD')
EDITORS = ('SSGC', 'BMNR', 'SSZN', 'CCQRS', 'ZDYNR')
SHOW = ('RQ', 'SJ', 'CXH', 'CDH')
SPORT_LABELS = {'badminton': '羽毛球', 'table_tennis': '乒乓球', 'tennis': '网球', 'pickleball': '匹克球'}
PRIVATE_URL_KEYS = {'uisstr', 'password', 'passwd', 'pwd', 'token', 'access_token', 'refresh_token',
                    'authorization', 'cookie', 'session', 'sessionid', 'api_key', 'apikey'}
CREATE_DEFAULTS = {
    'TYPE': 'ADD', 'SSID': 'ADD', 'ISJX': '0', 'MJXCOUNT': '0', 'WJXCOUNT': '0',
    'TEAMMINRS': '0', 'TEAMMAXRS': '0', 'TEAMCOUNT': '0', 'ISTEAM': '', 'TEAMLIST': [],
    'imgLogoFileList': [], 'imgBackFileList': [], 'SQLXR': '', 'SQTEL': '',
    'ISIMGZB': '0', 'IMGZBURL': '', 'ISVIDIOZB': '0', 'ISSFZHRZ': '0',
    'MAXSFZHCS': 0, 'VIDIOZBURL': ''}
CREATE_REQUIRED = ('SSMC', 'QSLXID', 'CGMC', 'CDSArray', 'STARTDATE', 'ENDDATE',
                   'JMDLX', 'BSSJLX', 'JMDLIST', 'SSLX', 'MCFZS', 'cityId')
CLIENT_FIELDS = ('STARTDATE', 'ENDDATE', 'XMLIST', 'ISSHOW', 'BMNR', 'SSGC', 'SSZN',
                 'CCQRS', 'ZDYNR', 'ISLDZDZB')
OPERATIONS = {'create_event': ('ssGl', 'insertOrUpdateOrDeleteSs'),
              'set_event_images': ('ssGl', 'insertOrUpdateOrDeleteSs'),
              'editor': ('clientSet', 'saveEditor'), 'material_flags': ('clientSet', 'saveSet'),
              'materials_all': ('clientSet', 'saveYjfbData'),
              'section_assign': ('bpGl', 'createXj'), 'section_visibility': ('trialItemGl', 'setXjData')}
OP_FIELDS = {'create_event': {'fields', 'logos', 'backgrounds'}, 'set_event_images': {'logos', 'backgrounds'},
             'editor': {'field', 'path', 'format', 'force_popup', 'icon_name'},
             'material_flags': {'changes'}, 'materials_all': {'scope', 'types', 'visible'},
             'section_assign': {'section', 'start_scene', 'end_scene'},
             'section_visibility': {'section', 'referee', 'mobile', 'lineup', 'show_fields'}}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def text(value, name):
    require(isinstance(value, str) and value.strip(), name + ' must be nonempty text')
    return value


def stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def file_at(root, name):
    require(isinstance(name, str) and name and '\\' not in name, 'Use relative POSIX file paths')
    p, w = PurePosixPath(name), PureWindowsPath(name)
    require(not p.is_absolute() and not w.drive and '..' not in p.parts, 'File path escapes input directory')
    p = (root / name).resolve()
    require(p.is_relative_to(root) and p.is_file(), 'File missing or symlink escapes input directory: ' + name)
    return p


def bit(value, name):
    require(type(value) is bool, name + ' must be an explicit boolean')
    return '1' if value else '0'


def sport_identity(spec, baseline, creating):
    """Check supplied observations without inferring sport from opaque numeric IDs.

    An absent observation still permits an offline draft; it cannot certify a
    write. Contradictory observations block request generation altogether.
    """
    expected = spec['event']['sport']
    require(expected in SPORT_LABELS, 'Use an explicit supported event.sport')
    observed = baseline.get('event') or {}
    require(isinstance(observed, dict), 'Event baseline must be a full event object')
    if observed.get('SSID'):
        require(observed['SSID'] == spec['event']['id'], 'Sport identity event baseline belongs to a different event')
    label = observed.get('QSLXMC')
    if label:
        require(label == SPORT_LABELS[expected], 'Sport identity conflict in baseline QSLXMC; verify the current module before writing')
    evidence = spec.get('sport_identity')
    if evidence is None:
        return {'status': 'unverified', 'write_blocked': True,
                'reason': 'Refresh current-page module and sport options before executing any request'}
    require(isinstance(evidence, dict), 'sport_identity must contain current-page observations')
    require(evidence.get('source') == 'current_page', 'Sport mapping must come from the current page, not a remembered constant')
    text(evidence.get('captured_at'), 'sport_identity.captured_at')
    page = urlsplit(text(evidence.get('page_url'), 'sport_identity.page_url'))
    require(page.scheme == 'https' and page.hostname == 'www.ptty.com.cn' and
            page.path == '/' and not page.username and not page.password and page.port in (None, 443),
            'Sport evidence must come from the verified management application')
    require(not page.query and '?' not in page.fragment, 'Record the page route without event or session query parameters')
    require(evidence.get('module_sport') == expected, 'Sport identity conflict in current module')
    options = evidence.get('options')
    require(isinstance(options, list) and options and all(isinstance(row, dict) for row in options), 'Record the current-page sport options')
    ids = [text(row.get('id'), 'sport option id') for row in options]
    require(len(ids) == len(set(ids)), 'Duplicate sport option IDs')
    selected = text(evidence.get('selected_id'), 'sport_identity.selected_id')
    matches = [row for row in options if row['id'] == selected]
    require(len(matches) == 1 and matches[0].get('sport') == expected and
            matches[0].get('label') == SPORT_LABELS[expected], 'Sport identity conflict in current-page selected option')
    target = spec['operations'][0].get('fields', {}) if creating else observed
    require(isinstance(target.get('QSLXID'), str) and target['QSLXID'] == selected,
            'Target QSLXID differs from current-page verified selection')
    return {'status': 'observed_consistent', 'write_blocked': False,
            'evidence_sha256': sha256(stable(evidence).encode()).hexdigest(),
            'captured_at': evidence['captured_at'], 'requires_live_recheck': True}


class EditorFragment(HTMLParser):
    """Reject active content and unresolved local URLs; retain approved formatting verbatim."""
    tags = set('p br div span h1 h2 h3 h4 h5 h6 strong b em i u s strike blockquote pre code '
               'ul ol li table thead tbody tfoot tr th td caption colgroup col img a hr sub sup'.split())
    attributes = {'class', 'style', 'title', 'align', 'valign', 'width', 'height', 'border', 'cellpadding',
                  'cellspacing', 'colspan', 'rowspan', 'scope', 'start', 'type', 'src', 'href', 'alt', 'target', 'rel'}

    def __init__(self, assets):
        super().__init__(convert_charrefs=True)
        self.assets, self.used, self.image_count = assets, set(), 0
        self.has_content = False

    def handle_starttag(self, tag, attrs):
        require(tag in self.tags, 'Unsupported editor HTML tag: ' + tag + '; supply a body fragment')
        if tag == 'img':
            sources = [value for key, value in attrs if key == 'src']
            require(len(sources) == 1 and isinstance(sources[0], str) and sources[0].strip(),
                    'Every editor image requires exactly one nonempty src URL or asset reference')
            self.image_count += 1
            self.has_content = True
        for key, value in attrs:
            require(key in self.attributes and not key.startswith('on'), 'Unsupported HTML attribute: ' + key)
            value = value or ''
            if key == 'style':
                require(not re.search(r'url\s*\(|expression\s*\(|@import|[\\\x00-\x08]', value, re.I), 'Active CSS is not accepted')
            if key in ('href', 'src'):
                require(not re.search(r'[\x00-\x20\\]', value), 'Invalid URL whitespace or escape')
                if key == 'src' and value.startswith('asset:'):
                    aid = value[6:]
                    require(aid in self.assets and self.assets[aid]['role'] == 'editor_image', 'Unknown editor image asset: ' + aid)
                    self.used.add(aid)
                else:
                    u = urlsplit(value)
                    require(u.scheme in ('https', 'http') and u.hostname and not u.username and not u.password,
                            'Use verified HTTP(S) URLs or asset: IDs; local/base64/script URLs are not publishable')
                    queries = [u.query, u.fragment.split('?', 1)[-1] if '?' in u.fragment else u.fragment]
                    require(not any(key.casefold() in PRIVATE_URL_KEYS for query in queries for key, _ in parse_qsl(query)),
                            'Do not publish temporary signed download or authentication URLs')

    def handle_endtag(self, tag):
        require(tag in self.tags, 'Unsupported editor HTML closing tag: ' + tag)

    def handle_data(self, data):
        if data.strip():
            self.has_content = True

    def handle_decl(self, decl):
        raise ValueError('Supply an editor body fragment, not a complete HTML document')


def create_fields(values, event_name):
    require(isinstance(values, dict) and set(values) <= set(CREATE_DEFAULTS) | set(CREATE_REQUIRED), 'Unknown creation field')
    require(set(CREATE_REQUIRED) <= set(values), 'Creation requires: ' + ', '.join(CREATE_REQUIRED))
    result = {**deepcopy(CREATE_DEFAULTS), **deepcopy(values)}
    require(result['TYPE'] == 'ADD' and result['SSID'] == 'ADD', 'Creation packet cannot update or delete an existing event')
    require(result['SSMC'] == event_name, 'Creation SSMC differs from event.name')
    for k in ('SSMC', 'QSLXID', 'CGMC', 'SSLX', 'MCFZS'):
        text(result[k], k)
    require(result['MCFZS'].isascii() and result['MCFZS'].isdigit() and int(result['MCFZS']) > 0, 'MCFZS must be positive minutes as text')
    require(isinstance(result['cityId'], list) and len(result['cityId']) == 2 and all(isinstance(x, str) and x for x in result['cityId']),
            'cityId requires two actual region IDs from getCityList')
    courts = result['CDSArray']
    require(isinstance(courts, list) and courts and len(set(courts)) == len(courts) and
            all(isinstance(x, str) and x.isascii() and x.isdigit() and 1 <= int(x) <= 35 for x in courts), 'Use distinct observed court numbers 1..35 as strings')
    require(date.fromisoformat(result['STARTDATE']) <= date.fromisoformat(result['ENDDATE']), 'Event dates are reversed')
    require(result['JMDLX'] in ('0', '1') and result['BSSJLX'] in ('QT', 'AM', 'PM', 'EM'), 'Invalid JMDLX/BSSJLX')
    periods = result['JMDLIST']
    require(isinstance(periods, list) and periods, 'JMDLIST required')
    used, last_end = set(), None
    for p in periods:
        require(set(p) == {'QJLXID', 'QJLXMC', 'QSDATA', 'JZDATA'}, 'Use observed JMDLIST fields')
        require(p['QJLXID'] in ('AM', 'PM', 'EM') and p['QJLXID'] not in used, 'Duplicate or unknown daily period')
        used.add(p['QJLXID']); text(p['QJLXMC'], 'QJLXMC')
        if result['JMDLX'] == '0':
            require(all(isinstance(p[k], str) and re.fullmatch(r'\d{2}:\d{2}', p[k]) for k in ('QSDATA', 'JZDATA')), 'Use HH:MM period times')
            start, end = (datetime.strptime(p[k], '%H:%M') for k in ('QSDATA', 'JZDATA'))
            require(start < end and (last_end is None or start >= last_end), 'Daily periods must be ordered, positive and non-overlapping')
            last_end = end
        else:
            require(p['QSDATA'] == p['JZDATA'] and isinstance(p['QSDATA'], str) and p['QSDATA'].isascii() and p['QSDATA'].isdigit() and int(p['QSDATA']) > 0,
                    'Scene-count mode uses the same positive textual count in QSDATA/JZDATA; verify current UI before execution')
    require(result['BSSJLX'] == 'QT' or used == {result['BSSJLX']}, 'BSSJLX disagrees with daily period list')
    require(not result['imgLogoFileList'] and not result['imgBackFileList'], 'Use local image asset IDs; do not invent uploaded image records')
    result['CDS'] = ''.join(c + ',' for c in courts)
    return result


def compile_packet(spec, root):
    root = Path(root).resolve()
    require(spec.get('schema_version') == 1, 'Unsupported source schema_version')
    event = deepcopy(spec.get('event', {}))
    require(isinstance(event.get('id'), str), 'event.id is a string; empty only for creation')
    text(event.get('name'), 'event.name'); text(event.get('sport'), 'event.sport')
    text(spec.get('source_version'), 'source_version')
    operations = spec.get('operations')
    require(isinstance(operations, list) and operations, 'operations required')
    creating = any(o.get('kind') == 'create_event' for o in operations)
    require(not creating or (len(operations) == 1 and not event['id']), 'Create separately; bind the actual new event ID before later operations')
    baseline = deepcopy(spec.get('baseline', {}))
    if not creating:
        require(event['id'] and baseline.get('event_id') == event['id'], 'Read-back baseline belongs to a different event')
        text(baseline.get('captured_at'), 'baseline.captured_at')
    identity = sport_identity(spec, baseline, creating)
    files, assets = {}, {}

    def add_file(name):
        p = file_at(root, name); raw = p.read_bytes(); digest = sha256(raw).hexdigest()
        packaged = 'files/' + digest[:16] + '-' + re.sub(r'[^\w.\-]', '_', p.name)
        files[packaged] = raw
        return {'path': packaged, 'sha256': digest, 'bytes': len(raw)}

    for item in spec.get('assets', []):
        aid = text(item.get('id'), 'asset.id')
        require(re.fullmatch(r'[A-Za-z0-9_-]+', aid) and aid not in assets, 'Use unique simple asset IDs')
        role = item.get('role')
        require(role in ('event_logo', 'event_background', 'editor_image'), 'Unknown image role')
        f = add_file(item.get('path'))
        from PIL import Image
        with Image.open(file_at(root, item['path'])) as image:
            image.verify()
        with Image.open(file_at(root, item['path'])) as image:
            require(image.format in ('JPEG', 'PNG'), 'Packet image preflight supports real JPEG/PNG files')
            require(getattr(image, 'n_frames', 1) == 1, 'Animated images need separate platform verification')
            width, height, fmt = image.width, image.height, image.format
        require(f['bytes'] < 512000 if role != 'editor_image' else f['bytes'] <= 8388608, 'Image exceeds observed upload size limit')
        assets[aid] = {'id': aid, 'role': role, **f, 'width': width, 'height': height, 'format': fmt,
                       'upload': {'endpoint': 'https://www.ptty.com.cn/trialUploadImage', 'multipart_field': 'file',
                                  'response_fields': ['content.filePath', 'content.filePath_ys', 'content.url']}}
    actions, used_assets, touched = [], set(), set()
    client = deepcopy(baseline.get('client'))
    section_rows = {str(r['XJ']): deepcopy(r) for r in baseline.get('sections', [])}
    require(len(section_rows) == len(baseline.get('sections', [])), 'Duplicate XJ in section baseline')
    assigned_ranges = []

    def once(key):
        require(key not in touched, 'Conflicting duplicate operation: ' + key)
        touched.add(key)

    def baseline_client():
        require(isinstance(client, dict), 'Read clientSet/mainLoadData content before this operation')
        return client

    def asset_list(op, key, role, limit):
        ids = op.get(key, [])
        require(isinstance(ids, list) and len(ids) <= limit and len(ids) == len(set(ids)), 'Invalid ' + key + ' asset count')
        require(all(i in assets and assets[i]['role'] == role for i in ids), 'Unknown or incorrect image role in ' + key)
        used_assets.update(ids)
        return [{'$uploaded_asset': i, 'map': {'IMGPATH': 'content.filePath', 'IMGPATH_YS': 'content.filePath_ys', 'url': 'content.url'}} for i in ids]

    for op in operations:
        kind = op.get('kind'); require(kind in OPERATIONS, 'Unsupported operation: ' + str(kind))
        require(set(op) <= OP_FIELDS[kind] | {'kind'}, 'Unknown field for ' + kind)
        operation, method = OPERATIONS[kind]
        request = {'headerData': {'ssid': '' if operation == 'ssGl' else '$current_page.ssid', 'op': operation, 'methodName': method}, 'busData': {}}
        row = {'kind': kind, 'request_template': request, 'live_execution_verified': False,
               'requires_live_readback': True, 'requires_sport_identity_check': True}
        body, binding = {}, []
        if identity['write_blocked']:
            binding.append('Verify current-page sport module, selected option and target metadata; the sport identity gate is unresolved')
        if kind in ('create_event', 'set_event_images'):
            once('event_form')
            logos = asset_list(op, 'logos', 'event_logo', 1); backgrounds = asset_list(op, 'backgrounds', 'event_background', 3)
            if kind == 'create_event':
                body = create_fields(op.get('fields'), event['name'])
                row['applied_new_form_defaults'] = deepcopy(CREATE_DEFAULTS)
            else:
                body = deepcopy(baseline.get('event'))
                require(isinstance(body, dict) and body.get('SSID') == event['id'], 'Read ssGl/getEditor content for the target event')
                require('logos' in op or 'backgrounds' in op, 'Specify which image list to replace')
                body['TYPE'] = 'UPT'
                if 'cityId' not in body:
                    require(body.get('SFID') and body.get('CITYID'), 'Current event region IDs missing')
                    body['cityId'] = [str(body['SFID']), str(body['CITYID'])]
                require(isinstance(body.get('CDSArray'), list) and body['CDSArray'], 'Current CDSArray missing')
                body['CDS'] = ''.join(str(c) + ',' for c in body['CDSArray'])
            if 'logos' in op: body['imgLogoFileList'] = logos
            if 'backgrounds' in op: body['imgBackFileList'] = backgrounds
            if logos or backgrounds: binding.append('Upload listed files and bind real returned image records before submitting the form')
            row['readback'] = 'ssGl/getSsList then getEditor; compare assigned SSID, fields and image records, never retry creation blindly'
        elif kind == 'editor':
            c = baseline_client(); field = op.get('field'); require(field in EDITORS, 'Unknown editor field')
            once('editor:' + field)
            require(c.get('ISQZSHOWTCC') in ('0', '1') and 'ZDYICONTXT' in c, 'Read current popup/icon settings; saveEditor sends both for every editor type')
            f = add_file(op.get('path')); content = file_at(root, op['path']).read_text(encoding='utf-8')
            fmt = op.get('format'); require(fmt in ('html', 'text'), 'Choose html fragment or text explicitly')
            require(content.strip(), 'Empty editor content requires a separately reviewed clearing operation')
            if fmt == 'text': content = ''.join('<p>' + escape(p).replace('\n', '<br>') + '</p>' for p in content.split('\n\n'))
            parser = EditorFragment(assets); parser.feed(content); parser.close(); used_assets.update(parser.used)
            require(parser.has_content, 'Empty editor content requires a separately reviewed clearing operation')
            body = {'EDITORHTML': content, 'TYPE': field, 'ISQZSHOWTCC': c['ISQZSHOWTCC'], 'ZDYICONTXT': c['ZDYICONTXT']}
            if 'force_popup' in op:
                require(field == 'SSZN', 'force_popup belongs to the supplementary notice')
                body['ISQZSHOWTCC'] = bit(op['force_popup'], 'force_popup'); c['ISQZSHOWTCC'] = body['ISQZSHOWTCC']
            if 'icon_name' in op:
                require(field == 'ZDYNR', 'icon_name belongs to the custom notice')
                body['ZDYICONTXT'] = text(op['icon_name'], 'icon_name'); c['ZDYICONTXT'] = body['ZDYICONTXT']
            c[field] = content
            if parser.used: binding.append('Replace asset: IDs with actual uploaded compressed-image URLs; HTML cannot contain these placeholders when saved')
            row.update(source_file=f, editor_image_assets=sorted(parser.used), readback='clientSet/mainLoadData field HTML and global popup/icon flags; then verify the actual client view')
        elif kind == 'material_flags':
            once('material_visibility'); c = baseline_client()
            require(all(k in c for k in CLIENT_FIELDS), 'Incomplete client baseline; do not submit a partial saveSet')
            # Reproduce mainLoadData's strict string comparisons. Both raw
            # fields are required; an empty field is not coerced to 0 or 1.
            registration = (c.get('ISGRBM'), c.get('ISLDBM'))
            require(all(isinstance(value, str) and value in ('', '0', '1') for value in registration),
                    'Current registration fields must both be present strings from empty/0/1')
            mode = {('1', '1'): 'ALL', ('0', '1'): 'LDBM', ('1', '0'): 'GR'}.get(registration, '')
            settings = {k: deepcopy(c[k]) for k in CLIENT_FIELDS}; settings['ISGRBM'] = mode
            require(isinstance(settings['XMLIST'], list), 'XMLIST must be the complete current project list')
            projects = {p['XMID']: p for p in settings['XMLIST']}
            require(len(projects) == len(settings['XMLIST']), 'Duplicate XMID in current client list')
            changes = op.get('changes'); require(isinstance(changes, list) and changes, 'Project visibility changes required')
            changed = set()
            for change in changes:
                pid = change.get('project_id'); values = change.get('flags')
                require(pid in projects and pid not in changed, 'Unknown or duplicate target project'); changed.add(pid)
                require(isinstance(values, dict) and values and set(values) <= set(FLAGS), 'Unknown report visibility flag')
                for k, value in values.items(): projects[pid][k] = bit(value, k)
            body = {'setInfo': settings}; c['XMLIST'] = deepcopy(settings['XMLIST'])
            row['readback'] = 'clientSet/mainLoadData XMLIST flags; verify untouched projects and registration/content settings remain equal'
        elif kind == 'materials_all':
            once('material_visibility'); baseline_client()
            require(op.get('scope') == 'all_projects', 'One-click publication has no project subset parameter; explicitly choose all_projects')
            types = op.get('types'); require(isinstance(types, list) and types and len(set(types)) == len(types) and set(types) <= set(FLAGS), 'Choose distinct known publication types')
            body = {'type': bit(op.get('visible'), 'visible'), 'dataArray': types}
            row['readback'] = 'clientSet/mainLoadData; compare selected flags across every project, then client view; does not upload a local PDF/Word file'
        elif kind == 'section_assign':
            node, start, end = op.get('section'), op.get('start_scene'), op.get('end_scene')
            require(type(node) is int and 1 <= node <= 50 and type(start) is int and type(end) is int and 1 <= start <= end, 'Invalid section/range')
            once('section_range:' + str(node))
            scenes = baseline.get('scene_numbers'); require(isinstance(scenes, list) and scenes and all(type(x) is int for x in scenes), 'Read actual CXH options from bpGl/getCxList')
            require(start in scenes and end in scenes, 'Section range endpoints not in current CXH list')
            require(all(end < a or start > z for a, z in assigned_ranges), 'Overlapping section ranges in this packet')
            assigned_ranges.append((start, end)); body = {'node': node, 'startCxh': start, 'endCxh': end}
            row['readback'] = 'bpGl/mainLoadData all pages: every in-range CCH has expected XJ; inspect noXjCount; then trialItemGl/getXjs'
        else:
            node = op.get('section'); once('section_visibility:' + str(node))
            require(type(node) is int and 1 <= node <= 50 and str(node) in section_rows, 'Publish only a section observed in getXjs; assign and read back new sections first')
            before = section_rows[str(node)]; require(all(type(before.get(k)) is bool for k in ('ISQY', 'ISWAPQY', 'ISCCMDQY')), 'Section baseline visibility fields must be booleans as observed')
            values = deepcopy(before)
            names = {'referee': 'ISQY', 'mobile': 'ISWAPQY', 'lineup': 'ISCCMDQY'}
            require(any(k in op for k in (*names, 'show_fields')), 'No section visibility change specified')
            for name, field in names.items():
                if name in op: bit(op[name], name); values[field] = op[name]
            shown = op.get('show_fields', values.get('SHOWLX'))
            require(isinstance(shown, list) and len(set(shown)) == len(shown) and set(shown) <= set(SHOW), 'SHOWLX uses RQ/SJ/CXH/CDH')
            values['SHOWLX'] = shown
            body = {'xjs': str(node) + ',', 'type': 'ADD' if values['ISQY'] else 'DEL', 'ISWAPQY': str(node) + ',',
                    'wapType': 'ADD' if values['ISWAPQY'] else 'DEL', 'ccmdType': 'ADD' if values['ISCCMDQY'] else 'DEL',
                    'SHOWLX': json.dumps(shown, ensure_ascii=False, separators=(',', ':'))}
            row['readback'] = 'trialItemGl/getXjs listXj booleans and SHOWLX; then each authorized client surface; switches save immediately'
        request['busData'] = body
        # saveSet includes all editor fields, so a later full-form save can carry
        # images introduced by an earlier editor action. Block every occurrence.
        def pending_images(value):
            if isinstance(value, dict):
                result = {value['$uploaded_asset']} if '$uploaded_asset' in value else set()
                return result | set().union(*(pending_images(v) for v in value.values()))
            if isinstance(value, list):
                return set().union(*(pending_images(v) for v in value))
            if isinstance(value, str):
                return set(re.findall(r'asset:([A-Za-z0-9_-]+)', value)) & set(assets)
            return set()
        pending = sorted(pending_images(body))
        if pending and not binding:
            binding.append('This request also contains earlier unresolved images; bind every occurrence across the entire packet before execution')
        row['pending_asset_ids'] = pending
        row['pending_bindings'] = binding
        actions.append(row)
    require(used_assets == set(assets), 'Remove unused assets or explicitly attach them to an operation')
    packet = {'schema': 'ptty.publication-packet.v1', 'mode': 'offline_plan', 'business_writes': 0,
              'live_execution_verified': False, 'event': event, 'source_version': spec['source_version'],
              'sport_identity': identity,
              'execution_policy': 'Offline plan only. Recheck target event, sport identity and latest baseline in the active page before any write. Unresolved identity blocks execution.',
              'image_binding_policy': 'Resolve every asset placeholder in every request, including subsequent full saveSet payloads; retain the source packet and record a new execution version. Never submit unresolved placeholders.',
              'baseline_sha256': sha256(stable(baseline).encode()).hexdigest(), 'baseline_captured_at': baseline.get('captured_at'),
              'assets': list(assets.values()), 'actions': actions,
              'files': [{'path': p, 'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)} for p, raw in sorted(files.items())]}
    packet['packet_sha256'] = sha256(stable(packet).encode()).hexdigest()
    return packet, files


def validate_packet(path):
    path = Path(path).resolve(); packet = json.loads(path.read_text(encoding='utf-8'))
    require(packet.get('schema') == 'ptty.publication-packet.v1' and packet.get('mode') == 'offline_plan', 'Not an offline publication packet')
    require(packet.get('business_writes') == 0 and packet.get('live_execution_verified') is False, 'Packet is a plan, not proof of execution')
    identity = packet.get('sport_identity')
    require(isinstance(identity, dict) and identity.get('status') in ('unverified', 'observed_consistent'), 'Sport identity gate missing; rebuild the packet')
    require(identity.get('write_blocked') is (identity['status'] == 'unverified'), 'Sport identity gate is inconsistent')
    require(packet.get('packet_sha256') == sha256(stable({k: v for k, v in packet.items() if k != 'packet_sha256'}).encode()).hexdigest(), 'Packet content hash mismatch')
    for f in packet['files']:
        raw = file_at(path.parent, f['path']).read_bytes()
        require(len(raw) == f['bytes'] and sha256(raw).hexdigest() == f['sha256'], 'File content changed: ' + f['path'])
    for action in packet['actions']:
        h = action['request_template']['headerData']; require(OPERATIONS.get(action['kind']) == (h['op'], h['methodName']), 'Unknown request operation')
        require(action.get('live_execution_verified') is False, 'Local packet does not prove a live write')
    return {'valid': True, 'event': packet['event'], 'operations': len(packet['actions']), 'files': len(packet['files']),
            'pending_bindings': sum(bool(a['pending_bindings']) for a in packet['actions']),
            'sport_identity_status': identity['status'], 'sport_write_blocked': identity['write_blocked'],
            'mode': 'offline_plan', 'business_writes': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('spec', type=Path); p.add_argument('directory', type=Path)
    p = sub.add_parser('validate'); p.add_argument('packet', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            require(not args.directory.exists(), 'Choose a new packet directory')
            packet, files = compile_packet(json.loads(args.spec.read_text(encoding='utf-8')), args.spec.resolve().parent)
            args.directory.mkdir(parents=True)
            for name, raw in files.items():
                target = args.directory / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            path = args.directory / 'publication-packet.json'
            path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        else:
            path = args.packet
        print(json.dumps(validate_packet(path), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
