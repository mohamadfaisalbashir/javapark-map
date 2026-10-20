'use client';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import './leaflet-global'; // window.L harus ada sebelum plugin dimuat
import 'leaflet.markercluster';
import 'leaflet.markercluster/dist/MarkerCluster.css';
import { useEffect } from 'react';
import { Circle, MapContainer, Marker, ScaleControl, TileLayer, useMap } from 'react-leaflet';
import { KATEGORI } from '../lib/format';

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

function isiPopup(f) {
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
  return root;
}

function LapisTaman({ fitur }) {
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
        return L.marker([lat, lon], { icon: ikonTaman, title: f.properties.name, alt: f.properties.name })
          .bindPopup(() => isiPopup(f), { maxWidth: 280 });
      }),
    );
    map.addLayer(grup);
    return () => {
      map.removeLayer(grup);
    };
  }, [fitur, map]);
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

export default function MapView({ fitur, bbox, pos, fokus }) {
  return (
    <MapContainer center={[-7.3, 110]} zoom={7} minZoom={5} zoomSnap={0.5} className="peta">
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution={ATRIBUSI} maxZoom={19} />
      <ScaleControl imperial={false} position="bottomleft" />
      <LapisTaman fitur={fitur} />
      <FitBounds bbox={bbox} />
      <FlyTo fokus={fokus} />
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
