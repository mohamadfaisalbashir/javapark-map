'use client';
import { useEffect, useRef, useState } from 'react';
import { jarakLabel } from '../lib/format';
import { arah, arahHp, selisih, urlPanorama } from '../lib/xr';

// FR-05: kalibrasi saat uji lapangan (NFR-08).
const SETENGAH_FOV = 30; // sudut pandang kamera belakang HP tegak, ± derajat dari tengah layar
const HALUS = 0.2; // 0..1; makin kecil makin halus, tapi label makin lambat mengikuti
const TUNGGU_KOMPAS_MS = 3000; // tanpa arah absolut selama ini = perangkat tanpa kompas

/** Layar penuh bersama untuk AR dan VR: judul, tombol Tutup, Escape, fokus dikembalikan saat ditutup. */
function Layar({ kat, judul, onTutup, children }) {
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
        <button ref={tutup} type="button" className="btn btn-ghost layar-tutup" onClick={onTutup}>Tutup</button>
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
export function ArView({ pos, daftar, izinArah, onTutup }) {
  const video = useRef(null);
  const [hadap, setHadap] = useState(null);
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
    return Math.abs(d) > SETENGAH_FOV ? [] : [{ t, x: 50 + (d / SETENGAH_FOV) * 30, y: 14 + i * 7 }];
  });

  return (
    <Layar kat="Mode AR · taman terdekat" judul="Arahkan kamera ke sekitar Anda" onTutup={onTutup}>
      <video ref={video} className="ar-video" autoPlay playsInline muted />
      {galat ? <p className="galat layar-galat" role="alert">{galat}</p> : (
        <>
          {label.map(({ t, x, y }) => (
            <div key={t.id} className="ar-label" style={{ left: `${x}%`, top: `${y}%` }}>
              <b>{t.name}</b>
              <span>{jarakLabel(t.distance_m)}</span>
            </div>
          ))}
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

/** FR-06: panorama 360° Google Street View / Mapillary dalam iframe. */
export function Viewer360({ fitur, onTutup }) {
  const p = fitur.properties;
  const sumber = p.vr_source === 'google' ? 'Google Street View' : 'Mapillary';
  return (
    <Layar kat={`Panorama 360° · ${sumber}`} judul={p.name} onTutup={onTutup}>
      <iframe
        className="layar-iframe"
        src={urlPanorama(fitur)}
        title={`Panorama 360° ${p.name} (${sumber})`}
        allow="accelerometer; gyroscope; fullscreen"
        allowFullScreen
      />
    </Layar>
  );
}
