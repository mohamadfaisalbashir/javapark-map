// Jalankan: npm test (dari folder web/)
import assert from 'node:assert/strict';
import test from 'node:test';
import { bentukRute, dekode6, jarakTempuh, pandu, teksManuver } from './rute.js';

const kira = (a, b, tol, pesan) => assert.ok(Math.abs(a - b) <= tol, `${pesan ?? ''} ${a} != ${b} ±${tol}`);

test('dekode6: contoh polyline Google (presisi 5 dibaca presisi 6 = ÷10)', () => {
  const p = dekode6('_p~iF~ps|U_ulLnnqC_mqNvxq`@');
  const harap = [[38.5, -120.2], [40.7, -120.95], [43.252, -126.453]];
  p.forEach(([a, b], i) => {
    kira(a * 10, harap[i][0], 1e-9);
    kira(b * 10, harap[i][1], 1e-9);
  });
});

test('teksManuver: Bahasa Indonesia', () => {
  assert.equal(teksManuver({ type: 15, street_names: ['Jalan Jaksa'] }), 'Belok kiri ke Jalan Jaksa');
  assert.equal(teksManuver({ type: 10 }), 'Belok kanan');
  assert.equal(teksManuver({ type: 4, street_names: ['Jalan X'] }), 'Tiba di tujuan');
  assert.equal(teksManuver({ type: 26, roundabout_exit_count: 2 }), 'Masuk bundaran, ambil jalan keluar ke-2');
  assert.equal(teksManuver({ type: 99 }), 'Lanjutkan');
});

// Rute uji di khatulistiwa: 200 m ke utara, lalu 100 m ke timur (0,0009° ≈ 100 m).
const rute = bentukRute(
  [[0, 0], [0.0009, 0], [0.0018, 0], [0.0018, 0.0009]],
  [{ begin_shape_index: 0, type: 1 }, { begin_shape_index: 2, type: 10 }, { begin_shape_index: 3, type: 4 }],
  300,
);

test('pandu: di jalur, sebelum belokan', () => {
  const p = pandu(rute, { lat: 0.00045, lon: 0.0001 }); // ±50 m di sepanjang rute, ±11 m ke timur
  kira(p.menyimpang_m, 11, 1);
  kira(p.sisa_m, 250, 2);
  kira(p.sisa_s, 250, 2);
  assert.equal(p.manuver.teks, 'Belok kanan');
  kira(p.manuver.jarak_m, 150, 2);
  assert.equal(p.menuju, false);
  assert.deepEqual(p.titikArah, { lat: 0.0009, lon: 0 }); // titik rute pertama ≥ 40 m di depan
});

test('pandu: belum di jalur (mis. di dalam bangunan) → Menuju jalur rute', () => {
  const p = pandu(rute, { lat: 0.0003, lon: 0.00045 }); // ±50 m ke timur dari garis awal
  assert.equal(p.menuju, true);
  assert.equal(p.manuver.teks, 'Menuju jalur rute');
  kira(p.manuver.jarak_m, 50, 1);
  kira(p.titikArah.lat, 0.0003, 1e-9, 'lat proyeksi');
  kira(p.titikArah.lon, 0, 1e-9, 'lon proyeksi'); // panah menunjuk ke garis, bukan ke depan
  kira(p.sisa_m, 300 - 33.4, 2);
});

test('pandu: setelah belokan dan menyimpang jauh', () => {
  let p = pandu(rute, { lat: 0.0018, lon: 0.0005 });
  assert.equal(p.manuver.teks, 'Tiba di tujuan');
  kira(p.manuver.jarak_m, 44, 2);
  assert.deepEqual(p.titikArah, { lat: 0.0018, lon: 0.0009 });
  p = pandu(rute, { lat: 0.0009, lon: 0.001 }); // ±111 m ke timur garis
  assert.ok(p.menyimpang_m > 100, `menyimpang ${p.menyimpang_m}`);
});

test('jarakTempuh: km → m, urut naik, buang > 10 km & tanpa rute, maks. 10 taman', async () => {
  const asli = globalThis.fetch;
  let url;
  // 14 kandidat: indeks 0–10 berjarak 9,5; 9; …; 4,5 km (urutan terbalik), 11 = 10 km pas, 12 = 10,9 km, 13 = tanpa rute.
  const km = [...Array.from({ length: 11 }, (_, i) => 9.5 - i * 0.5), 10, 10.9, null];
  globalThis.fetch = async (u) => {
    url = decodeURIComponent(u);
    // latitude kandidat = indeks km-nya, agar mock menjawab sesuai target yang diminta.
    const { targets } = JSON.parse(new URL(u).searchParams.get('json'));
    return {
      ok: true,
      json: async () => ({ sources_to_targets: [targets.map((t, i) => ({ to_index: i, distance: km[t.lat], time: km[t.lat] && km[t.lat] * 60 }))] }),
    };
  };
  try {
    const daftar = km.map((_, i) => ({ id: i, name: `T${i}`, latitude: i, longitude: 107 }));
    const hasil = await jarakTempuh({ lat: -6, lon: 107 }, daftar, 'motor');
    assert.equal(hasil.length, 10);
    assert.deepEqual(hasil.map((t) => t.name), ['T10', 'T9', 'T8', 'T7', 'T6', 'T5', 'T4', 'T3', 'T2', 'T1']);
    assert.deepEqual([hasil[0].rute_m, hasil[0].rute_s], [4500, 270]);
    assert.ok(hasil.every((t) => t.rute_m <= 10000));
    assert.match(url, /\/sources_to_targets\?json=.*"costing":"motorcycle"/);
    // Sedikit kandidat: 10 km pas masih masuk, 10,9 km dan tanpa rute dibuang.
    const sisa = await jarakTempuh({ lat: -6, lon: 107 }, daftar.slice(11), 'kaki');
    assert.deepEqual(sisa.map((t) => [t.name, t.rute_m]), [['T11', 10000]]);
  } finally {
    globalThis.fetch = asli;
  }
});
