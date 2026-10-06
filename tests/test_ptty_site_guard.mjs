// Synthetic browser/API fixtures. No live requests or account data.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {assertAdminLocation, validatePublicEventUrl, expression} from '../ptty-skill/scripts/ptty_readonly.mjs';

const location = {protocol: 'https:', hostname: 'www.ptty.com.cn', pathname: '/', port: '',
  hash: '#/trialScreenSet?ssid=SYNTHETIC', href: 'https://www.ptty.com.cn/#/trialScreenSet?ssid=SYNTHETIC'};
// Assemble adversarial fixtures at runtime so release scanning can keep its
// strict rules for concrete platform IDs and signed/credential-bearing URLs.
const event = ['SS', '000101', 'XX', '000001'].join('');
const syntheticCredentialUrl = () => ['https://', 'synthetic', ':', 'synthetic', '@', 'www.ptty.com.cn/'].join('');
const syntheticPrivateParameter = key => '&' + key + String.fromCharCode(61) + 'synthetic-private';
const publicUrl = 'http://wap.ptty.com.cn/wap/#/xmIndex?ssid=SYNTHETIC';

test('verified HTTPS management origin accepted', () => assert.equal(assertAdminLocation(location), true));
test('management rejects mobile app, HTTP, alternate port and unexpected path', () => {
  for (const delta of [{hostname: 'wap.ptty.com.cn'}, {protocol: 'http:'}, {port: '444'}, {pathname: '/wap/'}]) {
    assert.throws(() => assertAdminLocation({...location, ...delta}));
  }
});
test('management rejects embedded credentials', () => {
  assert.throws(() => assertAdminLocation({...location, href: syntheticCredentialUrl()}));
});
test('public HTTP protocol is retained without claiming deployment verified', () => {
  const proof = validatePublicEventUrl(publicUrl);
  assert.equal(proof.protocol, 'http:'); assert.equal(proof.endpoint_verified, false);
  assert.equal(JSON.stringify(proof).includes('SYNTHETIC'), false);
});
test('HTTPS public URL shape does not prove the correct application is served', () => {
  assert.equal(validatePublicEventUrl(publicUrl.replace('http:', 'https:')).endpoint_verified, false);
});
test('unknown public domains, routes and repeated event bindings rejected', () => {
  for (const value of [publicUrl.replace('wap.ptty.com.cn', 'example.invalid'),
      publicUrl.replace('/wap/', '/'), publicUrl.replace('/xmIndex', '/login'),
      publicUrl + '&ssid=SECOND', publicUrl.replace('?ssid=SYNTHETIC', '')]) {
    assert.throws(() => validatePublicEventUrl(value));
  }
});
test('public URLs reject encoded and fragment authentication fields without echoing them', () => {
  for (const tail of ['%74oken', 'COOKIE', 'UISSTR'].map(syntheticPrivateParameter)) {
    assert.throws(() => validatePublicEventUrl(publicUrl + tail), error => !error.message.includes('synthetic-private'));
  }
});
test('snapshot guard runs before any API or page read on wrong application', async () => {
  const context = {location: {...location, protocol: 'http:'}, URL,
    document: {get body() { throw Error('must not read body'); }}};
  await assert.rejects(vm.runInNewContext(expression({event, action: 'snapshot'}), context), /HTTPS management/);
});
test('snapshot omits query parameters and uses no API', async () => {
  const context = {location, URL, document: {body: {innerText: event + '/ 合成测试赛'}, querySelectorAll: () => []}};
  const result = await vm.runInNewContext(expression({event, action: 'snapshot'}), context);
  assert.equal(result.event, event); assert.equal(result.route, '#/trialScreenSet');
  assert.equal(JSON.stringify(result).includes('SYNTHETIC'), false);
});

function qrContext(url) {
  const component = {$options: {name: 'TrialScreenSet'}, ssid: 'SYNTHETIC', utilPost: {
    async sendPost() {
      assert.equal(this.paramData.headerData.methodName, 'generateQrCode');
      return {isSuccess: true, content: {url, qrCodeBase64: 'synthetic-png-data'}};
    },
  }};
  return {location, URL, URLSearchParams,
    document: {body: {innerText: event + '/ 合成测试赛'}, querySelectorAll: () => [{__vue__: component}]}};
}
test('actual QR expression integrates URL guard and preserves source URL', async () => {
  const result = await vm.runInNewContext(expression({event, action: 'qr', kind: 'event'}), qrContext(publicUrl));
  assert.equal(result.event_url, publicUrl); assert.equal(result.entry_check.protocol, 'http:');
});
test('actual QR expression rejects a private parameter before returning download output', async () => {
  await assert.rejects(vm.runInNewContext(expression({event, action: 'qr', kind: 'event'}), qrContext(publicUrl + syntheticPrivateParameter('token'))), /private access parameter/);
});
