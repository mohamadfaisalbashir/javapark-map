// Klien API (Bagian 9). Dipanggil dari browser; basis URL disematkan saat build.
const BASE = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');

async function get(path, signal) {
  const res = await fetch(BASE + path, { signal });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

const qs = (o) => {
  const s = new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v != null)).toString();
  return s ? `?${s}` : '';
};

export const api = {
  regions: (signal) => get('/api/regions', signal),
  parks: (q, signal) => get(`/api/parks${qs(q)}`, signal),
  stats: (q, signal) => get(`/api/stats/parks-per-city${qs(q)}`, signal),
  bbox: (type, id, signal) => get(`/api/regions/${type}/${id}/bbox`, signal),
  // NFR-07: lokasi pengguna hanya dikirim sebagai query ke endpoint ini.
  nearest: (lat, lon, signal) => get(`/api/parks/nearest?lat=${lat}&lon=${lon}&limit=10&radius_km=10`, signal),
};
