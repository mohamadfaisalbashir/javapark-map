// Jalankan: npm test (dari folder web/)
import assert from 'node:assert/strict';
import test from 'node:test';
import { FASILITAS, KEGIATAN, cocok } from './format.js';

const p = (facilities, extra = {}) => ({ name: 'Taman Bungkul', category: 'taman_kota', facilities, ...extra });

test('cocok: kategori, kegiatan (salah satu), fasilitas (semua), nama', () => {
  const t = p(['bermain', 'toilet', 'jogging']);
  assert.equal(cocok(t, {}), true);
  assert.equal(cocok(t, { kat: 'rth' }), false);
  assert.equal(cocok(t, { kegiatan: 'anak' }), true);
  assert.equal(cocok(t, { kegiatan: 'olahraga' }), true); // jogging saja sudah cukup
  assert.equal(cocok(p(['toilet']), { kegiatan: 'anak' }), false);
  assert.equal(cocok(t, { fas: ['toilet', 'bermain'] }), true);
  assert.equal(cocok(t, { fas: ['toilet', 'mushola'] }), false);
  assert.equal(cocok(t, { q: 'bungkul' }), true);
  assert.equal(cocok(t, { q: 'flora' }), false);
  assert.equal(cocok(p(undefined), { fas: ['toilet'] }), false); // data lama tanpa kolom fasilitas
});

test('kegiatan hanya memakai fasilitas yang terdaftar', () => {
  assert.equal(Object.keys(FASILITAS).length, 5);
  for (const k of Object.values(KEGIATAN)) for (const f of k.fas) assert.ok(f in FASILITAS, f);
});
