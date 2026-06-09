const state = {
  offers: [],
  history: [],
  energyIndex: [],
  selectedSector: 'all',
  selectedProfile: 'family_energy',
  sort: 'score',
  search: '',
  onlyActive: true,
  hideLongConstraints: false,
  compare: JSON.parse(localStorage.getItem('tariffRadarCompare') || '[]'),
  chartOfferId: null
};

const profiles = {
  family_energy: { label: 'Famiglia', electricityKwh: 2700, gasSmc: 800, focus: ['luce', 'gas'] },
  single_light: { label: 'Single', electricityKwh: 1600, gasSmc: 350, focus: ['luce', 'gas'] },
  high_usage: { label: 'Casa energivora', electricityKwh: 4200, gasSmc: 1300, focus: ['luce', 'gas'] },
  mobile_heavy: { label: 'Mobile heavy', focus: ['mobile'] },
  fiber_home: { label: 'Fibra casa', focus: ['fibra'] }
};

const sectorLabels = { all: 'Tutto', mobile: 'Mobile', fibra: 'Fibra', luce: 'Luce', gas: 'Gas', dual: 'Dual' };
const fmtEUR = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 2 });
const fmtNum = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 2 });
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

async function loadJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Errore caricamento ${path}`);
  return response.json();
}

function daysUntil(dateString) {
  if (!dateString) return 99999;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const target = new Date(`${dateString}T00:00:00`);
  return Math.ceil((target - today) / 86400000);
}

function latestDate(items, field = 'lastChecked') {
  const dates = items.map(i => i[field]).filter(Boolean).sort();
  return dates.at(-1) || '—';
}

function estimateAnnualCost(offer, profile = profiles[state.selectedProfile]) {
  const activation = Number(offer.activation || 0);
  const monthly = Number(offer.baseMonthly || 0);
  const unit = Number(offer.unitPrice || 0);
  const spread = Number(offer.spread || 0);
  if (offer.sector === 'luce') {
    const kwh = profile.electricityKwh || 2700;
    return activation + monthly * 12 + kwh * (unit + spread);
  }
  if (offer.sector === 'gas') {
    const smc = profile.gasSmc || 800;
    return activation + monthly * 12 + smc * (unit + spread);
  }
  if (offer.fullPriceAfterPromo && offer.promoMonths && offer.promoMonths < 12) {
    return activation + Number(offer.promoMonths) * monthly + (12 - Number(offer.promoMonths)) * Number(offer.fullPriceAfterPromo);
  }
  return activation + monthly * 12;
}

function scoreText(score) {
  if (score >= 88) return 'forte';
  if (score >= 78) return 'buono';
  if (score >= 68) return 'medio';
  return 'verifica';
}

function expiryText(offer) {
  const d = daysUntil(offer.expiryDate);
  if (!offer.expiryDate) return 'non indicata';
  if (d < 0) return 'scaduta';
  if (d === 0) return 'oggi';
  return `${d} giorni`;
}

function getFilteredOffers() {
  const query = state.search.trim().toLowerCase();
  return state.offers
    .filter(o => state.selectedSector === 'all' || o.sector === state.selectedSector)
    .filter(o => !state.onlyActive || o.status === 'active')
    .filter(o => !state.hideLongConstraints || Number(o.constraintMonths || 0) <= 24)
    .filter(o => {
      if (!query) return true;
      const hay = [o.provider, o.name, o.allowance, o.speed, o.sector, ...(o.tags || [])].join(' ').toLowerCase();
      return hay.includes(query);
    })
    .map(o => ({ ...o, annualCost: estimateAnnualCost(o) }))
    .sort((a, b) => {
      if (state.sort === 'annualCost') return a.annualCost - b.annualCost;
      if (state.sort === 'monthly') return Number(a.baseMonthly || 0) - Number(b.baseMonthly || 0);
      if (state.sort === 'expiry') return daysUntil(a.expiryDate) - daysUntil(b.expiryDate);
      if (state.sort === 'confidence') return Number(b.confidence || 0) - Number(a.confidence || 0);
      return Number(b.score || 0) - Number(a.score || 0);
    });
}

function setArc(score) {
  const pct = Math.max(0, Math.min(100, score)) / 100;
  const dash = 320 - 320 * pct;
  $('#scoreArc').style.strokeDashoffset = dash;
  $('#needle').style.transform = `rotate(${(-90 + 180 * pct).toFixed(1)}deg)`;
}

function renderTicker() {
  const fragments = state.offers.slice(0, 14).map(o => `${o.provider} ${o.name}: ${fmtEUR.format(Number(o.baseMonthly || 0))}/mese`);
  $('#tickerTrack').textContent = [...fragments, ...fragments].join('  ·  ');
}

function renderKpis() {
  const active = state.offers.filter(o => o.status === 'active');
  const scores = active.map(o => Number(o.score || 0)).filter(Boolean);
  const avgScore = Math.round(scores.reduce((a, b) => a + b, 0) / Math.max(scores.length, 1));
  const sources = new Set(active.map(o => o.sourceUrl)).size;
  const expiring = active.filter(o => {
    const d = daysUntil(o.expiryDate);
    return d >= 0 && d <= 30;
  });
  const sorted = [...active].map(o => ({ ...o, annualCost: estimateAnnualCost(o) })).sort((a, b) => b.score - a.score);
  const costs = active.map(o => estimateAnnualCost(o)).filter(Number.isFinite);
  const avg = costs.reduce((a, b) => a + b, 0) / Math.max(costs.length, 1);
  const best = Math.min(...costs);
  const lowest = [...active].sort((a, b) => Number(a.baseMonthly || 0) - Number(b.baseMonthly || 0))[0];
  const closest = expiring.sort((a, b) => daysUntil(a.expiryDate) - daysUntil(b.expiryDate))[0];

  $('#lastUpdate').textContent = latestDate(active);
  $('#marketScore').textContent = avgScore;
  setArc(avgScore);
  $('#kpiOffers').textContent = active.length;
  $('#kpiExpiring').textContent = expiring.length;
  $('#kpiSources').textContent = sources;
  $('#bestNow').textContent = sorted[0] ? `${sorted[0].provider} ${sorted[0].name}` : '—';
  $('#lowestMonthly').textContent = lowest ? `${lowest.provider} ${fmtEUR.format(lowest.baseMonthly)}` : '—';
  $('#closestExpiry').textContent = closest ? `${closest.provider}: ${expiryText(closest)}` : 'nessuna entro 30 gg';
  $('#deltaBestAvg').textContent = Number.isFinite(best) ? fmtEUR.format(Math.max(0, avg - best)) : '—';
}

function renderSectorFilters() {
  const sectors = ['all', ...new Set(state.offers.map(o => o.sector))];
  $('#sectorFilters').innerHTML = sectors.map(sector => `
    <button class="chip ${state.selectedSector === sector ? 'active' : ''}" data-sector="${sector}">${sectorLabels[sector] || sector}</button>
  `).join('');
  $$('#sectorFilters .chip').forEach(button => button.addEventListener('click', () => {
    state.selectedSector = button.dataset.sector;
    renderAll();
  }));
}

function renderOfferGrid() {
  const offers = getFilteredOffers();
  $('#resultsCount').textContent = `${offers.length} righe · ${profiles[state.selectedProfile].label}`;
  if (!offers.length) {
    $('#offerGrid').innerHTML = '<div class="offer-card"><div class="offer-body"><h3>Nessuna offerta filtrata</h3><p>Resetta i filtri o amplia la ricerca.</p></div></div>';
    return;
  }
  $('#offerGrid').innerHTML = offers.map(o => {
    const isCompared = state.compare.includes(o.id);
    const annual = estimateAnnualCost(o);
    const monthly = Number(o.baseMonthly || 0);
    const score = Number(o.score || 0);
    const confidence = Number(o.confidence || 0);
    return `
      <article class="offer-card" data-id="${o.id}">
        <div class="offer-sector">
          <strong>${sectorLabels[o.sector] || o.sector}</strong>
          <span>${o.status === 'active' ? 'attiva' : o.status}</span>
        </div>
        <div class="offer-body">
          <div class="offer-title">
            <h3>${escapeHtml(o.name)}</h3>
            <small>${escapeHtml(o.provider)}</small>
          </div>
          <p class="allowance">${escapeHtml(o.allowance || 'Dettagli nella fonte ufficiale')}</p>
          <div class="tags">${(o.tags || []).slice(0, 5).map(t => `<span>${escapeHtml(t)}</span>`).join('')}</div>
        </div>
        <div class="offer-numbers">
          <div class="price-box">
            <span>canone</span>
            <strong>${fmtEUR.format(monthly)}</strong>
            <small>annuo stimato ${fmtEUR.format(annual)}</small>
          </div>
          <div class="score-box">
            <span>segnale ${scoreText(score)}</span>
            <div class="score-meter"><i style="width:${Math.max(4, Math.min(100, score))}%"></i></div>
            <strong>${score}/100</strong> <small>conf. ${confidence}%</small>
          </div>
        </div>
        <div class="offer-actions">
          <a href="${o.sourceUrl}" target="_blank" rel="noopener">Fonte</a>
          <button class="compare-btn ${isCompared ? 'added' : ''}" data-id="${o.id}">${isCompared ? 'Rimuovi' : 'Confronta'}</button>
          <div class="meta-list">
            <div>check: ${escapeHtml(o.lastChecked || '—')}</div>
            <div>scade: ${escapeHtml(expiryText(o))}</div>
            <div>setup: ${escapeHtml(o.setupLabel || '—')}</div>
          </div>
        </div>
      </article>
    `;
  }).join('');

  $$('.compare-btn').forEach(btn => btn.addEventListener('click', () => toggleCompare(btn.dataset.id)));
  $$('.offer-card').forEach(card => card.addEventListener('click', (ev) => {
    if (ev.target.closest('a,button')) return;
    state.chartOfferId = card.dataset.id;
    $('#chartOfferSelect').value = state.chartOfferId;
    drawPriceChart();
  }));
}

function toggleCompare(id) {
  if (state.compare.includes(id)) {
    state.compare = state.compare.filter(x => x !== id);
  } else {
    if (state.compare.length >= 3) state.compare.shift();
    state.compare.push(id);
  }
  localStorage.setItem('tariffRadarCompare', JSON.stringify(state.compare));
  renderOfferGrid();
  renderCompare();
}

function renderCompare() {
  const selected = state.compare.map(id => state.offers.find(o => o.id === id)).filter(Boolean);
  if (!selected.length) {
    $('#compareTableWrap').innerHTML = '<p class="empty">Aggiungi fino a 3 offerte dalla matrice.</p>';
    return;
  }
  const rows = [
    ['Provider', o => o.provider],
    ['Offerta', o => o.name],
    ['Settore', o => sectorLabels[o.sector] || o.sector],
    ['Canone', o => fmtEUR.format(o.baseMonthly || 0)],
    ['Costo annuo stimato', o => fmtEUR.format(estimateAnnualCost(o))],
    ['Setup', o => o.setupLabel || '—'],
    ['Vincolo', o => `${o.constraintMonths || 0} mesi`],
    ['Scadenza', o => expiryText(o)],
    ['Segnale', o => `${o.score}/100`],
    ['Fonte', o => `<a href="${o.sourceUrl}" target="_blank" rel="noopener">apri</a>`]
  ];
  $('#compareTableWrap').innerHTML = `
    <table class="compare-table">
      <thead><tr><th>Campo</th>${selected.map(o => `<th>${escapeHtml(o.provider)}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(([label, fn]) => `<tr><th>${label}</th>${selected.map(o => `<td>${fn(o)}</td>`).join('')}</tr>`).join('')}</tbody>
    </table>
  `;
}

function renderChartSelect() {
  const options = state.offers.map(o => `<option value="${o.id}">${o.provider} · ${o.name}</option>`).join('');
  $('#chartOfferSelect').innerHTML = options;
  if (!state.chartOfferId && state.offers[0]) state.chartOfferId = state.offers[0].id;
  $('#chartOfferSelect').value = state.chartOfferId;
}

function getHistoryForOffer(id) {
  const series = state.history.find(s => s.offerId === id);
  if (series?.points?.length) return series.points.map(([date, value]) => ({ date, value: Number(value) }));
  const offer = state.offers.find(o => o.id === id);
  if (!offer) return [];
  return [
    { date: offer.lastChecked || new Date().toISOString().slice(0, 10), value: Number(offer.baseMonthly || offer.unitPrice || 0) }
  ];
}

function drawLineChart(canvas, points, opts = {}) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = Number(canvas.getAttribute('height')) * dpr;
  ctx.scale(dpr, dpr);
  const w = rect.width;
  const h = Number(canvas.getAttribute('height'));
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = opts.bg || '#141411';
  ctx.fillRect(0, 0, w, h);
  const pad = 32;
  const values = points.map(p => p.value).filter(Number.isFinite);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, min + 1);
  ctx.strokeStyle = 'rgba(244,239,223,.22)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 5; i++) {
    const y = pad + (h - pad * 2) * i / 4;
    ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - pad, y); ctx.stroke();
  }
  if (!points.length) return;
  const x = (i) => pad + (w - pad * 2) * (points.length === 1 ? .5 : i / (points.length - 1));
  const y = (v) => h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2);
  ctx.strokeStyle = opts.color || '#d8ff37';
  ctx.lineWidth = 4;
  ctx.beginPath();
  points.forEach((p, i) => i ? ctx.lineTo(x(i), y(p.value)) : ctx.moveTo(x(i), y(p.value)));
  ctx.stroke();
  points.forEach((p, i) => {
    ctx.fillStyle = opts.dot || '#ff4a1f';
    ctx.beginPath(); ctx.arc(x(i), y(p.value), 5, 0, Math.PI * 2); ctx.fill();
  });
  ctx.fillStyle = '#f4efdf';
  ctx.font = '12px monospace';
  ctx.fillText(`${fmtNum.format(min)} → ${fmtNum.format(max)}`, pad, 18);
  const last = points.at(-1);
  ctx.fillText(`${last.date}: ${fmtNum.format(last.value)}`, pad, h - 8);
}

