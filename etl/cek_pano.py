"""FR-06: titik tur virtual 360° DI DALAM tiap taman -> data/clean/pano_taman.csv (dimuat etl/load.py).

Dijalankan sekali oleh tim (bukan bagian ETL), dari folder proyek, hanya Python stdlib:
    python etl/cek_pano.py              # perlu GOOGLE_MAPS_SERVER_KEY + MAPILLARY_TOKEN di .env (keduanya gratis)
    python etl/cek_pano.py --selftest   # uji fungsi murni, tanpa jaringan
Per taman:
 1. Batas taman = poligon OSM (leisure=park/garden/..., landuse=grass/village_green) yang memuat titik taman,
    atau yang terdekat ≤ 60 m; tidak ada = lingkaran RADIUS_CADANGAN_M. Marker di luar poligonnya digeser ke
    dalam (≤ GESER_MAKS_M) dan ditulis balik ke taman_kota.geojson.
 2. Panorama yang LOKASINYA di dalam batas, menurut prioritas (PERINGKAT): virtual tour Street View Google,
    lalu virtual tour Mapillary (360°), lalu photosphere pengguna. Maks. MAKS_TITIK, berjarak ≥ JARAK_MIN_M.
 3. Tak ada satu pun di dalam: panorama terdekat di luar, dengan heading menghadap taman (= "hanya jalan").
Kolom `titik` = "lat,lon;m:<id>;..." (di dalam; m: = gambar Mapillary) atau "lat,lon,heading" (dari tepi).
Kolom `jenis` = virtual_tour | photosphere | jalan | kosong. Untuk Google disimpan koordinat panorama, bukan pano_id
(dokumentasi Google: "don't persist this ID"); Maps Embed membuka panorama terdekat dari koordinat itu.
"""
import collections
import csv
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
MAKS_TITIK = 3
JARAK_MIN_M = 25  # dua panorama lebih dekat dari ini dianggap tempat yang sama
GRID_M = 35  # jarak antartitik grid pencarian
GRID_RAPAT_M = 12  # pencarian ulang bila tak ada panorama di dalam (lihat titik_taman)
MAKS_GRID = 49  # batas permintaan per taman (taman sangat luas: grid dijarangkan)
RADIUS_CADANGAN_M = 60  # taman tanpa poligon OSM
# Panorama Google (mobil Street View) di tepi poligon hampir selalu di jalan pinggir taman; trekker di dalam taman
# berada jauh dari tepi. ponytail: heuristik jarak-ke-tepi, bukan cek jaringan jalan OSM; kalibrasi bila meleset.
TEPI_GOOGLE_M = 15
CARI_LUAR_M = (50, 150, 400, 1000)  # radius panorama cadangan "dari tepi"
GESER_MAKS_M = 300  # marker lebih jauh dari ini ke poligonnya tidak digeser otomatis (dicetak untuk dicek tim)
GOOGLE, MAPILLARY, PHOTOSPHERE = 0, 1, 2  # peringkat: kecil = didahulukan; 0 & 1 = virtual tour
JENIS_TAMAN = ('["leisure"~"^(park|garden|common|recreation_ground|nature_reserve)$"]',
               '["landuse"~"^(grass|village_green|recreation_ground|forest)$"]')


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


def arah(lat1, lon1, lat2, lon2):
    """Bearing awal dari titik 1 ke titik 2, derajat [0, 360) (= arah() di web/lib/xr.js)."""
    f1, f2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(f2)
    x = math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def di_dalam(lat, lon, cincin):
    """Ray casting; cincin = [(lat, lon), ...]. Batas = daftar cincin luar (lubang diabaikan)."""
    hasil = False
    for i in range(len(cincin)):
        (a_lat, a_lon), (b_lat, b_lon) = cincin[i - 1], cincin[i]
        if (a_lat > lat) != (b_lat > lat) and lon < (b_lon - a_lon) * (lat - a_lat) / (b_lat - a_lat) + a_lon:
            hasil = not hasil
    return hasil


def jarak_ke_tepi(lat, lon, cincin):
    """Jarak (m) titik ke sisi terdekat cincin; proyeksi ekuirektangular lokal (cukup untuk skala taman)."""
    ky, kx = 111_320, 111_320 * math.cos(math.radians(lat))
    xy = [((b - lon) * kx, (a - lat) * ky) for a, b in cincin]
    terbaik = math.inf
    for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]):
        dx, dy = x2 - x1, y2 - y1
        t = max(0, min(1, -(x1 * dx + y1 * dy) / (dx * dx + dy * dy))) if dx or dy else 0
        terbaik = min(terbaik, math.hypot(x1 + t * dx, y1 + t * dy))
    return terbaik


