"""Bagian 6.5: cari panorama 360° di sekitar tiap taman -> data/clean/pano_taman.csv (dimuat etl/load.py).

Dijalankan sekali oleh tim (bukan bagian ETL), dari folder proyek, hanya Python stdlib:
    python etl/cek_pano.py              # perlu GOOGLE_MAPS_SERVER_KEY dan/atau MAPILLARY_TOKEN di .env
    python etl/cek_pano.py --selftest   # uji fungsi murni, tanpa jaringan
Urutan per taman: Google Street View (utama) -> Mapillary (cadangan) -> kosong (tanpa tombol 360°).
Dari Google hanya label "google" yang disimpan; pano_id tidak (dokumentasi Google: "don't persist this ID").
"""
import csv
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
RADIUS_M = 50  # = radius bawaan pencarian Street View Embed (viewer FR-06) dan batas pencarian Mapillary


def baca_env():
    """.env sederhana (KUNCI=nilai); variabel lingkungan menimpa .env."""
    env = {}
    if (AKAR / ".env").exists():
        for baris in (AKAR / ".env").read_text(encoding="utf-8").splitlines():
            k, ada, v = baris.partition("=")
            if ada and not k.strip().startswith("#"):
                env[k.strip()] = v.strip()
    return {**env, **os.environ}


def jarak_m(lat1, lon1, lat2, lon2):
    rad = math.pi / 180
    h = (math.sin((lat2 - lat1) * rad / 2) ** 2
         + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin((lon2 - lon1) * rad / 2) ** 2)
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def bbox(lat, lon):
    """Kotak ±RADIUS_M di sekitar titik (filter is_pano Mapillary wajib memakai bbox)."""
    d_lat = RADIUS_M / 111_320
    d_lon = d_lat / math.cos(math.radians(lat))
    return f"{lon - d_lon:.6f},{lat - d_lat:.6f},{lon + d_lon:.6f},{lat + d_lat:.6f}"


def pilih_mapillary(lat, lon, gambar):
    """Panorama terbaru dalam RADIUS_M (bbox lebih luas dari lingkaran), atau None."""
    dekat = []
    for g in gambar:
        glon, glat = (g.get("computed_geometry") or g["geometry"])["coordinates"]
        if jarak_m(lat, lon, glat, glon) <= RADIUS_M:
            dekat.append(g)
    return str(max(dekat, key=lambda g: g["captured_at"])["id"]) if dekat else None


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "TPBW-taman-kota/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:  # URL tidak dicetak: berisi kunci
        sys.exit(f"GAGAL: {urllib.parse.urlsplit(url).netloc} HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")


def ada_street_view(lat, lon, kunci):
    q = urllib.parse.urlencode({"location": f"{lat},{lon}", "radius": RADIUS_M, "key": kunci})
    s = get_json(f"https://maps.googleapis.com/maps/api/streetview/metadata?{q}")
    if s["status"] not in ("OK", "ZERO_RESULTS", "NOT_FOUND"):
        sys.exit(f"GAGAL: Street View metadata {s['status']} {s.get('error_message', '')} "
                 "(periksa GOOGLE_MAPS_SERVER_KEY dan Street View Static API di Google Cloud)")
    return s["status"] == "OK"


def cari_mapillary(lat, lon, token):
    q = urllib.parse.urlencode({"access_token": token, "bbox": bbox(lat, lon), "is_pano": "true",
                                "fields": "id,captured_at,geometry,computed_geometry", "limit": 2000})
    return pilih_mapillary(lat, lon, get_json(f"https://graph.mapillary.com/images?{q}")["data"])


def main():
    env = baca_env()
    kunci, token = env.get("GOOGLE_MAPS_SERVER_KEY", ""), env.get("MAPILLARY_TOKEN", "")
    if not kunci and not token:
        sys.exit("GAGAL: isi GOOGLE_MAPS_SERVER_KEY dan/atau MAPILLARY_TOKEN di .env (lihat .env.example)")
    for nama, nilai in (("GOOGLE_MAPS_SERVER_KEY", kunci), ("MAPILLARY_TOKEN", token)):
        if not nilai:
            print(f"PERINGATAN: {nama} kosong, sumber itu dilewati (hasil tidak lengkap).")

    with open(AKAR / "data/clean/taman_kota.geojson", encoding="utf-8") as f:
        taman = [x for x in json.load(f)["features"] if x["properties"].get("status") == "Aktif"]  # = load.py
    hasil = []
    for i, x in enumerate(taman, 1):
        lon, lat = x["geometry"]["coordinates"]
        src = mid = ""
        if kunci and ada_street_view(lat, lon, kunci):
            src = "google"
        elif token and (mid := cari_mapillary(lat, lon, token) or ""):
            src = "mapillary"
        p = x["properties"]
        hasil.append({"kota_kabupaten": p["kota_kabupaten"], "nama_taman": p["nama_taman"].strip(),
                      "vr_source": src, "mapillary_id": mid})
        print(f"[{i}/{len(taman)}] {p['nama_taman']}: {src or '-'}", flush=True)
        time.sleep(0.1)

    with open(AKAR / "data/clean/pano_taman.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kota_kabupaten", "nama_taman", "vr_source", "mapillary_id"])
        w.writeheader()
        w.writerows(hasil)
    n = {s: sum(h["vr_source"] == s for h in hasil) for s in ("google", "mapillary", "")}
    print(f"Selesai: google={n['google']}, mapillary={n['mapillary']}, tanpa={n['']} -> data/clean/pano_taman.csv")
    print("Lanjut: docker compose run --rm etl")


def selftest():
    assert abs(jarak_m(-6.9, 107.6, -6.9, 107.6)) < 1e-6
    assert 110_000 < jarak_m(-7, 110, -6, 110) < 111_500  # 1° lintang ≈ 111 km
    w, s, e, n = map(float, bbox(-7, 110).split(","))
    assert w < 110 < e and s < -7 < n
    assert abs(jarak_m(-7, 110, n, 110) - RADIUS_M) < 1

    def g(id_, lat, lon, t, computed=True):
        return {"id": id_, "captured_at": t,
                ("computed_geometry" if computed else "geometry"): {"type": "Point", "coordinates": [lon, lat]}}

    lat, lon = -7.0, 110.0
    sudut_bbox = g(1, lat + 0.0004, lon + 0.0004, 9e12)  # di dalam bbox, ±63 m: di luar lingkaran
    lama, baru = g(2, lat + 0.0001, lon, 1e12), g(3, lat, lon + 0.0001, 2e12, computed=False)
    assert pilih_mapillary(lat, lon, [sudut_bbox, lama, baru]) == "3"
    assert pilih_mapillary(lat, lon, [sudut_bbox]) is None
    assert pilih_mapillary(lat, lon, []) is None
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
