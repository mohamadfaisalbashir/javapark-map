"""FR-11: periksa ulang fasilitas tiap taman -> data/clean/fasilitas_taman.csv (dimuat etl/load.py).

Dijalankan sekali oleh tim (bukan bagian ETL), dari folder proyek, hanya Python stdlib, tanpa biaya:
    python etl/fasilitas_osm.py              # Overpass (+ Google Places bila kuncinya diizinkan)
    python etl/fasilitas_osm.py --selftest   # uji fungsi murni, tanpa jaringan
Sumber per fasilitas (dicatat di kolom bukti sebagai "<fasilitas>:<sumber>"):
 - osm:    objek OpenStreetMap ≤ RADIUS_M dari titik taman ATAU di dalam poligon taman (batas = etl/cek_pano.py).
           Radius dipakai (permintaan user 24 Nov 2026) karena masjid besar di sisi alun-alun terlihat di tur 360°;
           poligon dipakai agar fasilitas di taman luas (mis. Monas) tetap terhitung.
 - google: Google Places API (New) Nearby Search, tempat bertipe playground/public_bathroom/mosque/... dengan
           aturan lingkup yang sama. 1 permintaan per taman (≈100 ≪ kuota gratis bulanan) -> Rp0. Kunci ditolak = dilewati.
 - web:    bukti riset web yang sudah ada di CSV (kolom sumber berisi URL-nya), dipertahankan.
Sel = "ya" bila ada di salah satu sumber, selain itu kosong (= tidak diketahui). Baris diverifikasi = "ya" TIDAK diubah.
"""
import csv
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from cek_pano import (RADIUS_CADANGAN_M, baca_env, di_dalam, get_json, jarak_m, lingkaran, pilih_batas,
                      pisah_batas, query_batas)

AKAR = Path(__file__).resolve().parent.parent
CSV = AKAR / "data/clean/fasilitas_taman.csv"

# Urutan = kolom CSV. Harus sama dengan FASILITAS di etl/load.py dan web/lib/format.js.
FASILITAS = ["toilet", "mushola", "bermain", "jogging", "olahraga"]
KOLOM = ["kota_kabupaten", "nama_taman", *FASILITAS, "diverifikasi", "bukti", "sumber"]
RADIUS_M = 150  # ponytail: radius dari titik taman bisa menangkap fasilitas di luar taman (mis. masjid di seberang alun-alun)

# (fasilitas, kunci OSM, nilai yang cocok)
ATURAN = [
    ("toilet", "amenity", {"toilets"}),
    ("mushola", "amenity", {"place_of_worship"}),  # + muslim, dicek di jenis()
    ("bermain", "leisure", {"playground"}),
    ("jogging", "leisure", {"track"}),
    ("olahraga", "leisure", {"pitch", "sports_centre", "fitness_station"}),
]
# Tipe Google Places (Table A) -> fasilitas.
TIPE_PLACES = {"playground": "bermain", "public_bathroom": "toilet", "mosque": "mushola",
               "sports_complex": "olahraga", "athletic_field": "olahraga"}


def jenis(tags):
    """Tag satu objek OSM -> himpunan fasilitas."""
    hasil = {f for f, k, nilai in ATURAN if tags.get(k) in nilai}
    nama = tags.get("name", "").lower()
    if "mushola" in hasil and tags.get("religion") != "muslim" and not any(
            x in nama for x in ("mushola", "musholla", "musala", "masjid")):
        hasil.discard("mushola")
    if "jogging" in nama and tags.get("highway") in ("footway", "path", "track", "pedestrian"):
        hasil.add("jogging")
    return hasil


def query(lingkup):
    """lingkup = [(lat, lon, radius_m)]: satu query Overpass; hasil tiap taman dipisah elemen penanda `batas`."""
    kunci = {}
    for _, k, nilai in ATURAN:
        kunci.setdefault(k, set()).update(nilai)
    blok = []
    for lat, lon, r in lingkup:
        sekitar = f"(around:{r:.0f},{lat},{lon})"
        isi = "".join(f'nwr{sekitar}["{k}"~"^({"|".join(sorted(v))})$"];' for k, v in kunci.items())
        isi += f'way{sekitar}["highway"]["name"~"jogging",i];'
        blok.append(f"({isi});out center tags;make batas;out;")
    return "[out:json][timeout:600];" + "".join(blok)


def pisah(elemen):
    """Elemen respons -> [[(lat, lon, tags)] per taman] sesuai urutan titik."""
    per, kini = [], []
    for e in elemen:
        if e["type"] == "batas":
            per.append(kini)
            kini = []
        else:
            c = e.get("center") or e
            kini.append((c["lat"], c["lon"], e.get("tags", {})))
    return per