def lingkaran(lat, lon, r_m, n=24):
    d_lat = r_m / 111_320
    d_lon = d_lat / math.cos(math.radians(lat))
    return [(lat + d_lat * math.cos(2 * math.pi * i / n), lon + d_lon * math.sin(2 * math.pi * i / n)) for i in range(n)]


def grid(cincin_cincin, langkah_min=GRID_M, maks=MAKS_GRID):
    """Titik grid (≤ maks, jarak ≥ langkah_min) di dalam batas taman."""
    semua = [p for c in cincin_cincin for p in c]
    s, n = min(p[0] for p in semua), max(p[0] for p in semua)
    w, e = min(p[1] for p in semua), max(p[1] for p in semua)
    tinggi, lebar = jarak_m(s, w, n, w), jarak_m(s, w, s, e)
    langkah = max(langkah_min, math.sqrt(tinggi * lebar / maks))
    ny, nx = int(tinggi // langkah) + 1, int(lebar // langkah) + 1
    titik = [(s + (n - s) * (j + .5) / ny, w + (e - w) * (i + .5) / nx) for j in range(ny) for i in range(nx)]
    return [p for p in titik if any(di_dalam(*p, c) for c in cincin_cincin)][:maks]


def pilih(pano, lat, lon):
    """pano = [(lat, lon, peringkat, kode)] di dalam taman -> ≤ MAKS_TITIK titik berbeda, peringkat dulu, dekat dulu."""
    urut = sorted(pano, key=lambda p: (p[2], jarak_m(lat, lon, p[0], p[1])))
    hasil = []
    for p in urut:
        if all(jarak_m(p[0], p[1], q[0], q[1]) >= JARAK_MIN_M for q in hasil):
            hasil.append(p)
    return hasil[:MAKS_TITIK]


def get_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "TPBW-taman-kota/0.2", **(headers or {})})
    for coba in range(4):
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:  # URL tidak dicetak: berisi kunci
            if e.code in (429, 502, 503, 504) and coba < 3:
                time.sleep(10 * (coba + 1))
                continue
            sys.exit(f"GAGAL: {urllib.parse.urlsplit(url).netloc} HTTP {e.code}: {e.read()[:300].decode(errors='replace')}")


def query_batas(titik):
    """Satu query Overpass untuk semua taman: poligon taman/hijau yang memuat titik + taman ≤ 60 m.

    Hasil tiap taman dipisah elemen penanda `batas` (pola = etl/fasilitas_osm.py). Satu query per taman
    terlalu lambat (Overpass publik ±2 menit per permintaan).
    """
    taman, hijau = JENIS_TAMAN
    blok = [f'is_in({lat},{lon})->.a;(way(pivot.a){taman};rel(pivot.a){taman};way(pivot.a){hijau};'
            f'rel(pivot.a){hijau};way(around:60,{lat},{lon}){taman};rel(around:60,{lat},{lon}){taman};);'
            'out geom;make batas;out;' for lat, lon in titik]
    return "[out:json][timeout:900];" + "".join(blok)


def pisah_batas(elemen):
    """Elemen respons -> [[(nama OSM, cincin luar), ...] per taman] sesuai urutan titik."""
    per, kini = [], []
    for el in elemen:
        nama = el.get("tags", {}).get("name", "")
        if el["type"] == "batas":
            per.append(kini)
            kini = []
        elif el["type"] == "way" and el.get("geometry"):
            kini.append((nama, [(g["lat"], g["lon"]) for g in el["geometry"]]))
        elif el["type"] == "relation":
            kini += [(nama, [(g["lat"], g["lon"]) for g in m["geometry"]])
                     for m in el.get("members", []) if m.get("role") == "outer" and m.get("geometry")]
    return per


def pilih_batas(lat, lon, calon):
    """calon = [(nama, cincin)] -> ([cincin], nama): poligon yang memuat titik (terkecil = taman itu sendiri, bukan
    kawasan hijau besar di sekitarnya), atau yang terdekat; ([], "") bila tidak ada."""
    calon = [x for x in calon if len(x[1]) > 2]
    memuat = [x for x in calon if di_dalam(lat, lon, x[1])]
    if memuat:
        x = min(memuat, key=lambda x: luas(x[1]))
    elif calon:
        x = min(calon, key=lambda x: min(jarak_m(lat, lon, *p) for p in x[1]))
    else:
        return [], ""
    return [x[1]], x[0]


