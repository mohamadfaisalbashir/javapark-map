'use client';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './leaflet-global'; // window.L harus ada sebelum plugin dimuat
import 'leaflet.markercluster';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import { useEffect } from 'react';
import { Circle, MapContainer, Marker, Polygon, Polyline, ScaleControl, TileLayer, useMap } from 'react-leaflet';
import { FASILITAS, KATEGORI } from '../lib/format';
import { titikPanorama } from '../lib/xr';

// 6.1: atribusi wajib peta dasar + sumber data taman.
const ATRIBUSI = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &middot; data taman: inventaris tim';

const ikonTaman = L.divIcon({ className: 'pk', iconSize: [16, 16] });
const ikonSaya = L.divIcon({ className: 'me', html: '<i></i>', iconSize: [26, 26] });
const kurangiGerak = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function el(tag, kelas, teks) {
  const e = document.createElement(tag);
  e.className = kelas;
  e.textContent = teks; // textContent: nama dari OSM adalah data tak tepercaya
  return e;
}

function isiPopup(f, onVr) {
  const { name, category, address, city, province } = f.properties;
  const root = document.createElement('div');
  root.className = 'popup';
  root.append(el('p', 'popup-kat', KATEGORI[category] ?? category));
  root.append(el('h3', 'popup-nama', name));
  // Gambar taman = titik tur pertama lewat Maps Embed (gratis tanpa batas); statis: tak bisa diklik/digeser.
  const foto = titikPanorama(f)[0];
  if (foto) {
    const ifr = el('iframe', 'popup-foto', '');
    ifr.src = foto.url;
    ifr.title = `Gambar ${name}`;
    ifr.loading = 'lazy';
    ifr.tabIndex = -1;
    ifr.setAttribute('aria-hidden', 'true');
    root.append(ifr);
  }
  if (address) root.append(el('p', 'popup-alamat', address));
  root.append(el('p', 'popup-kota', `${city}, ${province}`));
  // FR-11: label fasilitas.
  const fas = f.properties.facilities ?? [];
  if (fas.length) {
    const ul = el('ul', 'fas', '');
    ul.setAttribute('aria-label', 'Fasilitas');
    fas.forEach((k) => ul.append(el('li', '', FASILITAS[k] ?? k)));
    root.append(ul);
  }
  const b = el('button', 'popup-vr', titikPanorama(f).length ? 'Tur virtual 360°' : 'Tur virtual'); // FR-06: semua taman
  b.type = 'button';
  b.addEventListener('click', () => onVr(f));
  root.append(b);
  return root;
}

function LapisTaman({ fitur, onVr }) {
  const map = useMap();
  useEffect(() => {
    const grup = L.markerClusterGroup({
      chunkedLoading: true,
      showCoverageOnHover: false,
      maxClusterRadius: 48,
      animate: !kurangiGerak,
      iconCreateFunction: (c) => {
        const n = c.getChildCount();
        const [kelas, ukuran] = n < 10 ? ['s', 34] : n < 100 ? ['m', 42] : ['l', 52];
        return L.divIcon({ html: `<span>${n}</span>`, className: `cluster ${kelas}`, iconSize: [ukuran, ukuran] });
      },
    });
    grup.addLayers(
      fitur.map((f) => {
        const [lon, lat] = f.geometry.coordinates;
        const m = L.marker([lat, lon], { icon: ikonTaman, title: f.properties.name, alt: f.properties.name });
        return m.bindPopup(() => isiPopup(f, onVr), { maxWidth: 280, minWidth: 240 });
      }),
    );
    map.addLayer(grup);
    return () => {
      map.removeLayer(grup);
    };
  }, [fitur, map, onVr]);
  return null;
}

function FitBounds({ bbox }) {
  const map = useMap();
  useEffect(() => {
    const [w, s, e, n] = bbox;
    map.fitBounds([[s, w], [n, e]], { padding: [28, 28] });
  }, [bbox, map]);
  return null;
}

function FlyTo({ fokus }) {
  const map = useMap();
  useEffect(() => {
    if (fokus) map.flyTo([fokus.lat, fokus.lon], Math.max(map.getZoom(), 14));
  }, [fokus, map]);
  return null;
}

// FR-07: tampilkan seluruh rute setiap rute baru dihitung; ruang bawah untuk kartu rute.
function FitRute({ rute }) {
  const map = useMap();
  useEffect(() => {
    if (rute?.length > 1) map.fitBounds(rute, { paddingTopLeft: [40, 40], paddingBottomRight: [40, 240], maxZoom: 17 });
  }, [rute, map]);
  return null;
}

export default function MapView({ fitur, bbox, pos, fokus, onVr, rute, jalur, iso }) {
  return (
    <MapContainer center={[-7.3, 110]} zoom={7} minZoom={5} zoomSnap={0.5} className="peta">
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution={ATRIBUSI} maxZoom={19} />
      {/* FR-08: wilayah terjangkau 15/10/5 menit, terluas digambar dulu. */}
      {iso?.map(({ menit, ring }) => (
        <Polygon key={menit} positions={ring} pathOptions={{ color: '#2e6b4a', weight: 1.5, fillColor: '#2e6b4a', fillOpacity: 0.13 }} interactive={false} />
      ))}
      <ScaleControl imperial={false} position="bottomleft" />
      <LapisTaman fitur={fitur} onVr={onVr} />
      <FitBounds bbox={bbox} />
      <FlyTo fokus={fokus} />
      {rute && (
        <>
          <Polyline positions={rute} pathOptions={{ color: '#14342a', weight: 8, opacity: 0.35 }} interactive={false} />
          <Polyline positions={rute} pathOptions={{ color: '#c4552d', weight: 4 }} interactive={false} />
          <FitRute rute={rute} />
        </>
      )}
      {/* FR-07: garis putus-putus dari posisi pengguna ke jalur rute selama belum di jalur (mis. dari dalam bangunan). */}
      {jalur && <Polyline positions={jalur} pathOptions={{ color: '#c4552d', weight: 3, dashArray: '2 8' }} interactive={false} />}
      {pos && (
        <>
          <Circle
            center={[pos.lat, pos.lon]}
            radius={pos.akurasi}
            pathOptions={{ color: '#c4552d', weight: 1, fillColor: '#c4552d', fillOpacity: 0.12 }}
          />
          <Marker position={[pos.lat, pos.lon]} icon={ikonSaya} interactive={false} keyboard={false} />
        </>
      )}
    </MapContainer>
  );
}
