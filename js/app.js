const state = {
  offers: [],
  history: [],
  energyIndex: [],
  selectedSector: 'all',
  selectedProfile: 'family_energy',
  sort: 'annualCost',
  search: '',
  onlyActive: true,
  hideLongConstraints: false,
  compare: JSON.parse(localStorage.getItem('radarCompare') || '[]'),
  chartOfferId: null
};

const profiles = {
  family_energy: { label: 'Famiglia casa', electricityKwh: 2700, gasSmc: 800, sectorFocus: ['luce', 'gas'] },
  single_light: { label: 'Single smart', electricityKwh: 1600, gasSmc: 350, sectorFocus: ['luce', 'gas'] },
  high_usage: { label: 'Casa energivora', electricityKwh: 4200, gasSmc: 1300, sectorFocus: ['luce', 'gas'] },
  mobile_heavy: { label: 'Mobile data heavy', sectorFocus: ['mobile'] },
  fiber_home: { label: 'Fibra casa', sectorFocus: ['fibra'] }
};

const sectorLabels = {
  all: 'Tutte',
  luce: 'Luce',
  gas: 'Gas',
  mobile: 'Mobile',
  fibra: 'Fibra',
  dual: 'Dual fuel'
};

const fmtCurrency = new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 2 });
const fmtNumber = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 2 });

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

async function loadJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`Impossibile caricare ${path}`);
  return response.json();
}

function latestDate(items, field = 'lastChecked') {
  return items
    .map((item) => item[field])
    .filter(Boolean)
    .sort()
    .at(-1) || '—';
}

function daysUntil(dateString) {
  if (!dateString) return 9999;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const date = new Date(`${dateString}T00:00:00`);
  return Math.ceil((date - today) / (1000 * 60 * 60 * 24));
}

function estimateAnnualCost(offer, profile = profiles[state.selectedProfile]) {
  const activation = Number(offer.activation || 0);
  const monthly = Number(offer.baseMonthly || 0);
  const unitPrice = Number(offer.unitPrice || 0);
  const spread = Number(offer.spread || 0);

  if (offer.sector === 'luce') {
    const kwh = profile.electricityKwh || 2200;
    return activation + monthly * 12 + kwh * (unitPrice + spread);
  }

  if (offer.sector === 'gas') {
    const smc = profile.gasSmc || 700;
    return activation + monthly * 12 + smc * (unitPrice + spread);
  }

  if (offer.fullPriceAfterPromo && offer.promoMonths && offer.promoMonths < 12) {
    const promoMonths = Math.max(0, Number(offer.promoMonths));
    return activation + promoMonths * monthly + (12 - promoMonths) * Number(offer.fullPriceAfterPromo);
  }

  return activation + monthly * 12;
}

function convenienceLabel(score) {
  if (score >= 88) return 'Molto forte';
  if (score >= 78) return 'Buona';
  if (score >= 68) return 'Media';
  return 'Da verificare';
}

function getFilteredOffers() {
  const query = state.search.trim().toLowerCase();
  return state.offers
    .filter((offer) => state.selectedSector === 'all' || offer.sector === state.selectedSector)
    .filter((offer) => !state.onlyActive || offer.status === 'active')
    .filter((offer) => !state.hideLongConstraints || Number(offer.constraintMonths || 0) <= 12)
    .filter((offer) => {
      if (!query) return true;
      const haystack = [offer.provider, offer.name, offer.subtitle, offer.sector, ...(offer.tags || [])].join(' ').toLowerCase();
      return haystack.includes(query);
    })
    .map((offer) => ({ ...offer, annualCost: estimateAnnualCost(offer) }))
    .sort((a, b) => {
      if (state.sort === 'score') return b.score - a.score;
      if (state.sort === 'expiry') return daysUntil(a.expiryDate) - daysUntil(b.expiryDate);
      if (state.sort === 'confidence') return b.confidence - a.confidence;
      return a.annualCost - b.annualCost;
    });
}

function renderSectorFilters() {
  const sectors = ['all', ...new Set(state.offers.map((offer) => offer.sector))];
  $('#sectorFilters').innerHTML = sectors.map((sector) => `
    <button class="chip ${state.selectedSector === sector ? 'active' : ''}" data-sector="${sector}">
      ${sectorLabels[sector] || sector}
    </button>
  `).join('');

  $$('#sectorFilters .chip').forEach((button) => {
    button.addEventListener('click', () => {
      state.selectedSector = button.dataset.sector;
      renderAll();
    });
  });
}

