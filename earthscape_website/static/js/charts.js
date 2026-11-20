/* ===== EarthScape Climate Agency — Chart.js Module ===== */

// Theme colours (must match CSS :root)
const ES = {
  deepForest: '#143121',
  pine:       '#15403A',
  forest:     '#1E5B3F',
  leaf:       '#7FB069',
  sage:       '#5C7666',
  cream:      '#F7F3E9',
  critical:   '#D64545',
  warning:    '#F2A007',
  ok:         '#1E5B3F',
  chipBg:     '#DCE8D2',
};

// Chart.js global defaults
Chart.defaults.font.family = "'Nunito Sans', sans-serif";
Chart.defaults.color = ES.deepForest;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.padding = 16;
Chart.defaults.elements.point.radius = 2;
Chart.defaults.elements.point.hoverRadius = 5;
Chart.defaults.responsive = true;
Chart.defaults.maintainAspectRatio = false;

// ── Registry — holds chart instances for cleanup ─────────
const chartRegistry = {};

function destroyChart(key) {
  if (chartRegistry[key]) {
    chartRegistry[key].destroy();
    delete chartRegistry[key];
  }
}

// ── Helper: fetch JSON with optional year filters ────────
async function fetchData(url, startYear, endYear) {
  const params = new URLSearchParams();
  if (startYear) params.append('start_year', startYear);
  if (endYear)   params.append('end_year', endYear);
  const sep = url.includes('?') ? '&' : '?';
  const fullUrl = params.toString() ? `${url}${sep}${params}` : url;
  const res = await fetch(fullUrl);
  if (!res.ok) throw new Error(`API ${res.status}: ${fullUrl}`);
  return res.json();
}

