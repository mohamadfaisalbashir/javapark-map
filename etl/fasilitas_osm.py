"""FR-11: draf fasilitas tiap taman dari OpenStreetMap -> data/clean/fasilitas_taman.csv (dimuat etl/load.py).

Dijalankan sekali oleh tim (bukan bagian ETL), dari folder proyek, hanya Python stdlib, tanpa kunci API:
    python etl/fasilitas_osm.py              # satu request Overpass untuk semua taman
    python etl/fasilitas_osm.py --selftest   # uji fungsi murni, tanpa jaringan
Hasilnya DRAF: sel "ya" = OSM mencatat fasilitas itu dalam RADIUS_M dari titik taman, kosong = tidak diketahui.
Tim lalu memverifikasi (isi "ya"/"tidak" tiap sel, lalu diverifikasi = "ya"). Baris yang sudah diverifikasi
TIDAK ditimpa saat skrip dijalankan ulang.
"""
import csv
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
CSV = AKAR / "data/clean/fasilitas_taman.csv"
# ponytail: taman berupa titik, bukan poligon; 150 m bisa menangkap fasilitas di luar taman (masjid/parkir sekitar).
# Diatasi lewat verifikasi tim; ganti dengan poligon taman bila datanya ada.
RADIUS_M = 150

# Urutan = kolom CSV. Harus sama dengan FASILITAS di etl/load.py dan web/lib/format.js.
FASILITAS = ["toilet", "mushola", "bermain", "jogging", "olahraga"]

# (fasilitas, kunci OSM, nilai yang cocok)
ATURAN = [
    ("toilet", "amenity", {"toilets"}),
    ("mushola", "amenity", {"place_of_worship"}),  # + religion=muslim, dicek di jenis()
    ("bermain", "leisure", {"playground"}),
    ("jogging", "leisure", {"track"}),
    ("olahraga", "leisure", {"pitch", "sports_centre"}),
]


def jenis(tags):
    """Tag satu objek OSM -> himpunan fasilitas."""
    hasil = {f for f, k, nilai in ATURAN if tags.get(k) in nilai}
    if "mushola" in hasil and tags.get("religion") != "muslim":
        hasil.discard("mushola")
    return hasil


def query(titik):
    """Satu query Overpass; hasil tiap taman dipisah elemen penanda `batas`."""
    kunci = {}
    for _, k, nilai in ATURAN:
        kunci.setdefault(k, set()).update(nilai)
    blok = []
    for lat, lon in titik:
        sekitar = f"(around:{RADIUS_M},{lat},{lon})"
        isi = "".join(f'nwr{sekitar}["{k}"~"^({"|".join(sorted(v))})$"];' for k, v in kunci.items())
        blok.append(f"({isi});out tags;make batas;out;")
    return "[out:json][timeout:170];" + "".join(blok)


def pisah(elemen):
    """Elemen respons -> [himpunan fasilitas per taman] sesuai urutan titik."""
    per, kini = [], set()
    for e in elemen:
        if e["type"] == "batas":
            per.append(kini)
            kini = set()
        else:
            kini |= jenis(e.get("tags", {}))
    return per


def gabung(lama, baru):
    """Baris lama yang diverifikasi dipertahankan; selebihnya diganti draf baru. Kunci = (kota_kabupaten, nama_taman)."""
    tetap = {(r["kota_kabupaten"], r["nama_taman"]): r for r in lama if r.get("diverifikasi") == "ya"}
    return [tetap.get((r["kota_kabupaten"], r["nama_taman"]), r) for r in baru]


def main():
    with open(AKAR / "data/clean/taman_kota.geojson", encoding="utf-8") as f:
        taman = [x for x in json.load(f)["features"] if x["properties"].get("status") == "Aktif"]  # = load.py
    titik = [(x["geometry"]["coordinates"][1], x["geometry"]["coordinates"][0]) for x in taman]
    req = urllib.request.Request("https://overpass-api.de/api/interpreter",
                                 data=urllib.parse.urlencode({"data": query(titik)}).encode(),
                                 headers={"User-Agent": "TPBW-taman-kota/0.1"})
    with urllib.request.urlopen(req, timeout=200) as r:
        per = pisah(json.load(r)["elements"])
    if len(per) != len(taman):
        sys.exit(f"GAGAL: Overpass mengembalikan {len(per)} kelompok, seharusnya {len(taman)} (coba lagi nanti)")

    baru = []
    for x, fas in zip(taman, per):
        p = x["properties"]
        baru.append({"kota_kabupaten": p["kota_kabupaten"], "nama_taman": p["nama_taman"].strip(),
                     **{k: "ya" if k in fas else "" for k in FASILITAS}, "diverifikasi": ""})
    lama = []
    if CSV.exists():
        with open(CSV, encoding="utf-8", newline="") as f:
            lama = list(csv.DictReader(f))
    hasil = gabung(lama, baru)
    with open(CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kota_kabupaten", "nama_taman", *FASILITAS, "diverifikasi", "bukti", "sumber"])
        w.writeheader()
        w.writerows(hasil)
    n_ver = sum(r["diverifikasi"] == "ya" for r in hasil)
    kosong = sum(not any(r[k] == "ya" for k in FASILITAS) for r in hasil)
    print(f"Selesai: {len(hasil)} taman ({n_ver} sudah diverifikasi, dipertahankan), {kosong} tanpa fasilitas di OSM")
    print("Per fasilitas: " + ", ".join(f"{k}={sum(r[k] == 'ya' for r in hasil)}" for k in FASILITAS))
    print(f"-> {CSV.relative_to(AKAR)}. Verifikasi manual, lalu: docker compose run --rm --build etl")


def selftest():
    assert jenis({"amenity": "toilets"}) == {"toilet"}
    assert jenis({"amenity": "place_of_worship", "religion": "muslim"}) == {"mushola"}
    assert jenis({"amenity": "place_of_worship", "religion": "christian"}) == set()
    assert jenis({"leisure": "pitch", "sport": "soccer"}) == {"olahraga"}
    assert jenis({"amenity": "parking"}) == set()  # di luar 5 fasilitas
    assert {f for f, _, _ in ATURAN} == set(FASILITAS)

    q = query([(-7.29, 112.74), (-6.2, 106.8)])
    assert q.count("make batas") == 2 and "around:150,-7.29,112.74" in q

    el = [{"type": "node", "tags": {"leisure": "playground"}}, {"type": "batas"},
          {"type": "batas"},
          {"type": "way", "tags": {"amenity": "parking"}}, {"type": "node", "tags": {"amenity": "toilets"}}, {"type": "batas"}]
    assert pisah(el) == [{"bermain"}, set(), {"toilet"}]

    def r(nama, ver="", toilet=""):
        return {"kota_kabupaten": "Kota Bandung", "nama_taman": nama, "toilet": toilet, "diverifikasi": ver}

    hasil = gabung([r("A", "ya", "tidak"), r("B", "", "ya")], [r("A", "", "ya"), r("B"), r("C")])
    assert hasil == [r("A", "ya", "tidak"), r("B"), r("C")]
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
