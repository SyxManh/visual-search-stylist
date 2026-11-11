// Browser-flow checks with a fake fetch; never sends images or uses an API key.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('templates/index.html', 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
const elements = new Map();
const getElement = id => {
  const classes = new Set();
  if (!elements.has(id)) elements.set(id, {
    files: [], checked: false, disabled: false, value: '', textContent: '', src: '',
    classList: {
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
      toggle(name, enabled) { if(enabled) classes.add(name); else classes.delete(name); },
    },
  });
  return elements.get(id);
};
let calls = 0;
let posted;
const sandbox = vm.createContext({
  document: {getElementById: getElement},
  window: {addEventListener() {}},
  location: {origin: 'https://local.example'},
  URL, FormData, AbortSignal,
  fetch: async (url, request) => {
    calls++;
    posted = request.body;
    return {ok: true, json: async () => url === '/upload-garment'
      ? {crop_path:'manual-crop.png', crop_url:'/static/crops/manual-crop.png', label:'Trang phục đã chọn'}
      : {result_url:'/static/tryon/test.png'}};
  },
});
vm.runInContext(script, sandbox);
vm.runInContext("currentSelection={cropPath:'test-crop.png'}; currentActiveCropPath='test-crop.png'", sandbox);
getElement('personInput').files = [new Blob(['synthetic test image'], {type:'image/png'})];
getElement('clothType').value = 'upper';
(async () => {
  assert.ok(html.indexOf('id="tryonCard"') < html.indexOf('id="mainSection"'), 'Try-on must be reachable before image detection');
  getElement('tryonCard').classList.add('hidden');
  vm.runInContext("updateTryOn('unknown')", sandbox);
  assert.equal(getElement('tryonCard').classList.contains('hidden'), false, 'Unknown detector labels must not hide try-on');
  getElement('garmentInput').files = [new Blob(['synthetic clothing'], {type:'image/png'})];
  await vm.runInContext('uploadTryOnGarment()', sandbox);
  assert.equal(getElement('tryonButton').disabled, false);
  assert.equal(getElement('garmentPreview').src, 'https://local.example/static/crops/manual-crop.png');
  calls = 0;
  await vm.runInContext('createTryOn()', sandbox);
  assert.equal(calls, 0, 'Consent must be required before submitting images');
  getElement('tryonConsent').checked = true;
  await vm.runInContext('createTryOn()', sandbox);
  assert.equal(calls, 1);
  assert.equal(posted.get('consent'), 'true');
  assert.equal(posted.get('consent_provider'), 'cloudflare');
  assert.ok(!html.includes('OpenAI') && !html.includes('Gemini'));  
  assert.equal(posted.get('crop_path'), 'manual-crop.png');
  assert.equal(posted.get('cloth_type'), 'upper');
  assert.equal(getElement('tryonResult').src, 'https://local.example/static/tryon/test.png');
  assert.equal(getElement('tryonButton').disabled, false);
  console.log('Web try-on: consent, request fields, result display and button reset passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