// ───────────────────────────────────────────────────────────
// 1. Temperature History Chart (line)
// ───────────────────────────────────────────────────────────
async function initHistoryChart(startYear, endYear, chartType) {
  const canvas = document.getElementById('historyChart');
  if (!canvas) return;
  destroyChart('history');

  const type = chartType || 'line';

  try {
    const data = await fetchData('/api/chart/history', startYear, endYear);
    const labels = data.labels || [];
    const temps  = data.temp_anomaly || [];
    const flags  = data.is_anomaly || [];

    // Separate normal vs anomaly points
    const normalData  = temps.map((v, i) => flags[i] ? null : v);
    const anomalyData = temps.map((v, i) => flags[i] ? v : null);

    chartRegistry['history'] = new Chart(canvas, {
      type: type,
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Temp Anomaly (°C)',
            data: normalData,
            borderColor: ES.forest,
            backgroundColor: type === 'bar' ? ES.forest : 'transparent',
            borderWidth: 2,
            tension: 0.3,
            spanGaps: true,
            pointRadius: 0,
            order: 2,
          },
          {
            label: 'Anomaly Flagged',
            data: anomalyData,
            borderColor: ES.critical,
            backgroundColor: ES.critical,
            borderWidth: 0,
            pointRadius: 4,
            pointStyle: 'triangle',
            showLine: false,
            order: 1,
          }
        ],
      },
      options: {
        plugins: {
          title: { display: true, text: 'Global Temperature Anomaly', font: { size: 16, family: "'Fraunces', serif" } },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y != null ? ctx.parsed.y.toFixed(3) : '—'} °C`
            }
          }
        },
        scales: {
          x: { ticks: { maxTicksLimit: 20 }, grid: { display: false } },
          y: { title: { display: true, text: '°C Anomaly' }, grid: { color: 'rgba(0,0,0,0.05)' } }
        }
      }
    });
  } catch (err) {
    console.error('History chart error:', err);
  }
}

// ───────────────────────────────────────────────────────────
// 2. CO₂ Chart
// ───────────────────────────────────────────────────────────
async function initCO2Chart(startYear, endYear) {
  const canvas = document.getElementById('co2Chart');
  if (!canvas) return;
  destroyChart('co2');

  try {
    const data = await fetchData('/api/chart/history', startYear, endYear);
    const labels = data.labels || [];
    const co2    = data.co2 || [];

    // Filter out nulls (pre-1958)
    const co2Filtered = co2.map(v => (v === null || v === 0) ? null : v);

    chartRegistry['co2'] = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [{
          label: 'CO₂ (ppm)',
          data: co2Filtered,
          borderColor: ES.sage,
          backgroundColor: hexToRgba(ES.sage, 0.1),
          fill: true,
          borderWidth: 2,
          tension: 0.35,
          spanGaps: false,
          pointRadius: 0,
        }],
      },
      options: {
        plugins: {
          title: { display: true, text: 'Atmospheric CO₂ Concentration', font: { size: 16, family: "'Fraunces', serif" } },
        },
        scales: {
          x: { ticks: { maxTicksLimit: 20 }, grid: { display: false } },
          y: { title: { display: true, text: 'ppm' }, grid: { color: 'rgba(0,0,0,0.05)' } }
        }
      }
    });
  } catch (err) {
    console.error('CO2 chart error:', err);
  }
}

// ───────────────────────────────────────────────────────────
// 3. Dual-Axis Temp + CO₂ Chart
// ───────────────────────────────────────────────────────────
async function initTempCO2Chart(startYear, endYear) {
  const canvas = document.getElementById('tempCo2Chart');
  if (!canvas) return;
  destroyChart('tempCo2');

  try {
    const data = await fetchData('/api/chart/history', startYear, endYear);
    const labels = data.labels || [];
    const temps  = data.temp_anomaly || [];
    const co2    = (data.co2 || []).map(v => (v === null || v === 0) ? null : v);

    chartRegistry['tempCo2'] = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Temp Anomaly (°C)',
            data: temps,
            borderColor: ES.forest,
            backgroundColor: 'transparent',
            borderWidth: 2,
            tension: 0.3,
            pointRadius: 0,
            yAxisID: 'yTemp',
          },
          {
            label: 'CO₂ (ppm)',
            data: co2,
            borderColor: ES.sage,
            backgroundColor: 'transparent',
            borderWidth: 2,
            tension: 0.35,
            pointRadius: 0,
            spanGaps: false,
            yAxisID: 'yCO2',
          }
        ],
      },
      options: {
        plugins: {
          title: { display: true, text: 'Temperature vs CO₂', font: { size: 16, family: "'Fraunces', serif" } },
        },
        scales: {
          x: { ticks: { maxTicksLimit: 20 }, grid: { display: false } },
          yTemp: {
            type: 'linear',
            position: 'left',
            title: { display: true, text: '°C Anomaly' },
            grid: { color: 'rgba(0,0,0,0.05)' },
          },
          yCO2: {
            type: 'linear',
            position: 'right',
            title: { display: true, text: 'CO₂ ppm' },
            grid: { drawOnChartArea: false },
          }
        }
      }
    });
  } catch (err) {
    console.error('TempCO2 chart error:', err);
  }
}

// ───────────────────────────────────────────────────────────
// 4. Forecast Chart
// ───────────────────────────────────────────────────────────
async function initForecastChart() {
  const canvas = document.getElementById('forecastChart');
  if (!canvas) return;
  destroyChart('forecast');

  try {
    const data = await fetchData('/api/chart/forecast');
    const labels   = data.labels || [];
    const forecast = data.forecast || [];
    const lower    = data.lower || [];
    const upper    = data.upper || [];
    const threshold = data.threshold || 1.5;

    chartRegistry['forecast'] = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Forecast',
            data: forecast,
            borderColor: ES.pine,
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            tension: 0.3,
            pointRadius: 4,
            pointBackgroundColor: ES.pine,
          },
          {
            label: 'Upper Bound',
            data: upper,
            borderColor: hexToRgba(ES.leaf, 0.4),
            backgroundColor: hexToRgba(ES.leaf, 0.12),
            borderWidth: 1,
            borderDash: [4, 4],
            tension: 0.3,
            pointRadius: 0,
            fill: '+1',  // fill between upper and lower
          },
          {
            label: 'Lower Bound',
            data: lower,
            borderColor: hexToRgba(ES.leaf, 0.4),
            backgroundColor: 'transparent',
            borderWidth: 1,
            borderDash: [4, 4],
            tension: 0.3,
            pointRadius: 0,
          },
          {
            label: `Threshold (${threshold}°C)`,
            data: Array(labels.length).fill(threshold),
            borderColor: ES.critical,
            backgroundColor: 'transparent',
            borderWidth: 2,
            borderDash: [8, 4],
            pointRadius: 0,
          }
        ],
      },
      options: {
        plugins: {
          title: { display: true, text: '12-Month Temperature Forecast', font: { size: 16, family: "'Fraunces', serif" } },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y != null ? ctx.parsed.y.toFixed(3) : '—'} °C`
            }
          }
        },
        scales: {
          x: { grid: { display: false } },
          y: {
            title: { display: true, text: '°C Anomaly' },
            grid: { color: 'rgba(0,0,0,0.05)' },
            suggestedMin: 1.0,
            suggestedMax: 2.0,
          }
        }
      }
    });
  } catch (err) {
    console.error('Forecast chart error:', err);
  }
}

