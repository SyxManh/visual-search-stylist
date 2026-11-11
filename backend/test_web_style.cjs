// Exercise public form flows with synthetic data; never calls a cloud API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function el(id) {
  if (!elements.has(id)) {
    const classes = new Set();
    elements.set(id, {files:[],value:'',checked:false,disabled:false,textContent:'',innerHTML:'',
      classList:{add:n=>classes.add(n),remove:n=>classes.delete(n),contains:n=>classes.has(n),
        toggle:(n,on)=>on ? classes.add(n) : classes.delete(n)}});
  }
  return elements.get(id);
}
const palette = {element:'Kim',nap_am:'Bạch Lạp Kim',lunar_year:2000,can_chi:'Canh Thìn',
  colors:[{label:'<img src=x onerror=bad()>',hex:'bad;anything',relation:'Cùng hành'}],
  note:'Gợi ý theo quan niệm truyền thống',method:'Năm âm lịch Việt Nam'};
let calls=[];
let reply={ok:true,body:{advice:'<img src=x onerror=bad()>',feng_shui:null}};
let pending;
const context = vm.createContext({document:{getElementById:el},FormData,AbortSignal,
  escapeHtml:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
  fetch:async(url,options)=>{
    calls.push({url,form:options.body});
    if(pending) await pending;
    return {ok:reply.ok,json:async()=>reply.body};
  },
});
vm.runInContext(fs.readFileSync('static/js/style_advisor.js','utf8'),context);
const run=ai=>vm.runInContext(`requestStyleAdvice(${ai})`,context);
(async()=>{
  el('advicePhoto').files=[new Blob(['synthetic person'],{type:'image/png'})];
  el('adviceHeight').value='170';el('adviceWeight').value='65';
  el('adviceOccasion').value='work';el('advicePreference').value='minimal';
  el('adviceBirth').value='2000-06-01';
  await run(true);
  assert.equal(calls.length,0,'Consent required before sending a photo');
  el('adviceConsent').checked=true;
  await run(true);
  assert.equal(calls[0].url,'/style-advice');
  assert.equal(calls[0].form.get('height_cm'),'170');
  assert.equal(calls[0].form.get('weight_kg'),'65');
  assert.equal(calls[0].form.get('consent_provider'),'cloudflare');
  assert.equal(calls[0].form.has('birth_date'),false,'DOB opt-out respected');
  assert.equal(el('adviceResult').textContent,'<img src=x onerror=bad()>');
  assert.equal(el('adviceResult').innerHTML,'','AI output is displayed as plain text');
  el('withFengShui').checked=true;el('adviceBirth').value='';
  await run(true);assert.equal(calls.length,1,'Missing DOB blocked when requested');
  el('adviceBirth').value='2000-06-01';
  el('adviceConsent').checked=false;el('advicePhoto').files=[];
  el('adviceHeight').value='';el('adviceWeight').value='';
  reply={ok:true,body:{feng_shui:palette}};
  await run(false);
  assert.equal(calls[1].url,'/feng-shui');
  assert.equal(calls[1].form.get('birth_date'),'2000-06-01');
  assert.equal(calls[1].form.has('person'),false);
  assert.equal(calls[1].form.has('height_cm'),false);
  assert.ok(el('fengShuiResult').innerHTML.includes('&lt;img'));
  assert.ok(!el('fengShuiResult').innerHTML.includes('bad;anything'));
  el('advicePhoto').files=[new Blob(['synthetic person'],{type:'image/png'})];
  el('adviceHeight').value='170';el('adviceWeight').value='65';el('adviceConsent').checked=true;
  reply={ok:false,body:{feng_shui:palette,error:'Hết hạn mức',code:'daily_quota_exceeded'}};
  await run(true);
  assert.equal(el('adviceResult').classList.contains('hidden'),true);
  assert.equal(el('fengShuiResult').classList.contains('hidden'),false);
  assert.equal(el('adviceStatus').textContent,'Hết hạn mức');
  assert.equal(el('adviceButton').disabled,false);
  reply={ok:true,body:{advice:'stale',feng_shui:palette}};
  let resolve;
  pending=new Promise(r=>{resolve=r;});
  const first=run(true);
  const count=calls.length;
  await run(true);assert.equal(calls.length,count,'Second click does not consume another request');
  vm.runInContext('resetStyleAdvice()',context);
  resolve();await first;pending=null;
  assert.notEqual(el('adviceResult').textContent,'stale','Changed inputs invalidate old results');
  console.log('Web adviser: consent, profile, DOB opt-out, local palette, safe rendering, quota and stale responses passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