function renderKpis() {
  const offers = state.offers;
  const active = offers.filter((offer) => offer.status === 'active');
  const expiring = active.filter((offer) => daysUntil(offer.expiryDate) <= 30 && daysUntil(offer.expiryDate) >= 0);
  const costs = active.map((offer) => estimateAnnualCost(offer)).filter(Number.isFinite);
  const avg = costs.reduce((sum, value) => sum + value, 0) / Math.max(costs.length, 1);
  const best = Math.min(...costs);
  const saving = Math.max(0, avg - best);
  const avgScore = Math.round(active.reduce((sum, offer) => sum + Number(offer.score || 0), 0) / Math.max(active.length, 1));
  const snapshots = state.history.length;
  const bestMonth = calculateBestWindow();

  $('#lastUpdate').textContent = latestDate(offers);
  $('#marketScore').textContent = `${avgScore}/100`;
  $('#marketSignal').textContent = avgScore >= 82 ? 'Mercato con diverse offerte interessanti.' : 'Mercato da monitorare, poche offerte forti.';
  $('#heroOffers').textContent = active.length;
  $('#heroExpiring').textContent = expiring.length;
  $('#heroSnapshots').textContent = snapshots;
  $('#kpiOffers').textContent = active.length;
  $('#kpiSaving').textContent = fmtCurrency.format(saving);
  $('#kpiExpiry').textContent = expiring.length;
  $('#kpiBestWindow').textContent = bestMonth;
}

function calculateBestWindow() {
  const buckets = new Map();
  state.history.forEach((point) => {
    const month = new Date(`${point.date}T00:00:00`).getMonth();
    if (!buckets.has(month)) buckets.set(month, []);
    buckets.get(month).push(Number(point.price));
  });
  if (!buckets.size) return '—';
  const best = [...buckets.entries()]
    .map(([month, values]) => ({ month, avg: values.reduce((a, b) => a + b, 0) / values.length }))
    .sort((a, b) => a.avg - b.avg)[0];
  return monthName(best.month);
}

function monthName(index) {
  return ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic'][index];
}

function renderOffers() {
  const offers = getFilteredOffers();
  $('#resultsCount').textContent = `${offers.length} offerte trovate · profilo ${profiles[state.selectedProfile].label}`;
  const template = $('#offerCardTemplate');
  const grid = $('#offerGrid');
  grid.innerHTML = '';

  if (!offers.length) {
    grid.innerHTML = '<p class="empty-state">Nessuna offerta corrisponde ai filtri attuali.</p>';
    return;
  }

  offers.forEach((offer) => {
    const node = template.content.cloneNode(true);
    const card = node.querySelector('.offer-card');
    card.dataset.offerId = offer.id;
    node.querySelector('.provider-badge').textContent = offer.provider.split(' ').map((part) => part[0]).join('').slice(0, 2).toUpperCase();
    node.querySelector('.sector-pill').textContent = sectorLabels[offer.sector] || offer.sector;
    node.querySelector('h3').textContent = offer.name;
    node.querySelector('.offer-subtitle').textContent = offer.subtitle;
    node.querySelector('.price-line strong').textContent = offer.priceLabel;
    node.querySelector('.price-line span').textContent = `Stima annua ${fmtCurrency.format(offer.annualCost)}`;
    node.querySelector('.score-bar span').style.width = `${Math.min(100, offer.score || 0)}%`;
    node.querySelector('.score-row em').textContent = `${offer.score}/100 · ${convenienceLabel(offer.score)}`;

    const facts = [
      ['Scadenza', formatDate(offer.expiryDate)],
      ['Attivazione', fmtCurrency.format(Number(offer.activation || 0))],
      ['Vincolo', offer.constraintMonths ? `${offer.constraintMonths} mesi` : 'No'],
      ['Confidenza', `${offer.confidence}%`]
    ];
    node.querySelector('.offer-facts').innerHTML = facts.map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('');
    node.querySelector('.tag-row').innerHTML = (offer.tags || []).map((tag) => `<span>${tag}</span>`).join('');
    node.querySelector('.source-link').href = offer.sourceUrl || '#';
    node.querySelector('.source-link').textContent = 'Fonte';
    node.querySelector('.compare-btn').textContent = state.compare.includes(offer.id) ? 'Rimuovi' : 'Confronta';
    node.querySelector('.compare-btn').addEventListener('click', () => toggleCompare(offer.id));
    node.querySelector('.details-btn').addEventListener('click', () => showDetails(offer.id));
    card.addEventListener('click', (event) => {
      if (event.target.closest('button, a')) return;
      selectChartOffer(offer.id);
    });
    grid.appendChild(node);
  });
}

