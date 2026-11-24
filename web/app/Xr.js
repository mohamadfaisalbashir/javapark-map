'use client';
import { useEffect, useRef, useState } from 'react';
import { ambilCuaca } from '../lib/cuaca';
import { FASILITAS, KATEGORI, jarakLabel, waktuLabel } from '../lib/format';
import { MODA } from '../lib/rute';
import PilihModa from './PilihModa';
import { arah, arahHp, selisih, titikPanorama } from '../lib/xr';

// FR-05: kalibrasi saat uji lapangan (NFR-08).
const SETENGAH_FOV = 30; // sudut pandang kamera belakang HP tegak, ± derajat dari tengah layar
const HALUS = 0.2; // 0..1; makin kecil makin halus, tapi label makin lambat mengikuti
const TUNGGU_KOMPAS_MS = 3000; // tanpa arah absolut selama ini = perangkat tanpa kompas

/** Layar penuh bersama untuk AR dan VR: judul, tombol Tutup, Escape, fokus dikembalikan saat ditutup. */
function Layar({ kat, judul, onTutup, labelTutup = 'Tutup', children }) {
  const tutup = useRef(null);
  useEffect(() => {
    const sebelum = document.activeElement;
    tutup.current.focus();
    return () => sebelum?.focus?.();
  }, []);
  useEffect(() => {
    const esc = (e) => e.key === 'Escape' && onTutup();
    window.addEventListener('keydown', esc);
    return () => window.removeEventListener('keydown', esc);
  }, [onTutup]);
  return (
    <div className="layar" role="dialog" aria-modal="true" aria-label={judul}>
      <header className="layar-kepala">
        <div>
          <p className="popup-kat">{kat}</p>
          <h2>{judul}</h2>
        </div>
        <button ref={tutup} type="button" className="btn btn-ghost layar-tutup" onClick={onTutup}>{labelTutup}</button>
      </header>
      <div className="layar-isi">{children}</div>
    </div>
  );
}

function galatAwal(izinArah) {
  if (!izinArah) return 'Izin sensor gerak/orientasi ditolak. Izinkan di pengaturan situs peramban, lalu buka Mode AR lagi.';
  if (!window.isSecureContext) return 'Mode AR butuh HTTPS (atau localhost).';
  if (!navigator.mediaDevices?.getUserMedia) return 'Peramban ini tidak mendukung akses kamera.';
  return null;
}

/** FR-05: label taman FR-02 di atas tampilan kamera, mengikuti arah hadap HP. */
export function ArView({ pos, daftar, izinArah, onTutup, onVr, moda, onModa }) {
  const video = useRef(null);
  const [hadap, setHadap] = useState(null);
  const [pilih, setPilih] = useState(null); // taman yang labelnya diketuk → panel pilihan
  const [galat, setGalat] = useState(() => galatAwal(izinArah));

  useEffect(() => {
    if (galat) return undefined;
    let h = null;
    let stream = null;
    let hidup = true;
    const henti = (s) => s?.getTracks().forEach((t) => t.stop());
    // Kamera baru dibuka setelah kompas terbukti ada, agar webcam laptop tidak menyala sia-sia (TC-13).
    const bukaKamera = () => navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      .then((s) => {
        if (!hidup) return henti(s);
        stream = s;
        video.current.srcObject = s;
        return undefined;
      })
      .catch((e) => hidup && setGalat(e.name === 'NotAllowedError'
        ? 'Izin kamera ditolak. Izinkan akses kamera di pengaturan peramban; peta tetap bisa dipakai.'
        : 'Kamera tidak dapat dibuka di perangkat ini.'));
    const baca = (e) => {
      const baru = arahHp(e);
      if (baru == null) return;
      if (h == null) bukaKamera();
      h = h == null ? baru : (h + selisih(h, baru) * HALUS + 360) % 360;
      setHadap(h);
    };
    // Chrome Android: event absolut terpisah. Safari iOS: deviceorientation + webkitCompassHeading.
    const jenis = 'ondeviceorientationabsolute' in window ? 'deviceorientationabsolute' : 'deviceorientation';
    window.addEventListener(jenis, baca);
    const t = setTimeout(() => {
      if (h == null) setGalat('Perangkat ini tidak punya kompas (mis. laptop). Mode AR hanya untuk HP.');
    }, TUNGGU_KOMPAS_MS);
    return () => {
      hidup = false;
      clearTimeout(t);
      window.removeEventListener(jenis, baca);
      henti(stream);
    };
  }, [galat]);

  // Urutan daftar = urutan jarak; baris ke-i diberi tinggi sendiri agar label searah tidak bertumpuk.
  const label = hadap == null || !pos ? [] : daftar.flatMap((t, i) => {
    const d = selisih(hadap, arah(pos, { lat: t.latitude, lon: t.longitude }));
    return Math.abs(d) > SETENGAH_FOV ? [] : [{ t, x: 50 + (d / SETENGAH_FOV) * 30, y: 18 + i * 6 }];
  });
  // Item /api/parks/nearest dibungkus jadi fitur GeoJSON agar titikPanorama & TurVirtual bisa dipakai ulang.
  const fiturDari = (t) => ({ properties: t, geometry: { coordinates: [t.longitude, t.latitude] } });

  return (
    <Layar kat={`Mode AR · ${MODA[moda].label}`} judul="Arahkan kamera ke sekitar Anda" onTutup={onTutup}>
      <video ref={video} className="ar-video" autoPlay playsInline muted />
      {galat ? <p className="galat layar-galat" role="alert">{galat}</p> : (
        <>
          <div className="ar-moda"><PilihModa moda={moda} onModa={onModa} kecil /></div>
          {label.map(({ t, x, y }) => (
            <button
              key={t.id}
              type="button"
              className="ar-label"
              aria-label={`${t.name}, ${jarakLabel(t.rute_m)}: detail dan tur virtual`}
              style={{ left: `${x}%`, top: `${y}%` }}
              onClick={() => setPilih(t)}
            >
              <b>{t.name}</b>
              <span>{jarakLabel(t.rute_m)}</span>
              {titikPanorama(fiturDari(t)).length > 0 && <small>360°</small>}
            </button>
          ))}
          {/* FR-05: panel tetap (tidak ikut goyang kompas) setelah label diketuk. */}
          {pilih && (
            <div className="ar-pilih" role="group" aria-label={`Pilihan untuk ${pilih.name}`}>
              <p><b>{pilih.name}</b><span>{jarakLabel(pilih.rute_m)} · ±{waktuLabel(pilih.rute_s)} ({MODA[moda].label.toLowerCase()})</span></p>
              <div className="ar-pilih-tombol">
                <button type="button" className="btn btn-primary" onClick={() => onVr(fiturDari(pilih))}>Tur virtual</button>
                <button type="button" className="btn btn-text" onClick={() => setPilih(null)}>Batal</button>
              </div>
            </div>
          )}
          <p className="ar-info">
            {hadap == null ? 'Membaca kompas…' : (
              <>
                <span aria-live="polite">
                  {label.length ? `${label.length} taman di depan Anda` : 'Tidak ada taman di depan. Putar badan perlahan.'}
                </span>
                <span className="ar-arah">Arah {Math.round(hadap)}°</span>
              </>
            )}
          </p>
        </>
      )}
    </Layar>
  );
}

