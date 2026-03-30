const DASHBOARDS = {
  claims: {
    title: '美国初请与续请失业救济金',
    subtitle: '数据源：MacroMicro 图表 19（本地抓取）',
    csvCandidates: [
      './chart19_all_series_latest.csv',
      '../data/raw/macromicro/chart19_all_series_latest.csv',
      '/data/raw/macromicro/chart19_all_series_latest.csv',
    ],
    seriesOrder: ['series_0', 'series_1', 'series_2'],
    seriesMeta: {
      series_0: { name: '初请失业救济金', color: '#2356a8' },
      series_1: { name: '续请失业救济金', color: '#ef7d2f' },
      series_2: { name: '初请4周均值', color: '#0f766e' },
    },
  },
  nonfarm: {
    title: '美国非农就业 vs GDP（年变动）',
    subtitle: '数据源：MacroMicro 图表 171（本地抓取）',
    csvCandidates: [
      './chart171_all_series_latest.csv',
      '../data/raw/macromicro/chart171_all_series_latest.csv',
      '/data/raw/macromicro/chart171_all_series_latest.csv',
    ],
    seriesOrder: ['series_0', 'series_1'],
    seriesMeta: {
      series_0: { name: '非农就业（年变动）', color: '#8e44ad' },
      series_1: { name: 'GDP（年变动）', color: '#16a085' },
    },
  },
};

const chart = echarts.init(document.getElementById('chart'));
let currentDashboardKey = 'claims';
let parsedRows = [];

function fmtNumber(v) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(v);
}