def radius_batas(lat, lon, batas):
    """Radius (m) dari titik taman yang mencakup seluruh batas, + 10 m."""
    return max(jarak_m(lat, lon, *p) for c in batas for p in c) + 10


def masuk(lat, lon, batas, pusat):
    """Objek di (lat, lon) termasuk fasilitas taman: ≤ RADIUS_M dari titik taman `pusat` atau di dalam batas."""
    return jarak_m(lat, lon, *pusat) <= RADIUS_M or any(di_dalam(lat, lon, c) for c in batas)


def places(lat, lon, r, kunci):
    """Google Places Nearby Search -> [(lat, lon, fasilitas)]; None bila kunci tidak diizinkan memakai Places API."""
    body = {"includedTypes": sorted(TIPE_PLACES), "maxResultCount": 20,
            "locationRestriction": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": min(r, 50000)}}}
    req = urllib.request.Request("https://places.googleapis.com/v1/places:searchNearby", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Goog-Api-Key": kunci,
                                          "X-Goog-FieldMask": "places.location,places.types"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            js = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return None
        raise
    return [(p["location"]["latitude"], p["location"]["longitude"], TIPE_PLACES[t])
            for p in js.get("places", []) for t in p.get("types", []) if t in TIPE_PLACES]


def bukti_lama(teks):
    """Kolom bukti -> {(fasilitas, sumber)}. Token tanpa ":" = hasil riset web (format lama)."""
    hasil = set()
    for t in (x.strip() for x in teks.split(",")):
        if t:
            f, _, s = t.partition(":")
            hasil.add((f, s or "web"))
    return hasil


def gabung(lama, temuan):
    """lama = baris CSV; temuan = {(fasilitas, sumber)} dari osm/google -> baris baru (diverifikasi: apa adanya)."""
    if lama.get("diverifikasi") == "ya":
        return lama
    bukti = {(f, s) for f, s in bukti_lama(lama.get("bukti", "")) if s == "web" and f in FASILITAS} | temuan
    ada = {f for f, _ in bukti}
    return {**lama, **{k: "ya" if k in ada else "" for k in FASILITAS},
            "bukti": ",".join(f"{f}:{s}" for f, s in sorted(bukti, key=lambda x: (FASILITAS.index(x[0]), x[1])))}


def main():
    with open(AKAR / "data/clean/taman_kota.geojson", encoding="utf-8") as f:
        taman = [x for x in json.load(f)["features"] if x["properties"].get("status") == "Aktif"]  # = load.py
    titik = [(x["geometry"]["coordinates"][1], x["geometry"]["coordinates"][0]) for x in taman]
    print("Mengambil poligon taman dari Overpass…", flush=True)
    per, _ = pisah_batas(get_json("https://overpass-api.de/api/interpreter",
                                  urllib.parse.urlencode({"data": query_batas(titik)}).encode())["elements"])
    if len(per) != len(taman):
        sys.exit(f"GAGAL: Overpass mengembalikan {len(per)} kelompok, seharusnya {len(taman)} (coba lagi nanti)")
    batas = [pilih_batas(lat, lon, c)[0] or [lingkaran(lat, lon, RADIUS_CADANGAN_M)] for (lat, lon), c in zip(titik, per)]
    lingkup = [(lat, lon, max(RADIUS_M, radius_batas(lat, lon, b))) for (lat, lon), b in zip(titik, batas)]
    print("Mengambil objek fasilitas dari Overpass…", flush=True)
    objek = pisah(get_json("https://overpass-api.de/api/interpreter",
                           urllib.parse.urlencode({"data": query(lingkup)}).encode())["elements"])
    if len(objek) != len(taman):
        sys.exit(f"GAGAL: Overpass mengembalikan {len(objek)} kelompok, seharusnya {len(taman)} (coba lagi nanti)")

    kunci = baca_env().get("GOOGLE_MAPS_SERVER_KEY", "")
    pakai_places = bool(kunci)
    lama = {}
    if CSV.exists():
        with open(CSV, encoding="utf-8", newline="") as f:
            lama = {(r["kota_kabupaten"], r["nama_taman"]): r for r in csv.DictReader(f)}
    hasil, berubah = [], []
    for x, b, (lat, lon, r), obj in zip(taman, batas, lingkup, objek):
        p = x["properties"]
        temuan = {(f, "osm") for la, lo, tags in obj if masuk(la, lo, b, (lat, lon)) for f in jenis(tags)}
        if pakai_places:
            g = places(lat, lon, r, kunci)
            if g is None:
                print("Info: kunci Google ditolak Places API (aktifkan 'Places API (New)'); lanjut tanpa Google.")
                pakai_places = False
            else:
                temuan |= {(f, "google") for la, lo, f in g if masuk(la, lo, b, (lat, lon))}
        kosong = {"kota_kabupaten": p["kota_kabupaten"], "nama_taman": p["nama_taman"].strip(),
                  **{k: "" for k in FASILITAS}, "diverifikasi": "", "bukti": "", "sumber": ""}
        sebelum = lama.get((kosong["kota_kabupaten"], kosong["nama_taman"]), kosong)
        baru = gabung(sebelum, temuan)
        if any(sebelum.get(k, "") != baru[k] for k in FASILITAS):
            beda = [f"{'+' if baru[k] else '-'}{k}" for k in FASILITAS if sebelum.get(k, "") != baru[k]]
            berubah.append(f"{baru['nama_taman']} ({' '.join(beda)})")
        hasil.append({k: baru.get(k, "") for k in KOLOM})

    with open(CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLOM)
        w.writeheader()
        w.writerows(hasil)
    print(f"Selesai: {len(hasil)} taman, Google Places {'dipakai' if pakai_places else 'tidak dipakai'}")
    print("Per fasilitas: " + ", ".join(f"{k}={sum(r[k] == 'ya' for r in hasil)}" for k in FASILITAS))
    print(f"Berubah ({len(berubah)}): " + "; ".join(berubah))
    print(f"-> {CSV.relative_to(AKAR)}. Lanjut: docker compose run --rm --build etl")


def selftest():
    assert jenis({"amenity": "toilets"}) == {"toilet"}
    assert jenis({"amenity": "place_of_worship", "religion": "muslim"}) == {"mushola"}
    assert jenis({"amenity": "place_of_worship", "name": "Musholla Al-Ikhlas"}) == {"mushola"}
    assert jenis({"amenity": "place_of_worship", "religion": "christian"}) == set()
    assert jenis({"leisure": "pitch", "sport": "soccer"}) == {"olahraga"}
    assert jenis({"highway": "footway", "name": "Jogging Track Taman"}) == {"jogging"}
    assert jenis({"amenity": "parking"}) == set()  # di luar 5 fasilitas
    assert {f for f, _, _ in ATURAN} == set(FASILITAS) and set(TIPE_PLACES.values()) <= set(FASILITAS)

    q = query([(-7.29, 112.74, 120), (-6.2, 106.8, 60)])
    assert q.count("make batas") == 2 and "around:120,-7.29,112.74" in q

    el = [{"type": "node", "lat": 1, "lon": 2, "tags": {"leisure": "playground"}}, {"type": "batas"}, {"type": "batas"},
          {"type": "way", "center": {"lat": 3, "lon": 4}, "tags": {"amenity": "toilets"}}, {"type": "batas"}]
    assert pisah(el) == [[(1, 2, {"leisure": "playground"})], [], [(3, 4, {"amenity": "toilets"})]]

    c = lingkaran(-7, 110, 60)
    assert 69 < radius_batas(-7, 110, [c]) < 71
    besar = lingkaran(-7, 110, 400)
    assert masuk(-7.001, 110, [c], (-7, 110))  # ±111 m: di luar poligon, tapi ≤ 150 m
    assert not masuk(-7.002, 110, [c], (-7, 110))  # ±222 m, di luar poligon
    assert masuk(-7.003, 110, [besar], (-7, 110))  # ±333 m, di dalam poligon taman luas

    assert bukti_lama("toilet,bermain") == {("toilet", "web"), ("bermain", "web")}
    assert bukti_lama("toilet:osm, jogging:web") == {("toilet", "osm"), ("jogging", "web")}
    baris = {"kota_kabupaten": "K", "nama_taman": "A", "toilet": "ya", "mushola": "ya", "bermain": "", "jogging": "",
             "olahraga": "", "diverifikasi": "", "bukti": "toilet", "sumber": "https://x"}
    b = gabung(baris, {("bermain", "osm")})
    # mushola lama tanpa bukti dari sumber mana pun dikosongkan; toilet tetap karena bukti web; bermain baru dari OSM.
    assert (b["toilet"], b["mushola"], b["bermain"], b["bukti"], b["sumber"]) == ("ya", "", "ya", "toilet:web,bermain:osm", "https://x")
    assert gabung({**baris, "diverifikasi": "ya"}, {("bermain", "osm")})["bermain"] == ""  # terverifikasi: tak disentuh
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
