let adviceBusy = false;
let adviceRevision = 0;

function resetStyleAdvice() {
    adviceRevision++;
    document.getElementById('adviceResult').classList.add('hidden');
    document.getElementById('adviceStatus').textContent = '';
}

function toggleFengShui() {
    const enabled = document.getElementById('withFengShui').checked;
    document.getElementById('fengShuiInputs').classList.toggle('hidden', !enabled);
    document.getElementById('fengShuiResult').classList.add('hidden');
    resetStyleAdvice();
}

function renderFengShui(result) {
    const panel = document.getElementById('fengShuiResult');
    if (!result) { panel.classList.add('hidden'); return; }
    const colors = Array.isArray(result.colors) ? result.colors : [];
    panel.innerHTML = `<h3>Ngũ hành ${escapeHtml(result.element)} · ${escapeHtml(result.nap_am)}</h3>
        <p style="margin-top:8px;">Năm âm lịch ${escapeHtml(result.lunar_year)} · ${escapeHtml(result.can_chi)}</p>
        <div class="palette-list">${colors.map(color => `<span class="palette-chip"><i class="palette-swatch" style="background:${/^#[0-9a-fA-F]{6}$/.test(color.hex) ? color.hex : '#94A3B8'}"></i>${escapeHtml(color.label)} · ${escapeHtml(color.relation)}</span>`).join('')}</div>
        <p class="advisor-note">${escapeHtml(result.method)}</p><p class="advisor-note">${escapeHtml(result.note)}</p>`;
    panel.classList.remove('hidden');
}

async function requestStyleAdvice(ai) {
    if (adviceBusy) return;
    const el = id => document.getElementById(id);
    const status = el('adviceStatus');
    const includePalette = !ai || el('withFengShui').checked;
    const birth = el('adviceBirth').value;
    const photo = el('advicePhoto').files[0] || el('personInput').files[0];
    const height = Number(el('adviceHeight').value.replace(',', '.'));
    const weight = Number(el('adviceWeight').value.replace(',', '.'));
    if (includePalette && !birth) { status.textContent = 'Hãy chọn ngày sinh dương lịch trước.'; return; }
    if (ai) {
        if (!photo) { status.textContent = 'Hãy chọn ảnh toàn thân để AI tư vấn.'; return; }
        if (photo.size > 12 * 1024 * 1024) { status.textContent = 'Ảnh vượt quá 12 MB.'; return; }
        if (!Number.isFinite(height) || !Number.isFinite(weight) || height < 50 || height > 250 || weight < 5 || weight > 350) { status.textContent = 'Nhập chiều cao 50–250 cm và cân nặng 5–350 kg; kiểm tra lại đơn vị.'; return; }
        if (!el('adviceConsent').checked) { status.textContent = 'Cần đồng ý gửi ảnh và số đo tới Cloudflare.'; return; }
    }
    const form = new FormData();
    if (includePalette) form.append('birth_date', birth);
    if (ai) {
        form.append('person', photo); form.append('height_cm', String(height)); form.append('weight_kg', String(weight));
        form.append('occasion', el('adviceOccasion').value); form.append('preference', el('advicePreference').value);
        form.append('consent', 'true'); form.append('consent_provider', 'cloudflare');
    }
    const revision = ++adviceRevision;
    adviceBusy = true;
    el('adviceButton').disabled = true; el('fengShuiButton').disabled = true;
    status.textContent = ai ? 'AI đang xem ảnh và tư vấn phối đồ…' : 'Đang tra màu theo năm sinh âm lịch…';
    if (ai) el('adviceResult').classList.add('hidden');
    try {
        const response = await fetch(ai ? '/style-advice' : '/feng-shui', {method:'POST',body:form,signal:AbortSignal.timeout(150000)});
        const data = await response.json();
        if (revision !== adviceRevision) return;
        renderFengShui(data.feng_shui);
        if (!response.ok) throw new Error(data.error || 'Không nhận được tư vấn.');
        if (ai && data.advice) {
            el('adviceResult').textContent = data.advice;
            el('adviceResult').classList.remove('hidden');
        }
        status.textContent = ai ? 'Đã nhận tư vấn dựa trên ảnh và hồ sơ của bạn.' : 'Đã tra màu theo năm sinh âm lịch.';
    } catch (error) {
        if (revision === adviceRevision) status.textContent = error.name === 'TimeoutError' ? 'Hết thời gian chờ tư vấn; kiểm tra Usage trước khi gửi lại.' : error.message;
    } finally {
        adviceBusy = false;
        el('adviceButton').disabled = false; el('fengShuiButton').disabled = false;
    }
}