UMUM = {"taman", "alun", "kota", "hutan", "rth", "park", "kabupaten", "dan", "di"}


def nama_mirip(a, b):
    """Nama taman & nama poligon OSM berbagi kata khas (bukan "taman", "alun", ...)?"""
    def kata(t):
        return set(re.findall(r"[a-z0-9]+", t.lower())) - UMUM
    return bool(kata(a) & kata(b))


def luas(c):
    """Luas relatif (derajat²) untuk membandingkan poligon."""
    return abs(sum(c[i - 1][1] * c[i][0] - c[i][1] * c[i - 1][0] for i in range(len(c)))) / 2


def metadata(lat, lon, radius, kunci):
    q = urllib.parse.urlencode({"location": f"{lat},{lon}", "radius": radius, "source": "outdoor", "key": kunci})
    for coba in range(4):  # UNKNOWN_ERROR = gangguan sementara di server Google
        s = get_json(f"https://maps.googleapis.com/maps/api/streetview/metadata?{q}")
        if s["status"] != "UNKNOWN_ERROR":
            break
        time.sleep(2 * (coba + 1))
    if s["status"] not in ("OK", "ZERO_RESULTS", "NOT_FOUND"):
        sys.exit(f"GAGAL: Street View metadata {s['status']} {s.get('error_message', '')}")
    if s["status"] != "OK":
        return None
    return s["location"]["lat"], s["location"]["lng"], milik_pengguna(s.get("copyright", ""))


def milik_pengguna(copyright):
    """Photosphere unggahan pengguna ("© Ariyanto") vs panorama Google ("© 2026 Google", tahun ikut berubah)."""
    return "Google" not in copyright


def mapillary(batas, token):
    """Gambar 360° Mapillary di dalam batas -> [(lat, lon, MAPILLARY, "m:<id>")] (ID Mapillary boleh disimpan)."""
    semua = [p for c in batas for p in c]
    q = urllib.parse.urlencode({"bbox": f"{min(p[1] for p in semua)},{min(p[0] for p in semua)},"
                                        f"{max(p[1] for p in semua)},{max(p[0] for p in semua)}",
                                "is_pano": "true", "fields": "id,geometry", "limit": 1000})
    js = get_json(f"https://graph.mapillary.com/images?{q}", headers={"Authorization": f"OAuth {token}"})
    return [(g[1], g[0], MAPILLARY, f"m:{x['id']}") for x in js.get("data", [])
            for g in [x["geometry"]["coordinates"]] if any(di_dalam(g[1], g[0], c) for c in batas)]


def geser_marker(lat, lon, batas):
    """Marker di luar poligon tamannya -> titik di dalam (pusat poligon, atau titik grid terdekat bila pusat di luar);
    None bila sudah di dalam / tanpa poligon. Pemanggil wajib cek nama_mirip() dulu (poligon terdekat bisa taman lain)."""
    if not batas or any(di_dalam(lat, lon, c) for c in batas):
        return None
    c = batas[0]
    pusat = (sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c))
    if di_dalam(*pusat, c):
        return pusat
    g = grid(batas)
    return min(g, key=lambda p: jarak_m(lat, lon, *p)) if g else None


def titik_taman(lat, lon, batas, kunci, token):
    """batas = hasil pilih_batas -> (teks kolom titik, jenis: virtual_tour | photosphere | jalan | '', ada_poligon)."""
    ada_poligon = bool(batas)
    batas = batas or [lingkaran(lat, lon, RADIUS_CADANGAN_M)]

    def jauh_dari_tepi(p):  # kamera mobil (Google/Mapillary) di tepi poligon = di jalan pinggir taman
        memuat = [c for c in batas if di_dalam(p[0], p[1], c)]
        return ada_poligon and memuat and max(jarak_ke_tepi(p[0], p[1], c) for c in memuat) >= TEPI_GOOGLE_M

    def google(langkah, maks):
        calon = {}
        with ThreadPoolExecutor(8) as ex:  # metadata gratis & tanpa kuota ketat; urut-satu-satu terlalu lambat
            hasil = ex.map(lambda g: metadata(g[0], g[1], langkah, kunci), [(lat, lon)] + grid(batas, langkah, maks))
        for p in hasil:
            if p and p[2] and any(di_dalam(p[0], p[1], c) for c in batas):  # photosphere pengguna: cukup di dalam
                calon[(round(p[0], 6), round(p[1], 6))] = (p[0], p[1], PHOTOSPHERE, None)
            elif p and not p[2] and jauh_dari_tepi(p):
                calon[(round(p[0], 6), round(p[1], 6))] = (p[0], p[1], GOOGLE, None)
        return list(calon.values())

    mly = [m for m in mapillary(batas, token) if jauh_dari_tepi(m)]
    pilihan = pilih(google(GRID_M, MAKS_GRID) + mly, lat, lon)
    if not pilihan:
        # Metadata hanya memberi panorama TERDEKAT: panorama mobil di jalan bisa menutupi photosphere di dalam taman.
        pilihan = pilih(google(GRID_RAPAT_M, MAKS_GRID * 3) + mly, lat, lon)
    if pilihan:
        return (";".join(p[3] or f"{p[0]:.6f},{p[1]:.6f}" for p in pilihan),
                "virtual_tour" if pilihan[0][2] < PHOTOSPHERE else "photosphere", ada_poligon)
    for r in CARI_LUAR_M:
        p = metadata(lat, lon, r, kunci)
        if p:
            return f"{p[0]:.6f},{p[1]:.6f},{round(arah(p[0], p[1], lat, lon))}", "jalan", ada_poligon
    return "", "", ada_poligon


