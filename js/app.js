const state = {
  offers: [],
  history: [],
  commodity: [],
  correlation: [],
  selectedSector: 'all',
  sort: 'unit',
  search: '',
  onlyActive: true,
  onlyWithUnit: false,
  hideHidden: false,
  compare: JSON.parse(localStorage.getItem('tariffRadarCompare') || '[]'),
  chartOfferId: null
};

const sectorLabels = { all: 'Tutto', mobile: 'Mobile', fibra: 'Fibra', luce: 'Luce', gas: 'Gas', dual: 'Dual' };
const fmtEUR = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 2 });
const fmt5 = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 5 });
const fmtNum = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 2 });
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

async function loadJson(path, fallback) {
  try {
    const response = await fetch(path, { cache: 'no-store' });
    if (!response.ok) return fallback;
    return response.json();
  } catch (_) {
    return fallback;
  }
}

function daysUntil(dateString) {
  if (!dateString) return 99999;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const target = new Date(`${dateString}T00:00:00`);
  if (Number.isNaN(target.getTime())) return 99999;
  return Math.ceil((target - today) / 86400000);
}

function latestDate(items, field = 'lastChecked') {
  const dates = items.map(i => i[field]).filter(Boolean).sort();
  return dates.at(-1) || '—';
}

function unitValue(offer) {
  if (offer.sector === 'luce') return Number(offer.unitPriceEurPerKwh ?? offer.unitPrice ?? NaN);
  if (offer.sector === 'gas') return Number(offer.unitPriceEurPerSmc ?? offer.unitPrice ?? NaN);
  return Number(offer.baseMonthly ?? NaN);
}

function fixedValue(offer) {
  return Number(offer.fixedFeeMonth ?? offer.baseMonthly ?? 0);
}

function hiddenCount(offer) {
  return Array.isArray(offer.hiddenCosts) ? offer.hiddenCosts.length : (offer.hiddenCostFlags || []).length || 0;
}

function hiddenAmount(offer) {
  const costs = offer.hiddenCosts || [];
  return costs.reduce((sum, item) => sum + (Number.isFinite(Number(item.amount)) ? Number(item.amount) : 0), 0);
}

function estimateComparisonCost(offer) {
  if (offer.sector === 'luce') {
    const unit = Number(offer.unitPrice || 0) + Number(offer.spread || 0);
    return unit * 1000 + fixedValue(offer) * 12 + hiddenAmount(offer);
  }
  if (offer.sector === 'gas') {
    const unit = Number(offer.unitPrice || 0) + Number(offer.spread || 0);
    return unit * 500 + fixedValue(offer) * 12 + hiddenAmount(offer);
  }
  if (offer.sector === 'fibra') {
    return Number(offer.baseMonthly || 0) * 12 + Number(offer.activation || 0) + hiddenAmount(offer);
  }
  return Number(offer.baseMonthly || 0) * 12 + Number(offer.activation || 0) + hiddenAmount(offer);
}

function unitLabel(offer) {
  const unit = unitValue(offer);
  if (!Number.isFinite(unit)) return '—';
  if (offer.sector === 'luce') return `${fmt5.format(unit)} €/kWh`;
  if (offer.sector === 'gas') return `${fmt5.format(unit)} €/Smc`;
  return `${fmtEUR.format(unit)}/mese`;
}

function spreadLabel(offer) {
  const spread = Number(offer.spread);
  if (!Number.isFinite(spread)) return '—';
  return offer.sector === 'luce' ? `${fmt5.format(spread)} €/kWh` : `${fmt5.format(spread)} €/Smc`;
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
    .filter(o => !state.onlyWithUnit || Number.isFinite(unitValue(o)))
    .filter(o => !state.hideHidden || hiddenCount(o) === 0)
    .filter(o => {
      if (!query) return true;
      const hay = [o.provider, o.name, o.allowance, o.speed, o.sector, o.indexName, o.tariffType, ...(o.tags || []), ...(o.hiddenCostFlags || [])].join(' ').toLowerCase();
      return hay.includes(query);
    })
    .map(o => ({ ...o, comparisonCost: estimateComparisonCost(o) }))
    .sort((a, b) => {
      if (state.sort === 'unit') return safeSort(unitValue(a), unitValue(b));
      if (state.sort === 'fixed') return fixedValue(a) - fixedValue(b);
      if (state.sort === 'hidden') return hiddenCount(a) - hiddenCount(b) || hiddenAmount(a) - hiddenAmount(b);
      if (state.sort === 'expiry') return daysUntil(a.expiryDate) - daysUntil(b.expiryDate);
      if (state.sort === 'confidence') return Number(b.confidence || 0) - Number(a.confidence || 0);
      return Number(b.score || 0) - Number(a.score || 0);
    });
}