/**
 * FR-06: tur virtual 360° di DALAM taman: maks. 3 titik panorama (etl/cek_pano.py), plus cuaca kini dan fasilitas (FR-11).
 * Taman tanpa panorama di dalamnya: satu panorama dari tepi, menghadap ke taman.
 */
export function TurVirtual({ fitur, onTutup, labelTutup }) {
  const p = fitur.properties;
  const [lon, lat] = fitur.geometry.coordinates;
  const titik = titikPanorama(fitur);
  const [n, setN] = useState(0);
  const [cuaca, setCuaca] = useState(null);
  const fas = p.facilities ?? [];

  useEffect(() => {
    let hidup = true;
    setN(0);
    setCuaca(null);
    ambilCuaca(lat, lon).then((x) => hidup && setCuaca(x), () => {}); // pelengkap: gagal = tidak tampil
    return () => {
      hidup = false;
    };
  }, [lat, lon]);

  const t = titik[n];
  return (
    <Layar kat={`Tur virtual · ${KATEGORI[p.category] ?? p.category}`} judul={p.name} onTutup={onTutup} labelTutup={labelTutup}>
      <div className="tur-info">
        <p>
          {p.city && <b>{p.city}, {p.province}</b>}
          {cuaca && <span>Cuaca kini: {cuaca}</span>}
        </p>
        {titik.length > 1 && (
          <div className="tur-tab" role="group" aria-label="Titik tur">
            {titik.map((x, i) => (
              <button key={x.url} type="button" aria-pressed={i === n} onClick={() => setN(i)}>Titik {i + 1}</button>
            ))}
          </div>
        )}
      </div>
      {(fas.length > 0 || t?.tepi) && (
        <div className="tur-detail">
          {fas.length > 0 && (
            <ul className="fas" aria-label="Fasilitas">
              {fas.map((k) => <li key={k}>{FASILITAS[k] ?? k}</li>)}
            </ul>
          )}
          {t?.tepi && <p className="tur-catatan">Belum ada panorama di dalam taman ini; tampilan dari tepi taman.</p>}
        </div>
      )}
      <div className="tur-tampil">
        {t ? (
          <>
            {/* Isi iframe transparan sampai panorama tergambar: teks ini terlihat selama memuat (data seluler bisa lama). */}
            <p className="vr-muat" aria-hidden="true">Memuat panorama 360°…</p>
            <iframe
              key={t.url}
              className="layar-iframe"
              src={t.url}
              title={`Panorama 360° ${p.name}, titik ${n + 1}`}
              allow="accelerometer; gyroscope; fullscreen"
            />
          </>
        ) : <p className="vr-muat">Panorama 360° taman ini belum tersedia.</p>}
      </div>
    </Layar>
  );
}
