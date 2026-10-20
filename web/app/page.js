'use client';
import dynamic from 'next/dynamic';
import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { KATEGORI, jarakLabel } from '../lib/format';
import { useNearest } from '../lib/useNearest';
import BarChart from './BarChart';

// Leaflet butuh `window`: komponen peta tidak dirender di server.
const MapView = dynamic(() => import('./MapView'), {
  ssr: false,
  loading: () => <div className="map-pesan">Memuat peta…</div>,
});

const JAWA = [104.9, -8.95, 114.9, -5.5]; // [minLon, minLat, maxLon, maxLat]
const TOP_N = 20; // FR-04: tanpa filter tampilkan 20 kota/kabupaten teratas

function useCountUp(target) {
  const [nilai, setNilai] = useState(target);
  const dari = useRef(target);
  useEffect(() => {
    if (target == null) return undefined;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || dari.current == null) {
      dari.current = target;
      setNilai(target);
      return undefined;
    }
    const mulai = performance.now();
    const a = dari.current;
    let raf;
    const langkah = (t) => {
      const k = Math.min(1, (t - mulai) / 700);
      setNilai(Math.round(a + (target - a) * (1 - (1 - k) ** 3)));
      if (k < 1) raf = requestAnimationFrame(langkah);
      else dari.current = target;
    };
    raf = requestAnimationFrame(langkah);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return nilai;
}

export default function Halaman() {
  const [regions, setRegions] = useState([]);
  const [provinsiId, setProvinsiId] = useState('');
  const [kotaId, setKotaId] = useState('');
  const [resetN, setResetN] = useState(0);
  const [data, setData] = useState({ parks: null, stats: [], bbox: JAWA });
  const [galat, setGalat] = useState(null);
  const nearest = useNearest();

  useEffect(() => {
    const ac = new AbortController();
    api.regions(ac.signal).then(setRegions).catch((e) => {
      if (e.name !== 'AbortError') setGalat('Daftar wilayah tidak dapat dimuat. Pastikan API berjalan.');
    });
    return () => ac.abort();
  }, []);

  // FR-03: peta, bar chart, dan batas zoom mengikuti filter yang sama.
  useEffect(() => {
    const ac = new AbortController();
    const wilayah = kotaId ? ['city', kotaId] : provinsiId ? ['province', provinsiId] : null;
    const q = wilayah ? { [wilayah[0] === 'city' ? 'city_id' : 'province_id']: wilayah[1] } : {};
    setGalat(null);
    Promise.all([
      api.parks(q, ac.signal),
      api.stats(wilayah ? q : { limit: TOP_N }, ac.signal),
      wilayah ? api.bbox(wilayah[0], wilayah[1], ac.signal) : null,
    ])
      .then(([parks, stats, bb]) => setData({ parks, stats, bbox: bb ? bb.bbox : [...JAWA] }))
      .catch((e) => {
        if (e.name !== 'AbortError') setGalat('Data taman tidak dapat dimuat. Pastikan API berjalan lalu muat ulang halaman.');
      });
    return () => ac.abort();
  }, [provinsiId, kotaId, resetN]);

  const provinsi = regions.find((p) => String(p.id) === provinsiId);
  const daftarKota = provinsi?.cities ?? [];
  const kota = daftarKota.find((c) => String(c.id) === kotaId);
  const cakupan = kota ? kota.name : provinsi ? provinsi.name : 'seluruh Pulau Jawa';
  const jumlah = data.parks ? data.parks.features.length : null;
  const angka = useCountUp(jumlah);

  const pilihProvinsi = (e) => {
    setProvinsiId(e.target.value);
    setKotaId('');
  };
  const reset = () => {
    setProvinsiId('');
    setKotaId('');
    setResetN((n) => n + 1);
  };

  return (
    <div className="shell">
      <aside className="panel">
        <header className="masthead rise" style={{ '--i': 0 }}>
          <p className="kicker">
            <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
              <circle cx="16" cy="16" r="15" fill="none" stroke="currentColor" />
              <circle cx="16" cy="13" r="6.4" fill="currentColor" />
              <path d="M16 18v8" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
            </svg>
            Atlas taman publik
          </p>
          <h1>
            Taman Kota
            <span>Pulau Jawa</span>
          </h1>
          <p className="lede">Temukan taman publik tanpa tiket masuk, dari alun-alun kota sampai RTH di sekitar Anda.</p>
          <p className="count-row">
            <span className="count" aria-hidden="true">{angka == null ? '—' : angka.toLocaleString('id-ID')}</span>
            <span className="count-cap" aria-hidden="true">
              taman ditampilkan
              <b>di {cakupan}</b>
            </span>
            {/* Angka beranimasi disembunyikan dari pembaca layar; hanya nilai akhir yang diumumkan. */}
            <span className="sr-only" aria-live="polite">
              {jumlah == null ? '' : `${jumlah.toLocaleString('id-ID')} taman ditampilkan di ${cakupan}`}
            </span>
          </p>
        </header>

        <section className="sec rise" style={{ '--i': 1 }} aria-labelledby="h-wilayah">
          <h2 id="h-wilayah"><span className="num" aria-hidden="true">I</span>Wilayah</h2>
          <label className="field">
            <span>Provinsi</span>
            <select value={provinsiId} onChange={pilihProvinsi}>
              <option value="">Semua provinsi</option>
              {regions.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Kota / Kabupaten</span>
            <select value={kotaId} onChange={(e) => setKotaId(e.target.value)} disabled={!provinsi}>
              <option value="">Semua kota/kabupaten</option>
              {daftarKota.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <button type="button" className="btn btn-text" onClick={reset}>Reset filter</button>
          {galat && <p className="galat" role="alert">{galat}</p>}
        </section>

        <section className="sec rise" style={{ '--i': 2 }} aria-labelledby="h-terdekat">
          <h2 id="h-terdekat"><span className="num" aria-hidden="true">II</span>Terdekat</h2>
          <p className="hint">10 taman terdekat dalam radius 10 km dari posisi Anda, diperbarui saat Anda berpindah.</p>
          <button
            type="button"
            className={`btn ${nearest.aktif ? 'btn-ghost' : 'btn-primary'}`}
            aria-pressed={nearest.aktif}
            onClick={nearest.aktif ? nearest.berhenti : nearest.mulai}
          >
            {nearest.aktif ? 'Hentikan pelacakan' : 'Taman Terdekat'}
          </button>
          <div className="status" aria-live="polite">
            {nearest.galat && <p className="galat">{nearest.galat}</p>}
            {!nearest.galat && nearest.aktif && !nearest.pos && <p>Menunggu sinyal GPS…</p>}
            {!nearest.galat && nearest.pos && nearest.daftar == null && <p>Mencari taman terdekat…</p>}
            {nearest.pos && <p className="akurasi">Akurasi GPS ±{Math.round(nearest.pos.akurasi)} m</p>}
            {nearest.daftar?.length === 0 && <p>Tidak ada taman dalam radius 10 km dari posisi Anda.</p>}
          </div>
          {nearest.daftar?.length > 0 && (
            <ol className="near">
              {nearest.daftar.map((t, i) => (
                <li key={t.id}>
                  <span className="n">{i + 1}</span>
                  <span className="nm">{t.name}<small>{KATEGORI[t.category] ?? t.category}</small></span>
                  <span className="d">{jarakLabel(t.distance_m)}</span>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="sec rise" style={{ '--i': 3 }} aria-labelledby="h-statistik">
          <h2 id="h-statistik"><span className="num" aria-hidden="true">III</span>Statistik</h2>
          <p className="hint">
            Jumlah taman per kota/kabupaten
            {!provinsiId && !kotaId ? `, ${TOP_N} teratas se-Jawa.` : ` di ${cakupan}.`}
          </p>
          {data.stats.length > 0 ? <BarChart data={data.stats} kotaId={kotaId} /> : <p className="hint">Memuat statistik…</p>}
        </section>

        <footer className="foot rise" style={{ '--i': 4 }}>
          <p>
            Data taman: inventaris tim (114 taman kota). Peta dasar &amp; batas wilayah &copy;{' '}
            <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>.
            Taman = ruang terbuka hijau publik tanpa tiket masuk.
          </p>
        </footer>
      </aside>

      <main className="stage">
        <div className="frame">
          <MapView fitur={data.parks?.features ?? []} bbox={data.bbox} pos={nearest.pos} fokus={nearest.fokus} />
          {data.parks == null && !galat && <div className="map-pesan">Memuat data taman…</div>}
        </div>
      </main>
    </div>
  );
}