function fmtDate(d) {
  return new Date(d + 'T00:00:00').toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

function getSeriesOrder(rows, config) {
  const order = [];
  const seen = new Set();
  config.seriesOrder.forEach((k) => {
    const has = rows.some((r) => r.series_label === k);
    if (has) {
      order.push(k);
      seen.add(k);
    }
  });
  rows.forEach((r) => {
    if (!seen.has(r.series_label)) {
      seen.add(r.series_label);
      order.push(r.series_label);
    }
  });
  return order;
}

function renderHeader(config) {
  document.getElementById('dashboardTitle').textContent = config.title;
  document.getElementById('dashboardSubtitle').textContent = config.subtitle;
}

function renderCards(rows, config) {
  const cardsEl = document.getElementById('cards');
  cardsEl.innerHTML = '';

  const order = getSeriesOrder(rows, config);
  order.forEach((label) => {
    const subset = rows.filter((r) => r.series_label === label);
    if (!subset.length) return;
    const last = subset[subset.length - 1];
    const meta = config.seriesMeta[label] || {
      name: label,
      color: '#2c3e50',
    };

    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `
      <div class="label">${meta.name}</div>
      <div class="value" style="color:${meta.color}">${fmtNumber(last.value)}</div>
      <div class="date">最新日期：${fmtDate(last.date)}</div>
    `;
    cardsEl.appendChild(div);
  });

  const latestDate = rows.reduce((m, r) => (r.date > m ? r.date : m), '0000-00-00');
  document.getElementById('lastUpdate').textContent = `最新观测：${fmtDate(latestDate)}`;
}

function buildSeries(rows, config) {
  const order = getSeriesOrder(rows, config);
  return order.map((label) => {
    const subset = rows
      .filter((r) => r.series_label === label)
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((r) => [r.date, r.value]);

    const meta = config.seriesMeta[label] || {
      name: label,
      color: '#344054',
    };

    return {
      name: meta.name,
      type: 'line',
      smooth: 0.2,
      showSymbol: false,
      lineStyle: { width: 2, color: meta.color },
      emphasis: { focus: 'series' },
      data: subset,
    };
  });
}

function renderChart(rows, config) {
  chart.setOption({
    animationDuration: 700,
    grid: { left: 56, right: 24, top: 46, bottom: 64 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      valueFormatter: (v) => fmtNumber(v),
    },
    legend: {
      top: 8,
      textStyle: { color: '#344054', fontWeight: 600 },
    },
    xAxis: {
      type: 'time',
      axisLabel: { color: '#667085' },
      axisLine: { lineStyle: { color: '#d0d5dd' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: '#667085',
        formatter: (v) => {
          const av = Math.abs(v);
          if (av >= 1000000000) return `${(v / 1000000000).toFixed(1)}B`;
          if (av >= 1000000) return `${(v / 1000000).toFixed(1)}M`;
          if (av >= 1000) return `${Math.round(v / 1000)}k`;
          return `${v}`;
        },
      },
      splitLine: { lineStyle: { color: '#e4e7ec', type: 'dashed' } },
    },
    dataZoom: [
      { type: 'inside', throttle: 50 },
      { type: 'slider', height: 24, bottom: 14 },
    ],
    series: buildSeries(rows, config),
  }, true);
}

function applyRange(range) {
  if (!parsedRows.length) return;

  if (range === 'ALL') {
    chart.dispatchAction({ type: 'dataZoom', start: 0, end: 100 });
    return;
  }

  const latest = parsedRows.reduce((m, r) => (r.date > m ? r.date : m), '0000-00-00');
  const latestDate = new Date(latest + 'T00:00:00');
  const years = Number(range.replace('Y', ''));
  const startDate = new Date(latestDate);
  startDate.setFullYear(latestDate.getFullYear() - years);

  const minDate = parsedRows.reduce((m, r) => (r.date < m ? r.date : m), '9999-12-31');
  const minTs = new Date(minDate + 'T00:00:00').getTime();
  const maxTs = latestDate.getTime();
  const startTs = Math.max(startDate.getTime(), minTs);

  const startPct = ((startTs - minTs) / (maxTs - minTs)) * 100;
  chart.dispatchAction({ type: 'dataZoom', start: startPct, end: 100 });
}

function parseCsvRows(rows) {
  return rows
    .filter((r) => r.date && r.value)
    .map((r) => ({
      date: r.date,
      value: Number(r.value),
      series_label: r.series_label || `series_${r.series_index || 0}`,
    }))
    .filter((r) => Number.isFinite(r.value));
}

function parseCsvByPath(path) {
  return new Promise((resolve, reject) => {
    Papa.parse(path, {
      download: true,
      header: true,
      complete: (result) => {
        const rows = parseCsvRows(result.data || []);
        if (!rows.length) {
          reject(new Error('CSV empty or invalid'));
          return;
        }
        resolve(rows);
      },
      error: (err) => reject(err),
    });
  });
}

async function loadDataWithFallback(paths) {
  let lastErr = null;
  for (const path of paths) {
    try {
      return await parseCsvByPath(path);
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error('No CSV path available');
}

function bindRangeButtons() {
  const buttons = [...document.querySelectorAll('#rangeButtons button')];
  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      buttons.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      applyRange(btn.dataset.range);
    });
  });
}

function setActiveTab(key) {
  [...document.querySelectorAll('#chartTabs .chart-tab')].forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.dashboard === key);
  });
}

async function switchDashboard(key) {
  const config = DASHBOARDS[key];
  if (!config) return;
  currentDashboardKey = key;
  setActiveTab(key);
  renderHeader(config);
  document.getElementById('lastUpdate').textContent = '加载中…';

  try {
    parsedRows = await loadDataWithFallback(config.csvCandidates);
    renderCards(parsedRows, config);
    renderChart(parsedRows, config);

    const activeRange = document.querySelector('#rangeButtons button.active')?.dataset.range || 'ALL';
    applyRange(activeRange);
  } catch (err) {
    document.getElementById('lastUpdate').textContent = `加载失败：${err.message}`;
  }
}

function bindTabs() {
  [...document.querySelectorAll('#chartTabs .chart-tab')].forEach((btn) => {
    btn.addEventListener('click', () => switchDashboard(btn.dataset.dashboard));
  });
}

bindRangeButtons();
bindTabs();
switchDashboard(currentDashboardKey);

window.addEventListener('resize', () => chart.resize());
