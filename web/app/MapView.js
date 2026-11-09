'use client';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './leaflet-global'; // window.L harus ada sebelum plugin dimuat
import 'leaflet.markercluster';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import { useEffect } from 'react';
import { Circle, MapContainer, Marker, Polyline, ScaleControl, TileLayer, useMap } from 'react-leaflet';
import { KATEGORI } from '../lib/format';
import { urlPanorama } from '../lib/xr';

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
  const [lon, lat] = f.geometry.coordinates;
  const root = document.createElement('div');
  root.className = 'popup';
  root.append(el('p', 'popup-kat', KATEGORI[category] ?? category));
  root.append(el('h3', 'popup-nama', name));
  if (address) root.append(el('p', 'popup-alamat', address));
  root.append(el('p', 'popup-kota', `${city}, ${province}`));
  const a = el('a', 'popup-link', 'Buka di OpenStreetMap');
  a.href = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=19/${lat}/${lon}`;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  root.append(a);
  if (urlPanorama(f)) {
    const b = el('button', 'popup-vr', 'Lihat 360°'); // FR-06
    b.type = 'button';
    b.addEventListener('click', () => onVr(f));
    root.append(b);
  }
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

export default function MapView({ fitur, bbox, pos, fokus, onVr, rute, jalur }) {
  return (
    <MapContainer center={[-7.3, 110]} zoom={7} minZoom={5} zoomSnap={0.5} className="peta">
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution={ATRIBUSI} maxZoom={19} />
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
