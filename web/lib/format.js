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

// Label sumbu chart diperpendek agar muat di layar sempit; nama lengkap tetap di tooltip.
export const ringkasNama = (n) => n
  .replace('Kota Administrasi ', '')
  .replace('Kabupaten Administrasi ', 'Kab. ')
  .replace('Kabupaten ', 'Kab. ');