// ───────────────────────────────────────────────────────────
// 5. GHG Emissions Bar Chart (placeholder / static demo)
// ───────────────────────────────────────────────────────────
function initGHGChart() {
  const canvas = document.getElementById('ghgChart');
  if (!canvas) return;
  destroyChart('ghg');

  const labels = ['CO₂', 'CH₄', 'N₂O', 'F-gases'];
  const values = [74.4, 17.3, 6.2, 2.1];  // approximate IPCC %

  chartRegistry['ghg'] = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Share of Global GHG (%)',
        data: values,
        backgroundColor: [ES.forest, ES.sage, ES.leaf, ES.chipBg],
        borderRadius: 8,
        maxBarThickness: 60,
      }],
    },
    options: {
      plugins: {
        title: { display: true, text: 'Greenhouse Gas Composition', font: { size: 16, family: "'Fraunces', serif" } },
      },
      scales: {
        x: { grid: { display: false } },
        y: { title: { display: true, text: '%' }, grid: { color: 'rgba(0,0,0,0.05)' }, beginAtZero: true }
      }
    }
  });
}

// ───────────────────────────────────────────────────────────
// 6. Live Page Functions
// ───────────────────────────────────────────────────────────
let liveChart = null;
let liveBuffer = [];
let liveIndex = 0;
const LIVE_MAX_POINTS = 60;

async function initLiveChart() {
  const canvas = document.getElementById('liveChart');
  if (!canvas) return;
  destroyChart('live');

  liveChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Temp Anomaly (live)',
        data: [],
        borderColor: ES.forest,
        backgroundColor: hexToRgba(ES.forest, 0.08),
        fill: true,
        borderWidth: 2,
        tension: 0.25,
        pointRadius: 3,
        pointBackgroundColor: ctx => {
          const v = ctx.raw;
          return (v && v.quarantined) ? ES.critical : ES.forest;
        },
      }],
    },
    options: {
      animation: { duration: 300 },
      plugins: {
        title: { display: true, text: 'Live Sensor Feed', font: { size: 16, family: "'Fraunces', serif" } },
      },
      scales: {
        x: { grid: { display: false } },
        y: { title: { display: true, text: '°C' }, grid: { color: 'rgba(0,0,0,0.05)' } }
      }
    }
  });
  chartRegistry['live'] = liveChart;

  // Pre-load data buffer
  try {
    const res = await fetch('/api/chart/history?start_year=2020&end_year=2026');
    const data = await res.json();
    liveBuffer = (data.temp_anomaly || []).slice(-120);
    liveIndex = 0;
  } catch (e) {
    console.warn('Live data pre-load failed, using synthetic:', e);
    liveBuffer = Array.from({ length: 120 }, () => 0.9 + Math.random() * 0.5);
  }
}

