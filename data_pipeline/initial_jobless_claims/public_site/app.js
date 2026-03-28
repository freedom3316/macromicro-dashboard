const CSV_PATH_CANDIDATES = [
  "./chart19_all_series_latest.csv",
  "../data/raw/macromicro/chart19_all_series_latest.csv",
  "/data/raw/macromicro/chart19_all_series_latest.csv",
];

const SERIES_ORDER = [
  "initial_jobless_claims",
  "continuing_jobless_claims",
  "initial_jobless_claims_4w_avg",
];

const SERIES_META = {
  initial_jobless_claims: { name: "初请失业救济金", color: "#2356a8" },
  continuing_jobless_claims: { name: "续请失业救济金", color: "#ef7d2f" },
  initial_jobless_claims_4w_avg: { name: "初请4周均值", color: "#0f766e" },
};

const chart = echarts.init(document.getElementById("chart"));
let parsedRows = [];

function fmtNumber(v) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(v);
}

function fmtDate(d) {
  return new Date(d + "T00:00:00").toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

function renderCards(rows) {
  const cardsEl = document.getElementById("cards");
  cardsEl.innerHTML = "";

  SERIES_ORDER.forEach((label) => {
    const subset = rows.filter((r) => r.series_label === label);
    if (!subset.length) return;
    const last = subset[subset.length - 1];

    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `
      <div class="label">${SERIES_META[label].name}</div>
      <div class="value" style="color:${SERIES_META[label].color}">${fmtNumber(last.value)}</div>
      <div class="date">最新日期：${fmtDate(last.date)}</div>
    `;
    cardsEl.appendChild(div);
  });

  const latestDate = rows.reduce((m, r) => (r.date > m ? r.date : m), "0000-00-00");
  document.getElementById("lastUpdate").textContent = `最新观测：${fmtDate(latestDate)}`;
}

function buildSeries(rows) {
  return SERIES_ORDER.map((label) => {
    const subset = rows
      .filter((r) => r.series_label === label)
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((r) => [r.date, r.value]);

    return {
      name: SERIES_META[label].name,
      type: "line",
      smooth: 0.2,
      showSymbol: false,
      lineStyle: { width: 2, color: SERIES_META[label].color },
      emphasis: { focus: "series" },
      data: subset,
    };
  });
}

function renderChart(rows) {
  const option = {
    animationDuration: 700,
    grid: { left: 56, right: 24, top: 46, bottom: 64 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      valueFormatter: (v) => fmtNumber(v),
    },
    legend: {
      top: 8,
      textStyle: { color: "#344054", fontWeight: 600 },
    },
    xAxis: {
      type: "time",
      axisLabel: { color: "#667085" },
      axisLine: { lineStyle: { color: "#d0d5dd" } },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        color: "#667085",
        formatter: (v) => (v >= 1000000 ? `${(v / 1000000).toFixed(1)}M` : `${Math.round(v / 1000)}k`),
      },
      splitLine: { lineStyle: { color: "#e4e7ec", type: "dashed" } },
    },
    dataZoom: [
      { type: "inside", throttle: 50 },
      { type: "slider", height: 24, bottom: 14 },
    ],
    series: buildSeries(rows),
  };

  chart.setOption(option);
}

function applyRange(range) {
  if (range === "ALL") {
    chart.dispatchAction({ type: "dataZoom", start: 0, end: 100 });
    return;
  }

  const latest = parsedRows.reduce((m, r) => (r.date > m ? r.date : m), "0000-00-00");
  const latestDate = new Date(latest + "T00:00:00");
  const years = Number(range.replace("Y", ""));
  const startDate = new Date(latestDate);
  startDate.setFullYear(latestDate.getFullYear() - years);

  const minDate = parsedRows.reduce((m, r) => (r.date < m ? r.date : m), "9999-12-31");
  const minTs = new Date(minDate + "T00:00:00").getTime();
  const maxTs = latestDate.getTime();
  const startTs = Math.max(startDate.getTime(), minTs);

  const startPct = ((startTs - minTs) / (maxTs - minTs)) * 100;
  chart.dispatchAction({ type: "dataZoom", start: startPct, end: 100 });
}

function bindRangeButtons() {
  const buttons = [...document.querySelectorAll("#rangeButtons button")];
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      applyRange(btn.dataset.range);
    });
  });
}

function parseCsvRows(rows) {
  return rows
    .filter((r) => r.date && r.value && r.series_label)
    .map((r) => ({
      date: r.date,
      value: Number(r.value),
      series_label: r.series_label,
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
          reject(new Error("CSV empty or invalid"));
          return;
        }
        resolve(rows);
      },
      error: (err) => reject(err),
    });
  });
}

async function loadDataWithFallback() {
  let lastErr = null;
  for (const path of CSV_PATH_CANDIDATES) {
    try {
      const rows = await parseCsvByPath(path);
      return rows;
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error("No CSV path available");
}

loadDataWithFallback()
  .then((rows) => {
    parsedRows = rows;
    renderCards(parsedRows);
    renderChart(parsedRows);
    bindRangeButtons();
    applyRange("ALL");
  })
  .catch((err) => {
    document.getElementById("lastUpdate").textContent = `加载失败：${err.message}`;
  });

window.addEventListener("resize", () => chart.resize());
