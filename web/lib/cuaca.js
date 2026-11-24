// FR-06 cuaca saat ini di tur virtual, lewat Open-Meteo (gratis, tanpa kunci, CORS terbuka).
// Yang dikirim hanya koordinat taman, bukan lokasi pengguna (NFR-07). Fungsi murni diuji di cuaca.test.mjs.

// Kode cuaca WMO (dokumentasi Open-Meteo, "weather_code"): [batas atas kode, teks].
const KODE = [
  [0, 'Cerah'], [2, 'Cerah berawan'], [3, 'Berawan'], [48, 'Berkabut'], [57, 'Gerimis'],
  [67, 'Hujan'], [77, 'Salju'], [82, 'Hujan lokal'], [86, 'Salju'], [99, 'Badai petir'],
];

export const teksCuaca = (kode) => KODE.find(([maks]) => kode <= maks)?.[1] ?? 'Cuaca tidak diketahui';

/** Cuaca kini di titik taman, mis. "33°C · Berawan". */
export async function ambilCuaca(lat, lon) {
  const res = await fetch(`https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,weather_code&timezone=auto`);
  if (!res.ok) throw new Error(`Open-Meteo ${res.status}`);
  const { current: c } = await res.json();
  return `${Math.round(c.temperature_2m)}°C · ${teksCuaca(c.weather_code)}`;
}