function drawPriceChart() {
  drawLineChart($('#priceChart'), getHistoryForOffer(state.chartOfferId), { color: '#d8ff37', dot: '#ff4a1f' });
}

function drawEnergyChart() {
  const points = state.energyIndex.map(p => ({ date: p.date, value: Number(p.psv || p.punApprox || 0) }));
  drawLineChart($('#energyChart'), points, { color: '#00b386', dot: '#d8ff37' });
}

function renderInsights() {
  const active = state.offers.filter(o => o.status === 'active');
  const expiring = active.filter(o => daysUntil(o.expiryDate) <= 30 && daysUntil(o.expiryDate) >= 0).sort((a, b) => daysUntil(a.expiryDate) - daysUntil(b.expiryDate));
  const mobile = active.filter(o => o.sector === 'mobile').sort((a, b) => estimateAnnualCost(a) - estimateAnnualCost(b))[0];
  const fiber = active.filter(o => o.sector === 'fibra').sort((a, b) => estimateAnnualCost(a) - estimateAnnualCost(b))[0];
  const energyFixed = active.filter(o => ['luce', 'gas'].includes(o.sector) && Number(o.constraintMonths || 0) >= 24);
  const insights = [];
  if (mobile) insights.push(`Mobile: ${mobile.provider} ${mobile.name} ha il costo annuo stimato più basso nel dataset (${fmtEUR.format(estimateAnnualCost(mobile))}).`);
  if (fiber) insights.push(`Fibra: ${fiber.provider} ${fiber.name} è la più aggressiva tra le offerte casa tracciate (${fmtEUR.format(fiber.baseMonthly)}/mese).`);
  if (expiring.length) insights.push(`Pressione promo: ${expiring.length} offerte hanno scadenza entro 30 giorni; prima scadenza ${expiring[0].provider} (${expiryText(expiring[0])}).`);
  if (energyFixed.length) insights.push(`Energia: ${energyFixed.length} offerte hanno prezzo/vincolo lungo. Sono confrontabili solo leggendo bene quota fissa, imposte e durata.`);
  insights.push('Lo script di import è predisposto per Open Data ARERA e scraping leggero del prezzo lancio: niente copia massiva di contenuti commerciali.');
  $('#insightList').innerHTML = insights.map(i => `<li>${escapeHtml(i)}</li>`).join('');
}