function liveStep() {
  if (!liveChart) return;
  if (liveIndex >= liveBuffer.length) liveIndex = 0;

  const val = liveBuffer[liveIndex];
  const now = new Date();
  const timeLabel = now.toLocaleTimeString();
  const threshold = parseFloat(document.getElementById('liveThreshold')?.value || '1.5');

  // Quarantine spike detection: value > threshold → mark red
  const isSpike = val > threshold;

  liveChart.data.labels.push(timeLabel);
  liveChart.data.datasets[0].data.push(val);

  // Colour points dynamically
  if (!liveChart.data.datasets[0].pointBackgroundColor ||
      typeof liveChart.data.datasets[0].pointBackgroundColor === 'function') {
    liveChart.data.datasets[0].pointBackgroundColor = [];
  }
  liveChart.data.datasets[0].pointBackgroundColor.push(isSpike ? ES.critical : ES.forest);

  // Keep rolling window
  if (liveChart.data.labels.length > LIVE_MAX_POINTS) {
    liveChart.data.labels.shift();
    liveChart.data.datasets[0].data.shift();
    if (Array.isArray(liveChart.data.datasets[0].pointBackgroundColor)) {
      liveChart.data.datasets[0].pointBackgroundColor.shift();
    }
  }

  liveChart.update('none');
  liveIndex++;

  // Update spike counter in UI
  const spikeCount = document.getElementById('spikeCount');
  if (spikeCount && isSpike) {
    spikeCount.textContent = parseInt(spikeCount.textContent || '0') + 1;
  }
}

let liveInterval = null;

function startLiveFeed() {
  if (liveInterval) return;
  liveInterval = setInterval(liveStep, 1500);
  const btn = document.getElementById('btnLiveToggle');
  if (btn) { btn.textContent = 'Pause'; btn.classList.add('btn-danger'); btn.classList.remove('btn-forest'); }
}

function stopLiveFeed() {
  clearInterval(liveInterval);
  liveInterval = null;
  const btn = document.getElementById('btnLiveToggle');
  if (btn) { btn.textContent = 'Resume'; btn.classList.remove('btn-danger'); btn.classList.add('btn-forest'); }
}

function toggleLiveFeed() {
  liveInterval ? stopLiveFeed() : startLiveFeed();
}

// ───────────────────────────────────────────────────────────
// 7. Year Filter Handler
// ───────────────────────────────────────────────────────────
function applyYearFilter() {
  const startYear = document.getElementById('startYear')?.value || '';
  const endYear   = document.getElementById('endYear')?.value || '';
  const chartType = document.getElementById('chartTypeToggle')?.value || 'line';

  // Re-init whichever charts are on the current page
  initHistoryChart(startYear, endYear, chartType);
  initCO2Chart(startYear, endYear);
  initTempCO2Chart(startYear, endYear);
}

// ───────────────────────────────────────────────────────────
// 8. Chart Type Toggle (line ↔ bar)
// ───────────────────────────────────────────────────────────
function toggleChartType() {
  const sel = document.getElementById('chartTypeToggle');
  if (!sel) return;
  applyYearFilter();  // re-draws history chart with new type
}

// ───────────────────────────────────────────────────────────
// Utility
// ───────────────────────────────────────────────────────────
function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// ───────────────────────────────────────────────────────────
// Auto-init on DOMContentLoaded
// ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Dashboard / History page charts
  if (document.getElementById('historyChart'))  initHistoryChart();
  if (document.getElementById('co2Chart'))      initCO2Chart();
  if (document.getElementById('tempCo2Chart'))  initTempCO2Chart();
  if (document.getElementById('ghgChart'))      initGHGChart();

  // Forecast page
  if (document.getElementById('forecastChart')) initForecastChart();

  // Live page
  if (document.getElementById('liveChart')) {
    initLiveChart().then(() => startLiveFeed());
  }

  // Bind filter button
  const filterBtn = document.getElementById('btnApplyFilter');
  if (filterBtn) filterBtn.addEventListener('click', applyYearFilter);

  // Bind chart type toggle
  const typeToggle = document.getElementById('chartTypeToggle');
  if (typeToggle) typeToggle.addEventListener('change', toggleChartType);

  // Bind live toggle
  const liveToggleBtn = document.getElementById('btnLiveToggle');
  if (liveToggleBtn) liveToggleBtn.addEventListener('click', toggleLiveFeed);
});
