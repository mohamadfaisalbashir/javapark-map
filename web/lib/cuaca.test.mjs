// Jalankan: npm test (dari folder web/)
import assert from 'node:assert/strict';
import test from 'node:test';
import { teksCuaca } from './cuaca.js';

test('teksCuaca: kode WMO → teks Indonesia', () => {
  assert.equal(teksCuaca(0), 'Cerah');
  assert.equal(teksCuaca(1), 'Cerah berawan');
  assert.equal(teksCuaca(3), 'Berawan');
  assert.equal(teksCuaca(51), 'Gerimis');
  assert.equal(teksCuaca(63), 'Hujan');
  assert.equal(teksCuaca(80), 'Hujan lokal');
  assert.equal(teksCuaca(95), 'Badai petir');
  assert.equal(teksCuaca(120), 'Cuaca tidak diketahui');
});