def main():
    env = baca_env()
    kunci, token = env.get("GOOGLE_MAPS_SERVER_KEY", ""), env.get("MAPILLARY_TOKEN", "")
    if not kunci or not token:
        sys.exit("GAGAL: isi GOOGLE_MAPS_SERVER_KEY dan MAPILLARY_TOKEN di .env (lihat .env.example)")
    path_taman = AKAR / "data/clean/taman_kota.geojson"
    teks_taman = path_taman.read_text(encoding="utf-8")
    taman = [x for x in json.loads(teks_taman)["features"] if x["properties"].get("status") == "Aktif"]  # = load.py
    titik = [(x["geometry"]["coordinates"][1], x["geometry"]["coordinates"][0]) for x in taman]
    print("Mengambil poligon taman dari Overpass (satu query, bisa beberapa menit)…", flush=True)
    per = pisah_batas(get_json("https://overpass-api.de/api/interpreter",
                               urllib.parse.urlencode({"data": query_batas(titik)}).encode())["elements"])
    if len(per) != len(taman):
        sys.exit(f"GAGAL: Overpass mengembalikan {len(per)} kelompok, seharusnya {len(taman)} (coba lagi nanti)")
    hasil, digeser, dicek = [], [], []
    for i, (x, (lat, lon), cincin) in enumerate(zip(taman, titik, per), 1):
        p = x["properties"]
        batas, nama_osm = pilih_batas(lat, lon, cincin)
        baru, geser = geser_marker(lat, lon, batas), ""
        if baru and not nama_mirip(p["nama_taman"], nama_osm):
            dicek.append(f"{p['nama_taman']} (di luar poligon terdekat {nama_osm or 'tanpa nama'!r}, tidak digeser)")
            baru = None
        if baru and jarak_m(lat, lon, *baru) > GESER_MAKS_M:
            dicek.append(f"{p['nama_taman']} ({jarak_m(lat, lon, *baru):.0f} m)")
        elif baru:
            # Tulis balik apa adanya (format file dipertahankan); string koordinat lama harus unik.
            lama = f"[{x['geometry']['coordinates'][0]}, {x['geometry']['coordinates'][1]}]"
            if teks_taman.count(lama) == 1:
                teks_taman = teks_taman.replace(lama, f"[{baru[1]:.6f}, {baru[0]:.6f}]")
                geser = f" (marker digeser {jarak_m(lat, lon, *baru):.0f} m)"
                digeser.append(p["nama_taman"] + geser)
                lat, lon = baru
            else:
                dicek.append(f"{p['nama_taman']} (koordinat {lama} tidak unik di geojson)")
        teks, jenis, ada_poligon = titik_taman(lat, lon, batas, kunci, token)
        hasil.append({"kota_kabupaten": p["kota_kabupaten"], "nama_taman": p["nama_taman"].strip(),
                      "titik": teks, "jenis": jenis})
        n = teks.count(";") + 1 if teks else 0
        print(f"[{i}/{len(taman)}] {p['nama_taman']}: {jenis or '-'} {n} titik"
              f"{'' if ada_poligon else ' (tanpa poligon OSM)'}{geser}", flush=True)

    path_taman.write_text(teks_taman, encoding="utf-8", newline="\n")
    with open(AKAR / "data/clean/pano_taman.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kota_kabupaten", "nama_taman", "titik", "jenis"])
        w.writeheader()
        w.writerows(hasil)
    n = collections.Counter(h["jenis"] or "tanpa" for h in hasil)
    print(f"Selesai: {dict(n)} -> data/clean/pano_taman.csv")
    print(f"Marker digeser ke dalam poligon ({len(digeser)}): " + ", ".join(digeser))
    if dicek:
        print(f"PERLU DICEK MANUAL ({len(dicek)}): " + ", ".join(dicek))
    print("Lanjut: docker compose run --rm etl")


