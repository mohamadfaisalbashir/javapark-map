// Jalankan: npm test (dari folder web/)
import assert from 'node:assert/strict';
import test from 'node:test';
import { FASILITAS, cocok } from './format.js';

const p = (facilities, extra = {}) => ({ name: 'Taman Bungkul', category: 'taman_kota', facilities, ...extra });

test('cocok: kategori, fasilitas (semua), nama', () => {
  const t = p(['bermain', 'toilet', 'jogging']);
  assert.equal(cocok(t, {}), true);
  assert.equal(cocok(t, { kat: 'rth' }), false);
  assert.equal(cocok(t, { fas: ['toilet', 'bermain'] }), true);
  assert.equal(cocok(t, { fas: ['toilet', 'mushola'] }), false);
  assert.equal(cocok(t, { q: 'bungkul' }), true);
  assert.equal(cocok(t, { q: 'flora' }), false);
  assert.equal(cocok(p(undefined), { fas: ['toilet'] }), false); // data lama tanpa kolom fasilitas
});

test('5 jenis fasilitas', () => {
  assert.deepEqual(Object.keys(FASILITAS), ['toilet', 'mushola', 'bermain', 'jogging', 'olahraga']);
});
