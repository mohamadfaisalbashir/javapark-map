// FR-07: jarak tempuh & rute per moda lewat Valhalla publik FOSSGIS (CORS terbuka, tanpa kunci API).
// Fungsi murni diuji di rute.test.mjs (`npm test`).
// ponytail: server demo FOSSGIS (batas pemakaian wajar, tanpa SLA); untuk produksi self-host Valhalla dengan PBF Jawa.
const VALHALLA = 'https://valhalla1.openstreetmap.de';
const LIHAT_DEPAN_M = 40; // panah AR menunjuk titik rute sejauh ini di depan pengguna
const MAKS_M = 10000; // FR-02/FR-07: hanya taman dengan jarak tempuh ≤ 10 km
const MAKS_TAMAN = 10;

export const MODA = {
  kaki: { label: 'Jalan kaki', costing: 'pedestrian' },
  motor: { label: 'Motor', costing: 'motorcycle' },
  mobil: { label: 'Mobil', costing: 'auto' },
};

const rad = Math.PI / 180;

/** Jarak haversine dua titik {lat, lon}, meter. */
export function jarakM(a, b) {
  const h = Math.sin(((b.lat - a.lat) * rad) / 2) ** 2
    + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(((b.lon - a.lon) * rad) / 2) ** 2;
  return 2 * 6371008.8 * Math.asin(Math.sqrt(h));
}

/** Dekode encoded polyline presisi 6 (format shape Valhalla) → [[lat, lon], ...]. */
export function dekode6(s) {
  const out = [];
  let i = 0;
  let lat = 0;
  let lon = 0;
  while (i < s.length) {
    const v = [0, 0];
    for (let k = 0; k < 2; k++) {
      let b;
      let geser = 0;
      let r = 0;
      do {
        b = s.charCodeAt(i++) - 63;
        r |= (b & 0x1f) << geser;
        geser += 5;
      } while (b >= 0x20);
      v[k] = r & 1 ? ~(r >> 1) : r >> 1;
    }
    lat += v[0];
    lon += v[1];
    out.push([lat / 1e6, lon / 1e6]);
  }
  return out;
}

// Valhalla belum punya bahasa Indonesia: teks disusun dari jenis manuver (dokumentasi Valhalla, "maneuver types").
const AKSI = {
  4: 'Tiba di tujuan', 5: 'Tiba di tujuan', 6: 'Tiba di tujuan',
  7: 'Lurus', 8: 'Lurus', 17: 'Lurus', 22: 'Tetap lurus', 25: 'Bergabung',
  9: 'Agak ke kanan', 10: 'Belok kanan', 11: 'Belok tajam ke kanan', 18: 'Ambil jalur kanan',
  20: 'Keluar ke kanan', 23: 'Tetap di kanan', 37: 'Bergabung ke kanan',
  16: 'Agak ke kiri', 15: 'Belok kiri', 14: 'Belok tajam ke kiri', 19: 'Ambil jalur kiri',
  21: 'Keluar ke kiri', 24: 'Tetap di kiri', 38: 'Bergabung ke kiri',
  12: 'Putar balik', 13: 'Putar balik', 26: 'Masuk bundaran', 27: 'Keluar bundaran',
  28: 'Naik feri', 29: 'Turun dari feri', 39: 'Naik lift', 40: 'Lewat tangga', 41: 'Naik eskalator',
};

/** Teks instruksi berbahasa Indonesia dari satu manuver Valhalla. */
export function teksManuver(m) {
  if (m.type >= 4 && m.type <= 6) return AKSI[m.type];
  let t = AKSI[m.type] ?? 'Lanjutkan';
  if (m.type === 26 && m.roundabout_exit_count) t += `, ambil jalan keluar ke-${m.roundabout_exit_count}`;
  const jalan = m.street_names?.[0];
  return jalan ? `${t} ke ${jalan}` : t;
}

async function valhalla(layanan, isi, signal) {
  const res = await fetch(`${VALHALLA}/${layanan}?json=${encodeURIComponent(JSON.stringify(isi))}`, { signal });
  if (!res.ok) throw new Error(`Valhalla ${res.status}`);
  return res.json();
}

