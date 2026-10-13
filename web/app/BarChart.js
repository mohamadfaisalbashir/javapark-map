'use client';
import { BarElement, CategoryScale, Chart as ChartJS, LinearScale, Tooltip } from 'chart.js';
import { useMemo } from 'react';
import { Bar } from 'react-chartjs-2';
import { ringkasNama } from '../lib/format';

ChartJS.register(BarElement, CategoryScale, LinearScale, Tooltip);

const INK = '#14342a';
const MOSS = '#2e6b4a';
const CLAY = '#c4552d';
const RULE = '#cfc6ab';

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// Angka di ujung batang (tanpa plugin pihak ketiga).
const angkaUjung = {
  id: 'angkaUjung',
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    ctx.save();
    ctx.font = `14px ${css('--font-display') || 'serif'}`;
    ctx.fillStyle = INK;
    ctx.textBaseline = 'middle';
    chart.getDatasetMeta(0).data.forEach((bar, i) => {
      ctx.fillText(chart.data.datasets[0].data[i].toLocaleString('id-ID'), bar.x + 6, bar.y);
    });
    ctx.restore();
  },
};

/** FR-04: bar chart jumlah taman per kota/kabupaten (urutan sudah menurun dari API). */
export default function BarChart({ data, kotaId }) {
  const chartData = useMemo(
    () => ({
      labels: data.map((d) => ringkasNama(d.city_name)),
      datasets: [{
        data: data.map((d) => d.count),
        backgroundColor: data.map((d) => (String(d.city_id) === String(kotaId) ? CLAY : MOSS)),
        borderWidth: 0,
        barPercentage: 0.74,
        categoryPercentage: 0.92,
      }],
    }),
    [data, kotaId],
  );

  const options = useMemo(() => ({
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: { right: 44 } },
    font: { family: css('--font-body') || 'sans-serif' },
    scales: {
      x: { beginAtZero: true, ticks: { precision: 0, color: INK }, grid: { color: RULE }, border: { display: false } },
      y: { ticks: { color: INK, autoSkip: false, font: { size: 12 } }, grid: { display: false }, border: { color: INK } },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => data[items[0].dataIndex].city_name,
          label: (c) => `${c.parsed.x.toLocaleString('id-ID')} taman`,
        },
      },
    },
  }), [data]);

  const ringkas = data.length
    ? `Bar chart jumlah taman per kota atau kabupaten. Tertinggi: ${data[0].city_name}, ${data[0].count} taman.`
    : 'Bar chart kosong.';

  return (
    <div className="chart" style={{ height: Math.max(130, data.length * 26 + 36) }}>
      <Bar data={chartData} options={options} plugins={[angkaUjung]} role="img" aria-label={ringkas} />
    </div>
  );
}