function formatDate(dateString) {
  if (!dateString) return '—';
  return new Intl.DateTimeFormat('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(`${dateString}T00:00:00`));
}

function toggleCompare(offerId) {
  if (state.compare.includes(offerId)) {
    state.compare = state.compare.filter((id) => id !== offerId);
  } else {
    state.compare = [...state.compare, offerId].slice(-3);
  }
  localStorage.setItem('radarCompare', JSON.stringify(state.compare));
  renderOffers();
  renderCompare();
}

function renderCompare() {
  const wrap = $('#compareTableWrap');
  const offers = state.compare.map((id) => state.offers.find((offer) => offer.id === id)).filter(Boolean);
  if (!offers.length) {
    wrap.innerHTML = '<p class="empty-state">Aggiungi offerte al confronto dalle card.</p>';
    return;
  }
  const rows = [
    ['Operatore', (o) => o.provider],
    ['Offerta', (o) => o.name],
    ['Settore', (o) => sectorLabels[o.sector] || o.sector],
    ['Prezzo', (o) => o.priceLabel],
    ['Costo annuo stimato', (o) => fmtCurrency.format(estimateAnnualCost(o))],
    ['Attivazione', (o) => fmtCurrency.format(Number(o.activation || 0))],
    ['Scadenza', (o) => formatDate(o.expiryDate)],
    ['Vincolo', (o) => o.constraintMonths ? `${o.constraintMonths} mesi` : 'No'],
    ['Score', (o) => `${o.score}/100`],
    ['Azioni', (o) => `<button class="btn btn-small ghost remove-compare" data-id="${o.id}">Rimuovi</button>`]
  ];

  wrap.innerHTML = `
    <table class="compare-table">
      <thead><tr><th>Parametro</th>${offers.map((offer) => `<th>${offer.provider}</th>`).join('')}</tr></thead>
      <tbody>${rows.map(([label, getter]) => `<tr><th>${label}</th>${offers.map((offer) => `<td>${getter(offer)}</td>`).join('')}</tr>`).join('')}</tbody>
    </table>
  `;
  $$('.remove-compare').forEach((button) => button.addEventListener('click', () => toggleCompare(button.dataset.id)));
}

function showDetails(offerId) {
  const offer = state.offers.find((item) => item.id === offerId);
  if (!offer) return;
  const points = state.history.filter((point) => point.offerId === offerId);
  const min = points.length ? Math.min(...points.map((p) => Number(p.price))) : null;
  const current = Number(offer.unitPrice || offer.baseMonthly || 0);
  const distanceFromBest = min ? ((current - min) / min) * 100 : 0;
  $('#detailsContent').innerHTML = `
    <div class="details-body">
      <h3>${offer.provider} · ${offer.name}</h3>
      <p>${offer.subtitle}</p>
      <div class="details-grid">
        <div><small>Costo annuo stimato</small><strong>${fmtCurrency.format(estimateAnnualCost(offer))}</strong></div>
        <div><small>Indice convenienza</small><strong>${offer.score}/100</strong></div>
        <div><small>Scadenza offerta</small><strong>${formatDate(offer.expiryDate)}</strong></div>
        <div><small>Ultimo controllo</small><strong>${formatDate(offer.lastChecked)}</strong></div>
        <div><small>Distanza dal minimo storico campione</small><strong>${fmtNumber.format(distanceFromBest)}%</strong></div>
        <div><small>Affidabilità dato</small><strong>${offer.confidence}%</strong></div>
      </div>
      <h4>Vincoli e costi da verificare</h4>
      <p>${offer.constraints || 'Nessun vincolo dichiarato nel dato corrente.'}</p>
      <ul>${(offer.hiddenCosts || []).map((cost) => `<li>${cost}</li>`).join('') || '<li>Nessun costo nascosto nel dataset corrente.</li>'}</ul>
      <p><a class="btn btn-primary" href="${offer.sourceUrl}" target="_blank" rel="noopener noreferrer">Apri fonte ufficiale</a></p>
    </div>
  `;
  $('#detailsDialog').showModal();
}

function selectChartOffer(offerId) {
  state.chartOfferId = offerId;
  $('#chartOfferSelect').value = offerId;
  renderPriceChart();
}

function setupChartSelector() {
  const select = $('#chartOfferSelect');
  select.innerHTML = state.offers.map((offer) => `<option value="${offer.id}">${offer.provider} · ${offer.name}</option>`).join('');
  state.chartOfferId = state.chartOfferId || state.offers[0]?.id;
  select.value = state.chartOfferId;
  select.addEventListener('change', () => selectChartOffer(select.value));
}

function drawLineChart(canvas, series, options = {}) {
  const ctx = canvas.getContext('2d');
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr;
  canvas.height = (options.height || canvas.getAttribute('height') || 220) * dpr;
  ctx.scale(dpr, dpr);
  const width = rect.width;
  const height = options.height || Number(canvas.getAttribute('height')) || 220;
  const pad = { top: 18, right: 18, bottom: 32, left: 44 };
  ctx.clearRect(0, 0, width, height);

  if (!series.length) {
    ctx.fillStyle = '#a8bcc0';
    ctx.fillText('Nessun dato storico', 16, 32);
    return;
  }

  const values = series.map((point) => Number(point.value));
  const min = Math.min(...values) * 0.96;
  const max = Math.max(...values) * 1.04;
  const x = (index) => pad.left + (index / Math.max(series.length - 1, 1)) * (width - pad.left - pad.right);
  const y = (value) => height - pad.bottom - ((value - min) / Math.max(max - min, 0.0001)) * (height - pad.top - pad.bottom);

  ctx.strokeStyle = 'rgba(255,255,255,.12)';
  ctx.lineWidth = 1;
  for (let i = 0; i < 4; i++) {
    const yy = pad.top + i * ((height - pad.top - pad.bottom) / 3);
    ctx.beginPath();
    ctx.moveTo(pad.left, yy);
    ctx.lineTo(width - pad.right, yy);
    ctx.stroke();
  }

  const gradient = ctx.createLinearGradient(0, 0, width, 0);
  gradient.addColorStop(0, '#74f7b4');
  gradient.addColorStop(1, '#7cc8ff');
  ctx.strokeStyle = gradient;
  ctx.lineWidth = 3;
  ctx.beginPath();
  series.forEach((point, index) => {
    if (index === 0) ctx.moveTo(x(index), y(point.value));
    else ctx.lineTo(x(index), y(point.value));
  });
  ctx.stroke();

  ctx.fillStyle = '#74f7b4';
  series.forEach((point, index) => {
    ctx.beginPath();
    ctx.arc(x(index), y(point.value), 4, 0, Math.PI * 2);
    ctx.fill();
  });

  ctx.fillStyle = '#a8bcc0';
  ctx.font = '12px Inter, sans-serif';
  ctx.fillText(fmtNumber.format(max), 6, pad.top + 4);
  ctx.fillText(fmtNumber.format(min), 6, height - pad.bottom);
  const first = series[0].label;
  const last = series.at(-1).label;
  ctx.fillText(first, pad.left, height - 8);
  ctx.textAlign = 'right';
  ctx.fillText(last, width - pad.right, height - 8);
  ctx.textAlign = 'left';
}

function renderPriceChart() {
  const offer = state.offers.find((item) => item.id === state.chartOfferId) || state.offers[0];
  if (!offer) return;
  const points = state.history
    .filter((point) => point.offerId === offer.id)
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((point) => ({ label: new Date(`${point.date}T00:00:00`).toLocaleDateString('it-IT', { month: 'short' }), value: Number(point.price) }));
  $('#chartSubtitle').textContent = `${offer.provider} · ${offer.name}`;
  drawLineChart($('#priceChart'), points, { height: 220 });
}

function renderEnergyChart() {
  const points = state.energyIndex.map((point) => ({
    label: new Date(`${point.date}T00:00:00`).toLocaleDateString('it-IT', { month: 'short' }),
    value: Number(point.electricityIndex)
  }));
  drawLineChart($('#energyChart'), points, { height: 160 });
}

function renderInsights() {
  const filtered = getFilteredOffers();
  const expiring = state.offers
    .filter((offer) => daysUntil(offer.expiryDate) <= 30 && daysUntil(offer.expiryDate) >= 0)
    .sort((a, b) => daysUntil(a.expiryDate) - daysUntil(b.expiryDate));
  const best = filtered[0];
  const fixedEnergy = state.offers.filter((offer) => offer.sector === 'luce' && offer.type === 'fixed');
  const variableEnergy = state.offers.filter((offer) => offer.sector === 'luce' && offer.type === 'variable');
  const fixedAvg = avg(fixedEnergy.map((offer) => estimateAnnualCost(offer)));
  const variableAvg = avg(variableEnergy.map((offer) => estimateAnnualCost(offer)));
  const diff = fixedAvg && variableAvg ? fixedAvg - variableAvg : 0;
  const insights = [];

  if (best) insights.push(`<strong>Best fit attuale:</strong> ${best.provider} ${best.name}, stima ${fmtCurrency.format(best.annualCost)} per il profilo selezionato.`);
  if (expiring[0]) insights.push(`<strong>Scadenza più vicina:</strong> ${expiring[0].name} scade tra ${daysUntil(expiring[0].expiryDate)} giorni.`);
  if (diff) insights.push(`<strong>Luce:</strong> nel campione demo il variabile costa ${fmtCurrency.format(Math.abs(diff))} ${diff > 0 ? 'meno' : 'più'} del fisso sul profilo corrente.`);
  insights.push(`<strong>Dato operativo:</strong> se una promo ha costo basso ma confidenza sotto 70%, va revisionata manualmente prima di pubblicarla.`);

  $('#insightList').innerHTML = insights.map((item) => `<li>${item}</li>`).join('');
}

function avg(values) {
  const filtered = values.filter(Number.isFinite);
  return filtered.reduce((sum, value) => sum + value, 0) / Math.max(filtered.length, 1);
}

function renderSeasonGrid() {
  const buckets = Array.from({ length: 12 }, (_, month) => ({ month, values: [] }));
  state.history.forEach((point) => {
    const month = new Date(`${point.date}T00:00:00`).getMonth();
    buckets[month].values.push(Number(point.price));
  });
  const scored = buckets.map((bucket) => ({
    ...bucket,
    avg: bucket.values.length ? avg(bucket.values) : Infinity
  })).sort((a, b) => a.avg - b.avg);
  const hotMonths = new Set(scored.slice(0, 3).map((bucket) => bucket.month));
  $('#seasonGrid').innerHTML = buckets.map((bucket) => `
    <div class="month-cell ${hotMonths.has(bucket.month) ? 'hot' : ''}">
      <strong>${monthName(bucket.month)}</strong>
      <small>${bucket.values.length ? `${bucket.values.length} dati` : '—'}</small>
    </div>
  `).join('');
}

function setupEvents() {
  $('#profileSelect').addEventListener('change', (event) => {
    state.selectedProfile = event.target.value;
    renderAll();
  });
  $('#sortSelect').addEventListener('change', (event) => {
    state.sort = event.target.value;
    renderOffers();
  });
  $('#searchInput').addEventListener('input', (event) => {
    state.search = event.target.value;
    renderOffers();
  });
  $('#onlyActive').addEventListener('change', (event) => {
    state.onlyActive = event.target.checked;
    renderOffers();
  });
  $('#hideLongConstraints').addEventListener('change', (event) => {
    state.hideLongConstraints = event.target.checked;
    renderOffers();
  });
  $('#resetFilters').addEventListener('click', () => {
    state.selectedSector = 'all';
    state.search = '';
    state.sort = 'annualCost';
    state.onlyActive = true;
    state.hideLongConstraints = false;
    $('#searchInput').value = '';
    $('#sortSelect').value = 'annualCost';
    $('#onlyActive').checked = true;
    $('#hideLongConstraints').checked = false;
    renderAll();
  });
  $('#dialogClose').addEventListener('click', () => $('#detailsDialog').close());
  $('#navToggle').addEventListener('click', () => {
    const nav = $('.main-nav');
    nav.classList.toggle('open');
    $('#navToggle').setAttribute('aria-expanded', nav.classList.contains('open'));
  });
  $('#alertForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const email = $('#alertEmail').value;
    const sector = $('#alertSector').value;
    const threshold = $('#alertThreshold').value;
    $('#alertNote').textContent = `Alert demo salvato localmente: ${sector} sotto ${fmtCurrency.format(Number(threshold))}. In produzione collega una funzione serverless per inviare email a ${email}.`;
    event.target.reset();
  });
  window.addEventListener('resize', debounce(() => {
    renderPriceChart();
    renderEnergyChart();
  }, 150));
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function renderAll() {
  renderKpis();
  renderSectorFilters();
  renderOffers();
  renderCompare();
  renderInsights();
  renderSeasonGrid();
  renderPriceChart();
  renderEnergyChart();
}

async function init() {
  try {
    const [offers, history, energyIndex] = await Promise.all([
      loadJson('data/offers.json'),
      loadJson('data/price-history.json'),
      loadJson('data/energy-index.json')
    ]);
    state.offers = offers;
    state.history = history;
    state.energyIndex = energyIndex;
    setupChartSelector();
    setupEvents();
    renderAll();
  } catch (error) {
    console.error(error);
    $('#offerGrid').innerHTML = `<p class="empty-state">Errore caricamento dati: ${error.message}</p>`;
  }
}

init();
