// Chart.js helpers (Section 9.4): one smooth white line with a soft fade, dashed reference
// lines, coloured dots only where something happened, tooltips with value + plain verdict.
// Needs the vendored Chart.js UMD + annotation plugin loaded as classic scripts first.

const STATUS = { good: '#2EE59D', okay: '#3B9EFF', watch: '#FFC53D', alert: '#FF4D6D' };
const VERDICT = { good: 'Good', okay: 'Okay', watch: 'Needs attention', alert: 'Get help now' };

export function chartAvailable() {
  return typeof window.Chart === 'function';
}

function fade(context) {
  const { chart } = context;
  const { ctx, chartArea } = chart;
  if (!chartArea) return 'rgba(255,255,255,0.06)';
  const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
  gradient.addColorStop(0, 'rgba(255,255,255,0.16)');
  gradient.addColorStop(1, 'rgba(255,255,255,0)');
  return gradient;
}

const shortDate = (value) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

export function trendChart(canvas, series, { unit = '', reference = [], label = '', second = null } = {}) {
  if (!chartAvailable()) return null;
  const points = series.points || [];
  const radius = points.map((p) => (p.status === 'alert' || p.status === 'watch' ? 4 : 0));
  const colors = points.map((p) => STATUS[p.status] || '#F2F4F7');
  const datasets = [{
    label, data: points.map((p) => p.v), borderColor: '#F2F4F7', borderWidth: 2, tension: 0.4, fill: true,
    backgroundColor: fade, pointRadius: radius, pointBackgroundColor: colors, pointBorderWidth: 0,
    pointHoverRadius: 5,
  }];
  if (second) {
    datasets.push({ label: second.label, data: points.map((p) => p.v2 ?? null), borderColor: '#8E97A6',
      borderWidth: 1.5, borderDash: [4, 4], tension: 0.4, pointRadius: 0, fill: false });
  }
  const annotations = {};
  reference.forEach((value, index) => {
    annotations[`ref${index}`] = { type: 'line', yMin: value, yMax: value, borderColor: 'rgba(255,255,255,0.18)',
      borderWidth: 1, borderDash: [5, 5] };
  });
  return new window.Chart(canvas, {
    type: 'line',
    data: { labels: points.map((p) => shortDate(p.t)), datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { grid: { display: false }, ticks: { color: '#8E97A6', maxTicksLimit: 6, maxRotation: 0 },
          border: { display: false } },
        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8E97A6', maxTicksLimit: 5 },
          border: { display: false } },
      },
      plugins: {
        legend: { display: false },
        annotation: { annotations },
        tooltip: {
          backgroundColor: '#07090D', borderColor: 'rgba(255,255,255,0.16)', borderWidth: 1, padding: 10,
          titleColor: '#F2F4F7', bodyColor: '#A3ABB8',
          callbacks: {
            label(item) {
              const point = points[item.dataIndex];
              const value = item.datasetIndex === 1 ? point.v2 : point.v;
              const verdict = VERDICT[point.status] ? ` · ${VERDICT[point.status]}` : '';
              return `${value}${unit ? ` ${unit}` : ''}${item.datasetIndex === 0 ? verdict : ''}`;
            },
          },
        },
      },
    },
  });
}

export function barLineChart(canvas, history) {
  if (!chartAvailable()) return null;
  const labels = history.map((row) => shortDate(row.t));
  return new window.Chart(canvas, {
    data: {
      labels,
      datasets: [
        { type: 'bar', label: 'Heart rate', data: history.map((row) => row.hr), borderRadius: 6,
          backgroundColor: history.map((row) => (row.current ? '#F2F4F7' : 'rgba(255,255,255,0.18)')) },
        { type: 'line', label: 'Blood pressure (top number)', data: history.map((row) => row.sys),
          borderColor: '#8E97A6', borderDash: [4, 4], tension: 0.35, pointRadius: 2, yAxisID: 'y2' },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: { grid: { display: false }, ticks: { color: '#8E97A6' }, border: { display: false } },
        y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#8E97A6' }, border: { display: false },
          title: { display: true, text: 'bpm', color: '#8E97A6' } },
        y2: { position: 'right', grid: { display: false }, ticks: { color: '#8E97A6' }, border: { display: false },
          title: { display: true, text: 'mmHg', color: '#8E97A6' } },
      },
      plugins: { legend: { labels: { color: '#A3ABB8', boxWidth: 12 } } },
    },
  });
}

export function statusColor(key) {
  return STATUS[key] || '#F2F4F7';
}
