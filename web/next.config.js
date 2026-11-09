// Browser memanggil /api/* di asal yang sama; server Next meneruskannya ke FastAPI.
// Jadi cukup satu alamat (mis. satu tunnel ke port 3000) untuk web + API.
// API_INTERNAL_URL dibaca saat build (rewrites disimpan di manifest build); di Compose = http://api:8000.
module.exports = {
  rewrites() {
    return [{ source: '/api/:path*', destination: `${process.env.API_INTERNAL_URL || 'http://localhost:8000'}/api/:path*` }];
  },
};