function renderSeason() {
  const months = ['GEN', 'FEB', 'MAR', 'APR', 'MAG', 'GIU', 'LUG', 'AGO', 'SET', 'OTT', 'NOV', 'DIC'];
  const hot = new Set(['MAG', 'GIU', 'NOV']);
  const mid = new Set(['MAR', 'APR', 'SET', 'DIC']);
  $('#seasonGrid').innerHTML = months.map(m => {
    const cls = hot.has(m) ? 'hot' : mid.has(m) ? 'mid' : 'low';
    const signal = hot.has(m) ? 'ALTO' : mid.has(m) ? 'MEDIO' : 'BASSO';
    return `<div class="season-cell ${cls}"><span>${m}</span><strong>${signal}</strong></div>`;
  }).join('');
}

function renderSources() {
  const map = new Map();
  state.offers.forEach(o => {
    if (!o.sourceUrl) return;
    if (!map.has(o.sourceUrl)) map.set(o.sourceUrl, { url: o.sourceUrl, provider: o.provider, count: 0, type: o.sourceType || 'official' });
    map.get(o.sourceUrl).count++;
  });
  $('#sourceList').innerHTML = [...map.values()].sort((a, b) => b.count - a.count).map(s => `
    <div class="source-item">
      <div><strong>${escapeHtml(s.provider)}</strong><span>${s.count} offerte · ${escapeHtml(s.type)}</span></div>
      <a href="${s.url}" target="_blank" rel="noopener">open</a>
    </div>
  `).join('');
}

