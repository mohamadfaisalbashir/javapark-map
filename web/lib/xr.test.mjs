// Jalankan: npm test (dari folder web/)
import assert from 'node:assert/strict';
import test from 'node:test';
import { arah, arahHp, selisih, urlPanorama } from './xr.js';

const dekat = (a, b) => assert.ok(Math.abs(selisih(a, b)) < 0.01, `${a} != ${b}`);

test('arah ke empat mata angin', () => {
  const o = { lat: -7, lon: 110 };
  dekat(arah(o, { lat: -6.9, lon: 110 }), 0);
  dekat(arah(o, { lat: -7, lon: 110.1 }), 90);
  dekat(arah(o, { lat: -7.1, lon: 110 }), 180);
  dekat(arah(o, { lat: -7, lon: 109.9 }), 270);
});

test('selisih sudut melewati utara', () => {
  assert.equal(selisih(350, 10), 20);
  assert.equal(selisih(10, 350), -20);
  assert.equal(selisih(0, 180), -180);
  assert.equal(selisih(90, 90), 0);
});

test('arah hadap HP', () => {
  assert.equal(arahHp({ webkitCompassHeading: 42, alpha: 0 }), 42);
  assert.equal(arahHp({ absolute: false, alpha: 10, beta: 90, gamma: 0 }), null); // relatif, bukan kompas
  assert.equal(arahHp({ absolute: true, alpha: null, beta: null, gamma: null }), null); // laptop
  dekat(arahHp({ absolute: true, alpha: 0, beta: 90, gamma: 0 }), 0); // tegak menghadap utara
  dekat(arahHp({ absolute: true, alpha: 90, beta: 90, gamma: 0 }), 270); // alpha naik = berputar ke kiri
  dekat(arahHp({ absolute: true, alpha: 270, beta: 80, gamma: 0 }), 90);
});

test('url panorama', () => {
  const f = (p) => ({ properties: p, geometry: { coordinates: [110.1, -7.2] } });
  assert.equal(urlPanorama(f({ vr_source: 'mapillary', mapillary_id: '123' })),
    'https://www.mapillary.com/embed?image_key=123&style=photo');
  assert.equal(urlPanorama(f({ vr_source: null })), null);
  assert.equal(urlPanorama(f({ vr_source: 'google' })), null); // tanpa NEXT_PUBLIC_GOOGLE_MAPS_EMBED_KEY
});
