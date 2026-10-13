import { Plus_Jakarta_Sans, Young_Serif } from 'next/font/google';
import './globals.css';

const display = Young_Serif({ subsets: ['latin'], weight: '400', variable: '--font-display', display: 'swap' });
const body = Plus_Jakarta_Sans({ subsets: ['latin'], variable: '--font-body', display: 'swap' });

export const metadata = {
  title: 'Taman Kota Pulau Jawa — Peta Taman Publik Gratis',
  description:
    'Peta interaktif taman kota gratis tanpa tiket masuk di Banten, DKI Jakarta, Jawa Barat, Jawa Tengah, DI Yogyakarta, dan Jawa Timur. Data © OpenStreetMap contributors.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="id" className={`${display.variable} ${body.variable}`}>
      <body>{children}</body>
    </html>
  );
}
