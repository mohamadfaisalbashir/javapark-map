'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';

const GESER_MIN_M = 100; // FR-02: perbarui daftar bila bergeser > 100 m sejak request terakhir

const PESAN = {
  1: 'Izin lokasi ditolak. Izinkan akses lokasi di pengaturan peramban untuk memakai fitur ini; peta tetap bisa dipakai.',
  2: 'Posisi tidak tersedia. Pastikan GPS atau layanan lokasi perangkat aktif. Mencoba lagi…',
  3: 'Waktu habis menunggu sinyal GPS. Mencoba lagi…',
};

function jarakM(a, b) {
  const rad = Math.PI / 180;
  const h = Math.sin(((b.lat - a.lat) * rad) / 2) ** 2
    + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(((b.lon - a.lon) * rad) / 2) ** 2;
  return 2 * 6371008.8 * Math.asin(Math.sqrt(h));
}

const KOSONG = { aktif: false, pos: null, daftar: null, galat: null };

/** FR-02: watchPosition + daftar 10 taman terdekat (radius 10 km). */
export function useNearest() {
  const [s, setS] = useState(KOSONG);
  const [fokus, setFokus] = useState(null); // posisi fix pertama, untuk flyTo sekali
  const watch = useRef(null);
  const terakhir = useRef(null); // posisi pada request terakhir
  const abort = useRef(null);

  const hentikan = useCallback(() => {
    if (watch.current != null) navigator.geolocation.clearWatch(watch.current);
    watch.current = null;
    abort.current?.abort();
  }, []);

  const berhenti = useCallback(() => {
    hentikan();
    setS(KOSONG);
  }, [hentikan]);

  const mulai = useCallback(() => {
    hentikan();
    if (!('geolocation' in navigator)) {
      setS({ ...KOSONG, galat: 'Peramban ini tidak mendukung geolokasi.' });
      return;
    }
    if (!window.isSecureContext) {
      setS({ ...KOSONG, galat: 'GPS hanya berfungsi lewat HTTPS atau localhost.' });
      return;
    }
    terakhir.current = null;
    let pertama = true;
    setS({ ...KOSONG, aktif: true });

    watch.current = navigator.geolocation.watchPosition(
      ({ coords }) => {
        const pos = { lat: coords.latitude, lon: coords.longitude, akurasi: coords.accuracy };
        setS((x) => ({ ...x, aktif: true, pos, galat: null }));
        if (pertama) {
          pertama = false;
          setFokus({ lat: pos.lat, lon: pos.lon });
        }
        if (terakhir.current && jarakM(terakhir.current, pos) <= GESER_MIN_M) return;
        terakhir.current = pos;
        abort.current?.abort();
        abort.current = new AbortController();
        api.nearest(pos.lat, pos.lon, abort.current.signal)
          .then((daftar) => setS((x) => ({ ...x, daftar, galat: null })))
          .catch((e) => {
            if (e.name !== 'AbortError') {
              terakhir.current = null; // coba lagi pada fix berikutnya
              setS((x) => ({ ...x, galat: 'Gagal mengambil daftar taman terdekat. Periksa koneksi atau coba lagi.' }));
            }
          });
      },
      (err) => {
        // Hanya izin ditolak yang permanen. Posisi tak tersedia / timeout sering sementara
        // (sinyal GPS putus sesaat): watch dibiarkan hidup dan galat hilang saat fix berikutnya.
        const permanen = err.code === 1;
        if (permanen) hentikan();
        setS((x) => ({ ...x, aktif: permanen ? false : x.aktif, galat: PESAN[err.code] ?? 'Gagal membaca lokasi.' }));
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 },
    );
  }, [hentikan]);

  useEffect(() => hentikan, [hentikan]); // bersihkan saat unmount

  return { ...s, fokus, mulai, berhenti };
}
