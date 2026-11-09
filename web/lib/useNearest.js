'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import { ambilRute, jarakM, jarakTempuh, pandu } from './rute';

const GESER_MIN_M = 100; // FR-02: perbarui daftar bila bergeser > 100 m sejak request terakhir

const PESAN = {
  1: 'Izin lokasi ditolak. Izinkan akses lokasi di pengaturan peramban untuk memakai fitur ini; peta tetap bisa dipakai.',
  2: 'Posisi tidak tersedia. Pastikan GPS atau layanan lokasi perangkat aktif. Mencoba lagi…',
  3: 'Waktu habis menunggu sinyal GPS. Mencoba lagi…',
};

const MENYIMPANG_M = 40; // FR-07: lebih jauh dari garis rute = hitung ulang rute
const JEDA_ULANG_MS = 10000; // FR-07: hitung ulang paling sering sekali per 10 dtk

// mentah = respons /api/parks/nearest; asal = posisi saat request itu.
const KOSONG = { aktif: false, pos: null, mentah: null, asal: null, galat: null };

/** FR-02 + FR-07: watchPosition + 10 taman terdekat (radius 10 km), diurutkan menurut jarak tempuh moda. */
export function useNearest(moda) {
  const [s, setS] = useState(KOSONG);
  const [tempuh, setTempuh] = useState(null); // { dari, moda, daftar | null (gagal) }
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
          .then((mentah) => setS((x) => ({ ...x, mentah, asal: pos, galat: null })))
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

  // FR-07: satu request matriks setiap daftar FR-02 atau moda berubah.
  useEffect(() => {
    if (!s.mentah?.length) return undefined;
    const ac = new AbortController();
    const kunci = { dari: s.mentah, moda };
    jarakTempuh(s.asal, s.mentah, moda, ac.signal)
      .then((daftar) => setTempuh({ ...kunci, daftar }))
      .catch((e) => e.name !== 'AbortError' && setTempuh({ ...kunci, daftar: null }));
    return () => ac.abort();
  }, [s.mentah, s.asal, moda]);

  const siap = tempuh?.dari === s.mentah && tempuh.moda === moda;
  return {
    aktif: s.aktif,
    pos: s.pos,
    galat: s.galat,
    // Hanya hasil jarak tempuh (tanpa garis lurus): null selama menghitung atau bila layanan rute gagal.
    daftar: s.mentah?.length === 0 ? [] : siap ? tempuh.daftar : null,
    menghitung: !!s.mentah?.length && !siap,
    tempuhGagal: siap && !tempuh.daftar,
    fokus,
    mulai,
    berhenti,
  };
}

/** FR-07: rute ke taman `tujuan`; dihitung ulang bila moda/tujuan berubah atau pengguna keluar jalur. */
export function useRute(pos, tujuan, moda) {
  const [r, setR] = useState(null); // { rute } | { galat }
  const [ulang, setUlang] = useState(0);
  const posTerkini = useRef(pos);
  const terakhir = useRef(0);
  useEffect(() => {
    posTerkini.current = pos;
  });

  useEffect(() => {
    setR(null);
  }, [tujuan, moda]);

  useEffect(() => {
    if (!tujuan || !posTerkini.current) return undefined;
    const ac = new AbortController();
    terakhir.current = Date.now();
    ambilRute(posTerkini.current, tujuan, moda, ac.signal)
      .then((rute) => setR({ rute }))
      .catch((e) => e.name !== 'AbortError' && setR({ galat: 'Rute tidak dapat dihitung. Periksa koneksi, atau taman tidak terjangkau dengan moda ini.' }));
    return () => ac.abort();
  }, [tujuan, moda, ulang]);

  const p = r?.rute && pos ? pandu(r.rute, pos) : null;
  const keluar = !!p && p.menyimpang_m > MENYIMPANG_M + (pos?.akurasi ?? 0);
  useEffect(() => {
    if (keluar && Date.now() - terakhir.current > JEDA_ULANG_MS) setUlang((n) => n + 1);
  });

  return { rute: r?.rute ?? null, pandu: p, galat: r?.galat ?? null };
}