/**
 * Jarak & waktu tempuh dari `asal` ke tiap kandidat (satu request matriks): maks. 10 taman berjarak tempuh ≤ 10 km,
 * urut naik. Kandidat = taman ≤ 10 km garis lurus; jarak lewat jalan selalu ≥ garis lurus, jadi tidak ada yang terlewat.
 */
export async function jarakTempuh(asal, daftar, moda, signal) {
  const d = await valhalla('sources_to_targets', {
    sources: [{ lat: asal.lat, lon: asal.lon }],
    targets: daftar.map((t) => ({ lat: t.latitude, lon: t.longitude })),
    costing: MODA[moda].costing,
  }, signal);
  const sel = new Map(d.sources_to_targets[0].map((x) => [x.to_index, x]));
  return daftar
    .map((t, i) => {
      const x = sel.get(i);
      return { ...t, rute_m: x?.distance == null ? null : x.distance * 1000, rute_s: x?.time ?? null };
    })
    .filter((t) => t.rute_m != null && t.rute_m <= MAKS_M)
    .sort((a, b) => a.rute_m - b.rute_m)
    .slice(0, MAKS_TAMAN);
}

/** Rute `asal` → taman `tujuan`: titik garis, jarak kumulatif (m), manuver, waktu total (s). */
export async function ambilRute(asal, tujuan, moda, signal) {
  const d = await valhalla('route', {
    locations: [{ lat: asal.lat, lon: asal.lon }, { lat: tujuan.latitude, lon: tujuan.longitude }],
    costing: MODA[moda].costing,
  }, signal);
  const leg = d.trip.legs[0];
  return bentukRute(dekode6(leg.shape), leg.maneuvers, leg.summary.time);
}

export function bentukRute(titik, maneuvers, total_s) {
  const kum = [0];
  for (let i = 1; i < titik.length; i++) {
    kum.push(kum[i - 1] + jarakM({ lat: titik[i - 1][0], lon: titik[i - 1][1] }, { lat: titik[i][0], lon: titik[i][1] }));
  }
  return { titik, kum, total_s, manuver: maneuvers.map((m) => ({ i: m.begin_shape_index, teks: teksManuver(m) })) };
}

/**
 * Posisi pengguna terhadap rute: jarak menyimpang dari garis, sisa jarak/waktu,
 * manuver berikutnya beserta jaraknya, dan titik yang ditunjuk panah AR.
 */
export function pandu({ titik, kum, manuver, total_s }, pos) {
  // Proyeksi ekuirektangular lokal di sekitar pengguna (cukup akurat untuk radius ≤ 10 km).
  const kx = Math.cos(pos.lat * rad) * 111320;
  const ky = 110540;
  let best = { d: Infinity, j: 0, t: 0 };
  for (let j = 0; j < titik.length - 1; j++) {
    const ax = (titik[j][1] - pos.lon) * kx;
    const ay = (titik[j][0] - pos.lat) * ky;
    const dx = (titik[j + 1][1] - titik[j][1]) * kx;
    const dy = (titik[j + 1][0] - titik[j][0]) * ky;
    const l2 = dx * dx + dy * dy;
    const t = l2 ? Math.min(1, Math.max(0, -(ax * dx + ay * dy) / l2)) : 0;
    const d = Math.hypot(ax + t * dx, ay + t * dy);
    if (d < best.d) best = { d, j, t };
  }
  const total = kum.at(-1);
  const sudah = kum[best.j] + best.t * ((kum[best.j + 1] ?? kum[best.j]) - kum[best.j]);
  const sisa = Math.max(0, total - sudah);
  const berikut = manuver.find((m) => kum[m.i] > sudah + 5) ?? manuver.at(-1);
  const k = kum.findIndex((x) => x >= sudah + LIHAT_DEPAN_M);
  const [lat, lon] = titik[k < 0 ? titik.length - 1 : k];
  return {
    menyimpang_m: titik.length > 1 ? best.d : jarakM(pos, { lat, lon }),
    sisa_m: sisa,
    sisa_s: total ? (total_s * sisa) / total : 0,
    manuver: { teks: berikut.teks, jarak_m: Math.max(0, kum[berikut.i] - sudah) },
    titikArah: { lat, lon },
  };
}
