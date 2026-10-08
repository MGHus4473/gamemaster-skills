"""Synthetic platform response -> saved QR/URL -> logo artwork -> exact decode."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('qr_delivery_export', ROOT / 'ptty-skill/scripts/qr_export.py')
qr_export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qr_export)
sys.path.insert(0, str(ROOT / 'ptty-skill/scripts'))
from verify_qr import verify


class QRDeliveryTests(unittest.TestCase):
    def test_platform_read_then_logo_preserves_exact_public_url(self):
        import qrcode
        import zxingcpp
        from PIL import Image
        url = 'http://wap.ptty.com.cn/wap/#/xmIndex?ssid=synthetic-event'
        png = io.BytesIO()
        qrcode.make(url).save(png, format='PNG')
        fixture = {'isSuccess': True, 'content': {'url': url, 'qrCodeBase64': base64.b64encode(png.getvalue()).decode()}}
        script = r'''
import vm from 'node:vm';
import {readFileSync, writeFileSync} from 'node:fs';
const {expression, qrNavigationExpression, decodeFile} = await import(process.argv[1]);
const response = JSON.parse(readFileSync(0, 'utf8'));
const event = 'SS000000X0001';
const location = {protocol:'https:',hostname:'www.ptty.com.cn',port:'',pathname:'/',hash:'#/trialClientSet?ssid=synthetic-event'};
const target = {$options:{name:'TrialScreenSet'},ssid:'synthetic-event',utilPost:{sendPost:async()=>response}};
let current = {ssid:'synthetic-event',$router:{push:async dest=>{location.hash='#'+dest.path+'?ssid='+dest.query.ssid;current=target;}}};
const ctx = {URL,URLSearchParams,location,document:{body:{innerText:event+'/'},querySelectorAll:()=>[{__vue__:current}]}};
const opts = {event,action:'qr',kind:'event',navigate:true};
await vm.runInNewContext(qrNavigationExpression(opts),ctx);
const result = await vm.runInNewContext(expression(opts),ctx);
writeFileSync(process.argv[2],decodeFile(result,'qr',process.argv[2]));
writeFileSync(process.argv[2]+'.url.txt',result.event_url+'\n');
'''
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            original, logo = d / 'platform.png', d / 'logo.png'
            subprocess.run(['node', '--input-type=module', '-e', script,
                            (ROOT / 'ptty-skill/scripts/ptty_readonly.mjs').as_uri(), str(original)],
                           input=json.dumps(fixture), text=True, capture_output=True, check=True)
            self.assertEqual(original.read_bytes(), png.getvalue())
            self.assertEqual(Path(str(original) + '.url.txt').read_text().strip(), url)
            Image.new('RGBA', (64, 64), (30, 100, 180, 255)).save(logo)
            for position in ('header', 'center'):
                with self.subTest(position=position):
                    out = d / (position + '.png')
                    args = qr_export.parser().parse_args(['--url-file', str(original) + '.url.txt',
                           '--logo', str(logo), '--logo-position', position, '--out', str(out),
                           '--footer', 'Synthetic event'])
                    report = qr_export.generate(args)
                    self.assertEqual(report['verification'], 'decoded_payload_equal')
                    self.assertEqual(report['logo_position'], position)
                    self.assertEqual(report['payload_sha256'], hashlib.sha256(url.encode()).hexdigest())
                    self.assertFalse(report['mobile_scan_verified'])
                    decoded = zxingcpp.read_barcodes(Image.open(out))
                    self.assertIn(url, [r.text for r in decoded])
                    self.assertTrue(Path(str(out) + '.verification.json').exists())
                    original_bytes = out.read_bytes()
                    checked = verify(out, str(original) + '.url.txt')
                    self.assertEqual(checked['verification'], 'decoded_payload_equal')
                    self.assertFalse(checked['image_modified'])
                    self.assertEqual(out.read_bytes(), original_bytes)

    def test_download_verifier_rejects_changed_payload_or_unreadable_artwork(self):
        import qrcode
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            source = 'http://wap.ptty.com.cn/wap/#/xmIndex?ssid=synthetic-event'
            expected = d / 'expected.txt'
            expected.write_text(source)
            for i, payload in enumerate([source.replace('http:', 'https:'),
                                          source.replace('synthetic-event', 'other-event'),
                                          'https://example.com/short-link']):
                out = d / f'wrong-{i}.png'
                qrcode.make(payload).save(out)
                with self.assertRaises(ValueError): verify(out, expected)
            Image.new('RGB', (400, 400), 'white').save(d / 'blank.png')
            with self.assertRaises(ValueError): verify(d / 'blank.png', expected)

    def test_download_verifier_rejects_multiple_codes(self):
        import qrcode
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            url = 'https://example.com/synthetic-event'
            expected = d / 'expected.txt'
            expected.write_text(url)
            a, b = qrcode.make(url).convert('RGB'), qrcode.make('https://example.com/wrong').convert('RGB')
            image = Image.new('RGB', (a.width + b.width + 100, max(a.height, b.height)), 'white')
            image.paste(a, (0, 0)); image.paste(b, (a.width + 100, 0)); image.save(d / 'two.png')
            with self.assertRaises(ValueError): verify(d / 'two.png', expected)

    def test_miniapp_code_cannot_be_replaced_or_covered_by_center_logo(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            source, logo = d / 'mini.png', d / 'logo.png'
            Image.new('RGB', (240, 240), 'blue').save(source)
            Image.new('RGB', (40, 40), 'red').save(logo)
            common = ['--source-image', str(source), '--miniapp', '--logo', str(logo)]
            args = qr_export.parser().parse_args(common + ['--out', str(d / 'blocked.png'), '--logo-position', 'center'])
            with self.assertRaises(ValueError): qr_export.generate(args)
            self.assertFalse((d / 'blocked.png').exists())
            args = qr_export.parser().parse_args(common + ['--out', str(d / 'header.png')])
            report = qr_export.generate(args)
            self.assertEqual(report['verification'], 'platform_original_preserved')
            x, y = report['code_origin']
            with Image.open(d / 'header.png') as output, Image.open(source) as original:
                self.assertEqual(output.crop((x, y, x + 240, y + 240)).tobytes(), original.tobytes())


if __name__ == '__main__':
    unittest.main()