function safeSort(a, b) {
  const aa = Number.isFinite(a) ? a : 999999;
  const bb = Number.isFinite(b) ? b : 999999;
  return aa - bb;
}

function setArc(score) {
  const pct = Math.max(0, Math.min(100, score)) / 100;
  $('#scoreArc').style.strokeDashoffset = 320 - 320 * pct;
  $('#needle').style.transform = `rotate(${(-90 + 180 * pct).toFixed(1)}deg)`;
}

function renderTicker() {
  const fragments = state.offers.slice(0, 18).map(o => `${o.provider} ${o.name}: ${unitLabel(o)} · hidden ${hiddenCount(o)}`);
  $('#tickerTrack').textContent = (fragments.length ? [...fragments, ...fragments] : ['RUN IMPORT SOURCES']).join('  ·  ');
}

function renderKpis() {
  const active = state.offers.filter(o => o.status === 'active');
  const conf = active.map(o => Number(o.confidence || 0)).filter(Boolean);
  const avgConf = Math.round(conf.reduce((a, b) => a + b, 0) / Math.max(conf.length, 1));
  const sources = new Set(active.map(o => o.sourceUrl).filter(Boolean)).size;
  const hidden = active.reduce((sum, o) => sum + hiddenCount(o), 0);
  const bestLuce = active.filter(o => o.sector === 'luce' && Number.isFinite(unitValue(o))).sort((a, b) => unitValue(a) - unitValue(b))[0];
  const bestGas = active.filter(o => o.sector === 'gas' && Number.isFinite(unitValue(o))).sort((a, b) => unitValue(a) - unitValue(b))[0];
  const bestFiber = active.filter(o => o.sector === 'fibra').sort((a, b) => hiddenCount(a) - hiddenCount(b) || estimateComparisonCost(a) - estimateComparisonCost(b))[0];

  $('#lastUpdate').textContent = latestDate(active);
  $('#marketScore').textContent = avgConf || '—';
  setArc(avgConf || 0);
  $('#kpiOffers').textContent = active.length;
  $('#kpiHidden').textContent = hidden;
  $('#kpiSources').textContent = sources;
  $('#bestLuce').textContent = bestLuce ? `${bestLuce.provider} · ${unitLabel(bestLuce)}` : 'non disponibile';
  $('#bestGas').textContent = bestGas ? `${bestGas.provider} · ${unitLabel(bestGas)}` : 'non disponibile';
  $('#bestFiber').textContent = bestFiber ? `${bestFiber.provider} · ${fmtEUR.format(bestFiber.baseMonthly || 0)}` : 'non disponibile';
  $('#hiddenPressure').textContent = hidden ? `${hidden} flags rilevati` : 'nessun flag';
}

function renderSectorFilters() {
  const sectors = ['all', ...new Set(state.offers.map(o => o.sector))];
  $('#sectorFilters').innerHTML = sectors.map(sector => `
    <button class="chip ${state.selectedSector === sector ? 'active' : ''}" data-sector="${sector}">${sectorLabels[sector] || sector}</button>
  `).join('');
  $$('#sectorFilters .chip').forEach(button => button.addEventListener('click', () => {
    state.selectedSector = button.dataset.sector;
    $('#sectorSelect').value = state.selectedSector;
    renderAll();
  }));
}

