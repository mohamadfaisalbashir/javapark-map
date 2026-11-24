export const KATEGORI = {
  taman_kota: 'Taman Kota',
  rth: 'RTH Publik',
  alun_alun: 'Alun-alun',
};

// 260 -> "260 m", 1234 -> "1,2 km"
export function jarakLabel(m) {
  if (m < 1000) return `${Math.round(m)} m`;
  return `${(m / 1000).toLocaleString('id-ID', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} km`;
}

// FR-07: 45 -> "1 mnt", 2000 -> "33 mnt", 4500 -> "1 j 15 mnt"
export function waktuLabel(dtk) {
  const mnt = Math.max(1, Math.round(dtk / 60));
  return mnt < 60 ? `${mnt} mnt` : `${Math.floor(mnt / 60)} j${mnt % 60 ? ` ${mnt % 60} mnt` : ''}`;
}

// Label sumbu chart diperpendek agar muat di layar sempit; nama lengkap tetap di tooltip.
export const ringkasNama = (n) => n
  .replace('Kota Administrasi ', '')
  .replace('Kabupaten Administrasi ', 'Kab. ')
  .replace('Kabupaten ', 'Kab. ');

// FR-11: 5 jenis fasilitas yang didata (kunci = nilai kolom parks.facilities & header fasilitas_taman.csv).
export const FASILITAS = {
  toilet: 'Toilet',
  mushola: 'Mushola',
  bermain: 'Area bermain anak',
  jogging: 'Jogging track',
  olahraga: 'Lapangan olahraga',
};

// FR-12: cari taman menurut kegiatan; cocok bila taman punya SALAH SATU fasilitasnya.
export const KEGIATAN = {
  anak: { label: 'Bawa anak', fas: ['bermain'] },
  olahraga: { label: 'Olahraga', fas: ['jogging', 'olahraga'] },
};

/** FR-09/11/12: properti taman lolos saringan? q = teks cari huruf kecil; fas = fasilitas yang WAJIB ada semua. */
export function cocok(p, { kat = '', kegiatan = '', fas = [], q = '' }) {
  const ada = new Set(p.facilities ?? []);
  return (!kat || p.category === kat)
    && (!kegiatan || KEGIATAN[kegiatan].fas.some((f) => ada.has(f)))
    && fas.every((f) => ada.has(f))
    && (!q || p.name.toLowerCase().includes(q));
}
