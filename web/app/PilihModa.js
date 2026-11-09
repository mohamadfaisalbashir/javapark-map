'use client';
import { useId } from 'react';
import { MODA } from '../lib/rute';

/** FR-07: pilihan moda perjalanan (sidebar, kartu rute, Mode AR); satu state `moda` di halaman. */
export default function PilihModa({ moda, onModa, kecil = false }) {
  const name = useId(); // tiap instance grup radio sendiri; nama sama akan saling mengosongkan
  return (
    <fieldset className={kecil ? 'moda moda-kecil' : 'moda'}>
      <legend className={kecil ? 'sr-only' : undefined}>Moda perjalanan</legend>
      {Object.entries(MODA).map(([k, m]) => (
        <label key={k}>
          <input type="radio" name={name} value={k} checked={moda === k} onChange={() => onModa(k)} />
          <span>{m.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