function renderOfferGrid() {
  const offers = getFilteredOffers();
  $('#resultsCount').textContent = `${offers.length} righe · ordinamento ${state.sort}`;
  if (!offers.length) {
    $('#offerGrid').innerHTML = '<div class="offer-card"><div class="offer-body"><h3>Nessuna offerta filtrata</h3><p>Resetta i filtri o lancia l’importer reale.</p></div></div>';
    return;
  }
  $('#offerGrid').innerHTML = offers.map(o => {
    const isCompared = state.compare.includes(o.id);
    const score = Number(o.score || 0);
    const confidence = Number(o.confidence || 0);
    const hidden = hiddenCount(o);
    return `
      <article class="offer-card ${hidden ? 'has-hidden' : ''}" data-id="${escapeHtml(o.id)}">
        <div class="offer-sector">
          <strong>${sectorLabels[o.sector] || o.sector}</strong>
          <span>${o.status === 'active' ? 'attiva' : escapeHtml(o.status || 'n/d')}</span>
        </div>
        <div class="offer-body">
          <div class="offer-title"><h3>${escapeHtml(o.name)}</h3><small>${escapeHtml(o.provider)}</small></div>
          <p class="allowance">${escapeHtml(o.allowance || 'Dettagli nella fonte ufficiale')}</p>
          <div class="unit-strip">
            <div><span>Materia/unità</span><strong>${unitLabel(o)}</strong></div>
            <div><span>Spread</span><strong>${spreadLabel(o)}</strong></div>
            <div><span>Quota fissa</span><strong>${fmtEUR.format(fixedValue(o))}/mese</strong></div>
            <div><span>Hidden</span><strong>${hidden}</strong></div>
          </div>
          <div class="tags">${(o.tags || []).slice(0, 6).map(t => `<span>${escapeHtml(t)}</span>`).join('')}</div>
        </div>
        <div class="offer-numbers">
          <div class="price-box">
            <span>${o.sector === 'fibra' ? 'canone' : 'unità'}</span>
            <strong>${o.sector === 'fibra' ? fmtEUR.format(o.baseMonthly || 0) : unitLabel(o)}</strong>
            <small>${normalizedLabel(o)}</small>
          </div>
          <div class="score-box">
            <span>score ${scoreText(score)} · conf. ${confidence}%</span>
            <div class="score-meter"><i style="width:${Math.max(4, Math.min(100, confidence))}%"></i></div>
            <strong>${score}/100</strong>
          </div>
        </div>
        <div class="offer-actions">
          <a href="${escapeAttr(o.sourceUrl || '#')}" target="_blank" rel="noopener">Fonte</a>
          <button class="compare-btn ${isCompared ? 'added' : ''}" data-id="${escapeHtml(o.id)}">${isCompared ? 'Rimuovi' : 'Confronta'}</button>
          <div class="meta-list">
            <div>check: ${escapeHtml(o.lastChecked || '—')}</div>
            <div>scade: ${escapeHtml(expiryText(o))}</div>
            <div>setup: ${escapeHtml(o.setupLabel || '—')}</div>
            <div>flags: ${escapeHtml((o.hiddenCostFlags || []).join(', ') || '—')}</div>
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

function normalizedLabel(o) {
  if (o.sector === 'luce') return `1000 kWh norm. ${fmtEUR.format(estimateComparisonCost(o))}`;
  if (o.sector === 'gas') return `500 Smc norm. ${fmtEUR.format(estimateComparisonCost(o))}`;
  if (o.sector === 'fibra') return `1° anno ${fmtEUR.format(estimateComparisonCost(o))}`;
  return `1° anno ${fmtEUR.format(estimateComparisonCost(o))}`;
}

function toggleCompare(id) {
  if (state.compare.includes(id)) state.compare = state.compare.filter(x => x !== id);
  else {
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
    ['Provider', o => escapeHtml(o.provider)],
    ['Offerta', o => escapeHtml(o.name)],
    ['Settore', o => sectorLabels[o.sector] || o.sector],
    ['Materia/unità', o => unitLabel(o)],
    ['Spread', o => spreadLabel(o)],
    ['Quota fissa/canone', o => `${fmtEUR.format(fixedValue(o))}/mese`],
    ['Costo normalizzato', o => normalizedLabel(o)],
    ['Attivazione', o => fmtEUR.format(o.activation || 0)],
    ['Hidden flags', o => escapeHtml((o.hiddenCostFlags || []).join(', ') || '—')],
    ['Vincolo', o => `${o.constraintMonths || 0} mesi`],
    ['Scadenza', o => expiryText(o)],
    ['Confidenza', o => `${o.confidence || 0}%`],
    ['Fonte', o => `<a href="${escapeAttr(o.sourceUrl || '#')}" target="_blank" rel="noopener">apri</a>`]
  ];
  $('#compareTableWrap').innerHTML = `
    <table class="compare-table">
      <thead><tr><th>Campo</th>${selected.map(o => `<th>${escapeHtml(o.provider)}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(([label, fn]) => `<tr><th>${label}</th>${selected.map(o => `<td>${fn(o)}</td>`).join('')}</tr>`).join('')}</tbody>
    </table>`;
}

function renderChartSelect() {
  const options = state.offers.map(o => `<option value="${escapeAttr(o.id)}">${escapeHtml(o.provider)} · ${escapeHtml(o.name)}</option>`).join('');
  $('#chartOfferSelect').innerHTML = options;
  if (!state.chartOfferId && state.offers[0]) state.chartOfferId = state.offers[0].id;
  $('#chartOfferSelect').value = state.chartOfferId;
}

function getHistoryForOffer(id) {
  const series = state.history.find(s => s.offerId === id);
  if (series?.points?.length) return series.points.map(([date, value]) => ({ date, value: Number(value) }));
  const offer = state.offers.find(o => o.id === id);
  if (!offer) return [];
  return [{ date: offer.lastChecked || new Date().toISOString().slice(0, 10), value: unitValue(offer) }];
}

function drawLineChart(canvas, series, opts = {}) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const hAttr = Number(canvas.getAttribute('height')) || 240;
  canvas.width = Math.max(320, rect.width) * dpr;
  canvas.height = hAttr * dpr;
  ctx.scale(dpr, dpr);
  const w = Math.max(320, rect.width);
  const h = hAttr;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = opts.bg || '#141411';
  ctx.fillRect(0, 0, w, h);
  const pad = 34;
  const values = series.flatMap(s => s.points.map(p => p.value)).filter(Number.isFinite);
  if (!values.length) {
    ctx.fillStyle = '#f4efdf'; ctx.font = '13px monospace'; ctx.fillText('Nessun dato storico. Lancia import_sources.py.', 22, 34); return;
  }
  const min = Math.min(...values, 0);
  const max = Math.max(...values, min + 1);
  ctx.strokeStyle = 'rgba(244,239,223,.22)'; ctx.lineWidth = 1;
  for (let i = 0; i < 5; i++) { const y = pad + (h - pad * 2) * i / 4; ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(w - pad, y); ctx.stroke(); }
  const maxLen = Math.max(...series.map(s => s.points.length));
  const x = (i, n) => pad + (w - pad * 2) * (n === 1 ? .5 : i / (n - 1));
  const y = (v) => h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2);
  const colors = ['#d8ff37', '#ff4a1f', '#00b386', '#7aa2ff'];
  series.forEach((s, si) => {
    const pts = s.points;
    ctx.strokeStyle = colors[si % colors.length]; ctx.lineWidth = 3;
    ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(x(i, pts.length), y(p.value)) : ctx.moveTo(x(i, pts.length), y(p.value))); ctx.stroke();
    ctx.fillStyle = colors[si % colors.length];
    pts.forEach((p, i) => { ctx.beginPath(); ctx.arc(x(i, pts.length), y(p.value), 4, 0, Math.PI * 2); ctx.fill(); });
    ctx.fillStyle = colors[si % colors.length]; ctx.font = '12px monospace'; ctx.fillText(s.label, pad + si * 150, 18);
  });
  ctx.fillStyle = '#f4efdf'; ctx.font = '12px monospace'; ctx.fillText(`${fmtNum.format(min)} → ${fmtNum.format(max)}`, pad, h - 8);
}

function drawPriceChart() {
  drawLineChart($('#priceChart'), [{ label: 'offerta selezionata', points: getHistoryForOffer(state.chartOfferId) }]);
}

function drawCommodityChart() {
  const points = state.commodity.map(p => ({ date: p.date || p.month, pun: Number(p.punEurMwh ?? p.punApprox), psv: Number(p.psvEurSmc ?? p.psv) }));
  drawLineChart($('#commodityChart'), [
    { label: 'PUN €/MWh', points: points.filter(p => Number.isFinite(p.pun)).map(p => ({ date: p.date, value: p.pun })) },
    { label: 'PSV €/Smc', points: points.filter(p => Number.isFinite(p.psv)).map(p => ({ date: p.date, value: p.psv })) }
  ]);
}

function drawCorrelationChart() {
  const rows = state.correlation;
  drawLineChart($('#correlationChart'), [
    { label: 'media luce €/kWh', points: rows.filter(r => Number.isFinite(Number(r.avgElectricityCommodityEurKwh))).map(r => ({ date: r.month, value: Number(r.avgElectricityCommodityEurKwh) })) },
    { label: 'media gas €/Smc', points: rows.filter(r => Number.isFinite(Number(r.avgGasCommodityEurSmc))).map(r => ({ date: r.month, value: Number(r.avgGasCommodityEurSmc) })) }
  ]);
}

function renderInsights() {
  const active = state.offers.filter(o => o.status === 'active');
  const luceWithUnit = active.filter(o => o.sector === 'luce' && Number.isFinite(unitValue(o))).length;
  const gasWithUnit = active.filter(o => o.sector === 'gas' && Number.isFinite(unitValue(o))).length;
  const fiberHidden = active.filter(o => o.sector === 'fibra' && hiddenCount(o) > 0).length;
  const avgHidden = active.length ? active.reduce((s, o) => s + hiddenCount(o), 0) / active.length : 0;
  const insights = [];
  insights.push(`Luce: ${luceWithUnit} offerte hanno prezzo materia prima estraibile in €/kWh.`);
  insights.push(`Gas: ${gasWithUnit} offerte hanno prezzo materia prima estraibile in €/Smc.`);
  insights.push(`Fibra: ${fiberHidden} offerte/pagine hanno almeno un costo o vincolo rilevato nel testo.`);
  insights.push(`Pressione costi nascosti media: ${fmtNum.format(avgHidden)} flags/offerta. Il valore non è un costo certo, ma un segnale di lettura obbligatoria.`);
  if (!state.commodity.length) insights.push('Grafico PUN/PSV vuoto: serve lanciare lo script per scaricare i prezzi storici dal Portale Offerte Open Data.');
  if (!state.correlation.length) insights.push('Rapporto materie prime/offerte: si popola accumulando snapshot giornalieri in data/offer-snapshots.json.');
  $('#insightList').innerHTML = insights.map(i => `<li>${escapeHtml(i)}</li>`).join('');
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
      <a href="${escapeAttr(s.url)}" target="_blank" rel="noopener">open</a>
    </div>
  `).join('') || '<p class="empty">Nessuna fonte caricata.</p>';
}

function bindEvents() {
  $('#sectorSelect').addEventListener('change', e => { state.selectedSector = e.target.value; renderAll(); });
  $('#searchInput').addEventListener('input', e => { state.search = e.target.value; renderOfferGrid(); renderCompare(); });
  $('#sortSelect').addEventListener('change', e => { state.sort = e.target.value; renderOfferGrid(); });
  $('#onlyActive').addEventListener('change', e => { state.onlyActive = e.target.checked; renderAll(); });
  $('#onlyWithUnit').addEventListener('change', e => { state.onlyWithUnit = e.target.checked; renderOfferGrid(); });
  $('#hideHidden').addEventListener('change', e => { state.hideHidden = e.target.checked; renderOfferGrid(); });
  $('#resetFilters').addEventListener('click', () => {
    state.selectedSector = 'all'; state.search = ''; state.sort = 'unit'; state.onlyActive = true; state.onlyWithUnit = false; state.hideHidden = false;
    $('#sectorSelect').value = 'all'; $('#searchInput').value = ''; $('#sortSelect').value = 'unit'; $('#onlyActive').checked = true; $('#onlyWithUnit').checked = false; $('#hideHidden').checked = false;
    renderAll();
  });
  $('#chartOfferSelect').addEventListener('change', e => { state.chartOfferId = e.target.value; drawPriceChart(); });
  $('#navToggle').addEventListener('click', () => $('.nav').classList.toggle('open'));
  window.addEventListener('resize', () => { drawPriceChart(); drawCommodityChart(); drawCorrelationChart(); });
}

function renderAll() {
  renderTicker(); renderKpis(); renderSectorFilters(); renderOfferGrid(); renderChartSelect(); renderCompare(); renderInsights(); renderSources();
  drawPriceChart(); drawCommodityChart(); drawCorrelationChart();
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}
function escapeAttr(value) { return escapeHtml(value); }

async function init() {
  try {
    const [offersData, historyData, commodityData, correlationData] = await Promise.all([
      loadJson('data/offers.json', { offers: [] }),
      loadJson('data/price-history.json', { series: [] }),
      loadJson('data/commodity-index.json', { series: [] }),
      loadJson('data/market-correlation.json', { series: [] })
    ]);
    state.offers = Array.isArray(offersData) ? offersData : (offersData.offers || []);
    state.history = Array.isArray(historyData) ? historyData : (historyData.series || []);
    state.commodity = Array.isArray(commodityData) ? commodityData : (commodityData.series || []);
    state.correlation = Array.isArray(correlationData) ? correlationData : (correlationData.series || []);
    bindEvents(); renderAll();
  } catch (error) {
    console.error(error);
    document.body.insertAdjacentHTML('afterbegin', `<div style="padding:20px;border:4px solid #111;background:#ff4a1f;font-weight:900">Errore dati: ${escapeHtml(error.message)}</div>`);
  }
}

document.addEventListener('DOMContentLoaded', init);