def selftest():
    assert abs(jarak_m(-6.9, 107.6, -6.9, 107.6)) < 1e-6
    assert 110_000 < jarak_m(-7, 110, -6, 110) < 111_500  # 1° lintang ≈ 111 km
    assert round(arah(-7, 110, -6.9, 110)) == 0 and round(arah(-7, 110, -7, 110.1)) == 90
    kotak = [(0, 0), (0, 1), (1, 1), (1, 0)]
    assert di_dalam(.5, .5, kotak) and not di_dalam(1.5, .5, kotak) and not di_dalam(.5, -.1, kotak)
    c = lingkaran(-7, 110, 60)
    assert di_dalam(-7, 110, c) and not di_dalam(-7.001, 110, c)  # 111 m di selatan
    g = grid([c])
    assert g and all(di_dalam(*p, c) for p in g)
    besar = lingkaran(-7, 110, 2000)
    assert len(grid([besar])) <= MAKS_GRID
    assert luas(kotak) == 1
    assert milik_pengguna("© Ariyanto") and not milik_pengguna("© 2026 Google") and not milik_pengguna("© Google")
    assert abs(jarak_ke_tepi(-7, 110, lingkaran(-7, 110, 60, 360)) - 60) < 0.5
    assert jarak_ke_tepi(-7, 110.00054, lingkaran(-7, 110, 60, 360)) < 1  # ±60 m ke timur = di tepi
    besar_kotak = [(-1, -1), (-1, 2), (2, 2), (2, -1)]
    assert pilih_batas(.5, .5, [("B", besar_kotak), ("K", kotak), ("", [(0, 0), (0, 1)])]) == ([kotak], "K")  # terkecil
    jauh = [(5, 5), (5, 6), (6, 6)]
    assert pilih_batas(3, 3, [("J", jauh), ("B", besar_kotak)]) == ([besar_kotak], "B")
    assert pilih_batas(0, 0, []) == ([], "")
    el = [{"type": "way", "tags": {"name": "Taman X"}, "geometry": [{"lat": 0, "lon": 0}] * 3}, {"type": "batas"},
          {"type": "batas"}]
    assert pisah_batas(el) == [[("Taman X", [(0, 0)] * 3)], []]
    assert nama_mirip("Taman Film", "Taman Film") and nama_mirip("Alun-Alun Sidoarjo (Monumen Jayandaru)", "Alun-Alun Sidoarjo")
    assert not nama_mirip("Taman Millenial Rajawali", "Taman Adipura Bantul") and not nama_mirip("Taman A", "")
    assert len(grid([c], GRID_RAPAT_M, 500)) > len(grid([c]))
    q = query_batas([(-7.29, 112.74), (-6.2, 106.8)])
    assert q.count("make batas") == 2 and "is_in(-7.29,112.74)" in q
    # Google > Mapillary > photosphere (walau lebih dekat); yang < JARAK_MIN_M dari pilihan sebelumnya dibuang.
    u1 = (-6.9997, 110, PHOTOSPHERE, None)
    m1, m1_kembar = (-7.0003, 110, MAPILLARY, "m:1"), (-7.0003, 110.0001, MAPILLARY, "m:2")
    g1 = (-7, 110.0009, GOOGLE, None)
    assert pilih([u1, m1_kembar, m1, g1], -7, 110) == [g1, m1, u1]
    assert len(pilih([(-7 + i * .001, 110, GOOGLE, None) for i in range(5)], -7, 110)) == MAKS_TITIK
    assert pilih([], -7, 110) == []
    # Marker di luar poligon -> pusatnya; di dalam / tanpa poligon -> None. Poligon L: pusat di luar -> titik grid.
    k = lingkaran(-7, 110, 60, 36)
    assert geser_marker(-7, 110, [k]) is None and geser_marker(-7.001, 110, []) is None
    assert jarak_m(*geser_marker(-7.001, 110, [k]), -7, 110) < 1
    el_l = [(0, 0), (0, .003), (.001, .003), (.001, .001), (.003, .001), (.003, 0)]
    baru = geser_marker(-.001, 0, [el_l])
    assert baru and di_dalam(*baru, el_l)
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
