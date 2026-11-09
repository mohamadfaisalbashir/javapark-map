'use client';
import dynamic from 'next/dynamic';
import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import { KATEGORI, jarakLabel, waktuLabel } from '../lib/format';
import { MODA } from '../lib/rute';
import { useNearest, useRute } from '../lib/useNearest';
import BarChart from './BarChart';
import PilihModa from './PilihModa';
import { ArView, Viewer360 } from './Xr';

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
  const [ar, setAr] = useState(null); // FR-05: null = tertutup, { izinArah } = terbuka
  const [vr, setVr] = useState(null); // FR-06: fitur taman yang panoramanya dibuka
  const [moda, setModa] = useState('kaki'); // FR-07
  const [tujuan, setTujuan] = useState(null); // FR-07: taman yang rutenya ditampilkan
  const nearest = useNearest(moda);
  const rute = useRute(nearest.pos, tujuan, moda);

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
  const bukaAr = async () => {
    let izinArah = true;
    // Safari iOS dan Chrome versi baru: izin sensor arah wajib diminta langsung dari ketukan pengguna.
    if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
      izinArah = await DeviceOrientationEvent.requestPermission().then((s) => s === 'granted', () => false);
    }
    setAr({ izinArah });
  };
  // FR-07: pilih/batalkan rute; di HP peta ada di atas daftar, jadi gulir ke peta agar rutenya terlihat.
  const pilihRute = (t) => {
    const batal = tujuan?.id === t.id;
    setTujuan(batal ? null : t);
    if (!batal) {
      const halus = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      document.querySelector('.stage')?.scrollIntoView({ behavior: halus ? 'smooth' : 'auto', block: 'start' });
    }
  };
  const berhentiLacak = () => {
    nearest.berhenti();
    setTujuan(null);
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
          <p className="hint">Maksimal 10 taman dengan jarak tempuh ≤ 10 km menurut moda pilihan Anda, diperbarui saat Anda berpindah.</p>
          <PilihModa moda={moda} onModa={setModa} />
          <button
            type="button"
            className={`btn ${nearest.aktif ? 'btn-ghost' : 'btn-primary'}`}
            aria-pressed={nearest.aktif}
            onClick={nearest.aktif ? berhentiLacak : nearest.mulai}
          >
            {nearest.aktif ? 'Hentikan pelacakan' : 'Taman Terdekat'}
          </button>
          <div className="status" aria-live="polite">
            {nearest.galat && <p className="galat">{nearest.galat}</p>}
            {!nearest.galat && nearest.aktif && !nearest.pos && <p>Menunggu sinyal GPS…</p>}
            {!nearest.galat && nearest.pos && nearest.daftar == null && !nearest.tempuhGagal && (
              <p>Menghitung jarak tempuh ({MODA[moda].label.toLowerCase()})…</p>
            )}
            {nearest.pos && <p className="akurasi">Akurasi GPS ±{Math.round(nearest.pos.akurasi)} m</p>}
            {nearest.daftar?.length === 0 && (
              <p>Tidak ada taman dengan jarak tempuh ≤ 10 km ({MODA[moda].label.toLowerCase()}) dari posisi Anda.</p>
            )}
            {nearest.tempuhGagal && <p className="galat">Jarak tempuh tidak dapat dihitung (layanan rute tidak tersedia). Coba lagi nanti.</p>}
          </div>
          {nearest.daftar?.length > 0 && (
            <ol className="near">
              {nearest.daftar.map((t, i) => (
                <li key={t.id}>
                  <span className="n">{i + 1}</span>
                  <span className="nm">{t.name}<small>{KATEGORI[t.category] ?? t.category}</small></span>
                  <span className="d">
                    {jarakLabel(t.rute_m)}
                    <small>±{waktuLabel(t.rute_s)}</small>
                  </span>
                  <button
                    type="button"
                    className="btn-rute"
                    aria-pressed={tujuan?.id === t.id}
                    aria-label={`Rute ke ${t.name}`}
                    onClick={() => pilihRute(t)}
                  >
                    Rute
                  </button>
                </li>
              ))}
            </ol>
          )}
          {nearest.daftar?.length > 0 && (
            <button type="button" className="btn btn-primary btn-ar" onClick={bukaAr}>Mode AR</button>
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
          <MapView
            fitur={data.parks?.features ?? []}
            bbox={data.bbox}
            pos={nearest.pos}
            fokus={nearest.fokus}
            onVr={setVr}
            rute={rute.rute?.titik}
          />
          {data.parks == null && !galat && <div className="map-pesan">Memuat data taman…</div>}
          {/* FR-07: kartu rute di atas peta (ala Google Maps). */}
          {tujuan && (
            <section className="kartu-rute" aria-label={`Rute ke ${tujuan.name}`}>
              <div className="kartu-kepala">
                <p>Rute ke <b>{tujuan.name}</b></p>
                <button type="button" className="kartu-tutup" aria-label="Tutup rute" onClick={() => setTujuan(null)}>×</button>
              </div>
              <PilihModa moda={moda} onModa={setModa} kecil />
              {rute.galat && <p className="galat">{rute.galat}</p>}
              {!rute.galat && !rute.pandu && <p className="kartu-ket">Menghitung rute…</p>}
              <div className="kartu-aksi">
                {rute.pandu && (
                  <p className="kartu-waktu">
                    {waktuLabel(rute.pandu.sisa_s)} <span>({jarakLabel(rute.pandu.sisa_m)})</span>
                  </p>
                )}
                <button type="button" className="btn btn-primary kartu-mulai" onClick={bukaAr}>Mulai (AR)</button>
              </div>
              {rute.pandu && (
                <p className="kartu-ket">
                  Berikutnya: <b>{rute.pandu.manuver.teks}</b> · {jarakLabel(rute.pandu.manuver.jarak_m)}
                </p>
              )}
            </section>
          )}
        </div>
      </main>

      {/* AR disembunyikan (kamera dimatikan) selama panorama dibuka dari label AR; menutup panorama = kembali ke AR. */}
      {ar && !vr && (
        <ArView
          pos={nearest.pos}
          daftar={nearest.daftar ?? []}
          izinArah={ar.izinArah}
          onTutup={() => setAr(null)}
          onVr={setVr}
          moda={moda}
          onModa={setModa}
          tujuan={tujuan}
          pandu={rute.pandu}
          onNavigasi={setTujuan}
          onAkhiriNav={() => setTujuan(null)}
        />
      )}
      {vr && <Viewer360 fitur={vr} onTutup={() => setVr(null)} labelTutup={ar ? 'Kembali ke Mode AR' : 'Tutup'} />}
    </div>
  );
}