function bindEvents() {
  $('#profileSelect').addEventListener('change', e => { state.selectedProfile = e.target.value; renderAll(); });
  $('#searchInput').addEventListener('input', e => { state.search = e.target.value; renderOfferGrid(); renderCompare(); });
  $('#sortSelect').addEventListener('change', e => { state.sort = e.target.value; renderOfferGrid(); });
  $('#onlyActive').addEventListener('change', e => { state.onlyActive = e.target.checked; renderAll(); });
  $('#hideLongConstraints').addEventListener('change', e => { state.hideLongConstraints = e.target.checked; renderOfferGrid(); });
  $('#resetFilters').addEventListener('click', () => {
    state.selectedSector = 'all'; state.search = ''; state.sort = 'score'; state.onlyActive = true; state.hideLongConstraints = false;
    $('#searchInput').value = ''; $('#sortSelect').value = 'score'; $('#onlyActive').checked = true; $('#hideLongConstraints').checked = false;
    renderAll();
  });
  $('#chartOfferSelect').addEventListener('change', e => { state.chartOfferId = e.target.value; drawPriceChart(); });
  $('#navToggle').addEventListener('click', () => $('.nav').classList.toggle('open'));
  window.addEventListener('resize', () => { drawPriceChart(); drawEnergyChart(); });
}

function renderAll() {
  renderTicker();
  renderKpis();
  renderSectorFilters();
  renderOfferGrid();
  renderChartSelect();
  drawPriceChart();
  drawEnergyChart();
  renderInsights();
  renderSeason();
  renderCompare();
  renderSources();
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
}

async function init() {
  try {
    const [offersData, historyData, energyData] = await Promise.all([
      loadJson('data/offers.json'),
      loadJson('data/price-history.json'),
      loadJson('data/energy-index.json')
    ]);
    state.offers = Array.isArray(offersData) ? offersData : (offersData.offers || []);
    state.history = Array.isArray(historyData) ? historyData : (historyData.series || []);
    state.energyIndex = Array.isArray(energyData) ? energyData : (energyData.series || []);
    bindEvents();
    renderAll();
  } catch (error) {
    console.error(error);
    document.body.insertAdjacentHTML('afterbegin', `<div style="padding:20px;border:4px solid #111;background:#ff4a1f;font-weight:900">Errore dati: ${escapeHtml(error.message)}</div>`);
  }
}

document.addEventListener('DOMContentLoaded', init);
