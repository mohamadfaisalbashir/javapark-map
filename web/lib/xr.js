// FR-05 (AR) dan FR-06 (VR 360°): fungsi murni, diuji di xr.test.mjs (`npm test`).

// >>> API KEY: isi NEXT_PUBLIC_GOOGLE_MAPS_EMBED_KEY di .env (lihat .env.example), lalu build ulang web.
// Kosong = tombol 360° untuk taman ber-vr_source "google" tidak tampil (FR-06).
const KUNCI_EMBED = process.env.NEXT_PUBLIC_GOOGLE_MAPS_EMBED_KEY;

const rad = Math.PI / 180;

/** Bearing awal dari a ke b, derajat searah jarum jam dari utara [0, 360). */
export function arah(a, b) {
  const f1 = a.lat * rad;
  const f2 = b.lat * rad;
  const dl = (b.lon - a.lon) * rad;
  const y = Math.sin(dl) * Math.cos(f2);
  const x = Math.cos(f1) * Math.sin(f2) - Math.sin(f1) * Math.cos(f2) * Math.cos(dl);
  return (Math.atan2(y, x) / rad + 360) % 360;
}

/** b − a dalam rentang [−180, 180). */
export const selisih = (a, b) => ((((b - a) % 360) + 540) % 360) - 180;

/** Arah hadap kamera belakang dari event deviceorientation; null bila perangkat tidak memberi arah absolut. */
export function arahHp(e) {
  if (e.webkitCompassHeading != null) return e.webkitCompassHeading; // Safari iOS
  if (!e.absolute || e.alpha == null || e.beta == null || e.gamma == null) return null;
  // Spesifikasi W3C DeviceOrientation, contoh "compass heading": arah sumbu −z (punggung HP).
  const [a, b, g] = [e.alpha * rad, e.beta * rad, e.gamma * rad];
  const vx = -Math.cos(a) * Math.sin(g) - Math.sin(a) * Math.sin(b) * Math.cos(g);
  const vy = -Math.sin(a) * Math.sin(g) + Math.cos(a) * Math.sin(b) * Math.cos(g);
  return (Math.atan2(vx, vy) / rad + 360) % 360;
}

/** URL iframe panorama 360° sebuah fitur GeoJSON taman, atau null bila tidak tersedia. */
export function urlPanorama({ properties: p, geometry: g }) {
  const [lon, lat] = g.coordinates;
  if (p.vr_source === 'google' && KUNCI_EMBED) {
    return `https://www.google.com/maps/embed/v1/streetview?key=${encodeURIComponent(KUNCI_EMBED)}&location=${lat},${lon}`;
  }
  if (p.vr_source === 'mapillary' && p.mapillary_id) {
    return `https://www.mapillary.com/embed?image_key=${encodeURIComponent(p.mapillary_id)}&style=photo`;
  }
  return null;
}
