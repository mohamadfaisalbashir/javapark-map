"""ETL GeoJSON bersih -> PostGIS.

Membaca data/clean/{provinces,cities}.geojson (batas wilayah OSM, hasil QGIS) dan
data/clean/taman_kota.geojson (inventaris taman kota tim; salinan "Data Taman Kota Pulau Jawa
GeoJSON.md", isinya sama dengan "Data taman beserta lon dan lat.xlsx"), memvalidasi, lalu memuat
provinces, cities, parks. Kota/kab tiap taman ditentukan spasial (titik di dalam poligon kota).
Idempoten: dijalankan ulang pada masukan yang sama menghasilkan isi tabel yang sama (upsert
berdasarkan osm_id / city_id + nama taman, lalu hapus baris yang tidak ada pada run ini).

    docker compose run --rm etl                             # ETL penuh
    docker compose run --rm etl python load.py --selftest   # uji fungsi murni, tanpa DB
"""
import collections
import json
import os
import re
import sys

import psycopg

CLEAN = "/data/clean"
JUMLAH_PROVINSI = 6  # Bagian 4: Banten, DKI Jakarta, Jawa Barat, Jawa Tengah, DI Yogyakarta, Jawa Timur
POLIGON = "ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3))"
GEOM = "ST_SetSRID(ST_GeomFromGeoJSON(%s::text), 4326)"


def kategori(nama):
    """Data tim tidak berkategori; diturunkan dari nama (Bagian 6.4: "Alun-alun" -> alun_alun)."""
    n = nama.lower()
    if re.search(r"alun[- ]alun", n):
        return "alun_alun"
    if "hutan kota" in n or re.search(r"\brth\b", n):
        return "rth"
    return "taman_kota"


def siapkan_taman(f):
    """-> (baris, []) bila lolos; (None, [pelanggaran, ...]) bila melanggar skema."""
    p, g = f["properties"], f.get("geometry") or {}
    nama = (p.get("nama_taman") or "").strip()
    m = []
    if g.get("type") != "Point":
        m.append("geometri bukan Point")
    elif not (-180 <= g["coordinates"][0] <= 180 and -90 <= g["coordinates"][1] <= 90):
        m.append("koordinat di luar rentang")
    if not nama:
        m.append("nama kosong")
    if m:
        return None, m
    lon, lat = g["coordinates"]
    return (nama, kategori(nama), p.get("kota_kabupaten"), round(lat, 6), round(lon, 6), json.dumps(g)), []


def periksa_batas(provinsi, kota):
    m = []
    if len(provinsi) != JUMLAH_PROVINSI:
        m.append(f"provinces.geojson: {len(provinsi)} fitur, seharusnya {JUMLAH_PROVINSI}")
    nama_prov = {f["properties"]["prov_name"] for f in provinsi}
    for f in provinsi + kota:
        if (f.get("geometry") or {}).get("type") not in ("Polygon", "MultiPolygon"):
            m.append(f"geometri bukan poligon: {f['properties']}")
    for f in kota:
        if f["properties"]["prov_name"] not in nama_prov:
            m.append(f"kota {f['properties']['city_name']!r}: prov_name tidak ada di provinces.geojson")
    for tipe, fs, kunci in (("provinsi", provinsi, "prov_osm_id"), ("kota", kota, "city_osm_id")):
        n = collections.Counter(str(f["properties"][kunci]) for f in fs)
        m += [f"{tipe}: {kunci} ganda {i}" for i, c in n.items() if c > 1]
    return m


def baca(nama):
    with open(f"{CLEAN}/{nama}.geojson", encoding="utf-8") as f:
        return json.load(f)["features"]


def main():
    provinsi, kota = baca("provinces"), baca("cities")
    taman = [f for f in baca("taman_kota") if f["properties"].get("status") == "Aktif"]
    masalah = periksa_batas(provinsi, kota)
    baris, kunci = [], collections.Counter()
    for f in taman:
        row, m = siapkan_taman(f)
        if m:
            masalah.append(f"taman {f['properties'].get('nama_taman')!r}: " + "; ".join(m))
        else:
            baris.append(row)
            kunci[(row[2], row[0])] += 1
    masalah += [f"taman ganda (kota, nama): {k}" for k, n in kunci.items() if n > 1]
    if masalah:
        print(f"GAGAL: {len(masalah)} pelanggaran data (15 pertama):")
        for x in masalah[:15]:
            print(" -", x)
        sys.exit(1)
    print(f"Dibaca: {len(provinsi)} provinsi, {len(kota)} kota/kab, {len(baris)} taman", flush=True)

    # Satu transaksi: gagal di tengah jalan = tidak ada perubahan.
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE stg_prov (osm_id bigint, name text, geom geometry) ON COMMIT DROP;
            CREATE TEMP TABLE stg_kota (osm_id bigint, name text, prov_name text, geom geometry) ON COMMIT DROP;
            CREATE TEMP TABLE stg_taman (name text, category text, kota_asal text,
                latitude numeric(9,6), longitude numeric(9,6), geom geometry) ON COMMIT DROP""")
        cur.executemany(f"INSERT INTO stg_prov VALUES (%s, %s, {GEOM})",
                        [(int(f["properties"]["prov_osm_id"]), f["properties"]["prov_name"], json.dumps(f["geometry"]))
                         for f in provinsi])
        cur.executemany(f"INSERT INTO stg_kota VALUES (%s, %s, %s, {GEOM})",
                        [(int(f["properties"]["city_osm_id"]), f["properties"]["city_name"],
                          f["properties"]["prov_name"], json.dumps(f["geometry"])) for f in kota])
        cur.executemany(f"INSERT INTO stg_taman VALUES (%s, %s, %s, %s, %s, {GEOM})", baris)

        cur.execute(f"""
            INSERT INTO provinces (osm_id, name, geom)
            SELECT osm_id, name, {POLIGON} FROM stg_prov
            ON CONFLICT (osm_id) DO UPDATE SET name = EXCLUDED.name, geom = EXCLUDED.geom
            RETURNING id""")
        prov = [r[0] for r in cur.fetchall()]

        # Nama kembar dalam satu provinsi (mis. Blitar): poligon lebih kecil = Kota, lebih besar = Kabupaten.
        cur.execute(f"""
            INSERT INTO cities (province_id, osm_id, name, geom)
            SELECT p.id, s.osm_id,
                   CASE WHEN s.bedakan AND s.r = 1 THEN 'Kota ' || s.name
                        WHEN s.bedakan AND s.r = 2 THEN 'Kabupaten ' || s.name
                        ELSE s.name END,
                   s.geom
            FROM (SELECT k.*,
                         (count(*) OVER (PARTITION BY k.prov_name, k.name) = 2
                          AND k.name !~ '^(Kota|Kabupaten) ') AS bedakan,
                         rank() OVER (PARTITION BY k.prov_name, k.name ORDER BY ST_Area(k.geom::geography)) AS r
                  FROM (SELECT osm_id, name, prov_name, {POLIGON} AS geom FROM stg_kota) k) s
            JOIN provinces p ON p.id = ANY(%s) AND p.name = s.prov_name
            ON CONFLICT (osm_id) DO UPDATE
              SET province_id = EXCLUDED.province_id, name = EXCLUDED.name, geom = EXCLUDED.geom
            RETURNING id, osm_id, name""", (prov,))
        hasil_kota = cur.fetchall()
        kota_pk = [r[0] for r in hasil_kota]
        asli = {int(f["properties"]["city_osm_id"]): f["properties"]["city_name"] for f in kota}
        diganti = [(asli[o], n) for _, o, n in hasil_kota if n != asli[o]]
        cur.execute("SELECT province_id, name FROM cities WHERE id = ANY(%s) GROUP BY 1, 2 HAVING count(*) > 1",
                    (kota_pk,))
        if cur.fetchall():
            sys.exit("GAGAL: nama kota/kab masih kembar dalam satu provinsi; perbaiki city_name di cities.geojson")

        # Kota tiap taman = poligon kota yang memuat titiknya (LIMIT 1: titik tepat di garis batas).
        cur.execute("""
            CREATE TEMP TABLE stg_join ON COMMIT DROP AS
            SELECT s.*, c.id AS city_id, c.name AS city_name
            FROM stg_taman s LEFT JOIN LATERAL (
              SELECT id, name FROM cities WHERE id = ANY(%s) AND ST_Covers(geom, s.geom) LIMIT 1) c ON true""",
                    (kota_pk,))
        cur.execute("SELECT name, kota_asal FROM stg_join WHERE city_id IS NULL ORDER BY 2, 1")
        di_luar = cur.fetchall()
        if di_luar:
            sys.exit("GAGAL: titik taman di luar semua poligon kota/kab: "
                     + ", ".join(f"{n} ({k})" for n, k in di_luar))
        cur.execute("SELECT city_id, name FROM stg_join GROUP BY 1, 2 HAVING count(*) > 1")
        if cur.fetchall():
            sys.exit("GAGAL: nama taman kembar dalam satu kota/kab hasil join spasial")

        cur.execute("""
            INSERT INTO parks (city_id, name, category, latitude, longitude, geom)
            SELECT city_id, name, category, latitude, longitude, geom::geography FROM stg_join
            ON CONFLICT (city_id, name) DO UPDATE SET
              category = EXCLUDED.category, latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
              geom = EXCLUDED.geom, address = NULL, fee_tag = NULL, updated_at = now()
            RETURNING id""")
        taman_pk = [r[0] for r in cur.fetchall()]
        # Hapus yang tidak ada pada run ini (urutan: taman -> kota -> provinsi, patuh FK).
        cur.execute("DELETE FROM parks WHERE id <> ALL(%s)", (taman_pk,))
        cur.execute("DELETE FROM cities WHERE id <> ALL(%s)", (kota_pk,))
        cur.execute("DELETE FROM provinces WHERE id <> ALL(%s)", (prov,))
        cur.execute("ANALYZE provinces; ANALYZE cities; ANALYZE parks")

        cur.execute("SELECT category, count(*) FROM parks GROUP BY category ORDER BY category")
        per_kategori = cur.fetchall()
        cur.execute("""SELECT pr.name, count(*) FROM parks p JOIN cities c ON c.id = p.city_id
                       JOIN provinces pr ON pr.id = c.province_id GROUP BY 1 ORDER BY 1""")
        per_provinsi = cur.fetchall()
        # Info: kota hasil join spasial berbeda dari kolom kota_kabupaten data tim (koordinat bisa meleset).
        cur.execute("""
            SELECT name, kota_asal, city_name FROM stg_join
            WHERE city_name NOT ILIKE '%' || regexp_replace(kota_asal, '^(Kota|Kabupaten) ', '') || '%'
            ORDER BY 2, 1""")
        beda_kota = cur.fetchall()

    print("=== Ringkasan ETL ===")
    print(f"Provinsi: {len(prov)} | Kota/Kab: {len(kota_pk)}")
    if diganti:
        print("Nama kembar dibedakan: " + ", ".join(f"{a} -> {b}" for a, b in sorted(diganti, key=lambda x: x[1])))
    print(f"Taman tersimpan: {sum(n for _, n in per_kategori)} ("
          + ", ".join(f"{k}={n}" for k, n in per_kategori) + ")")
    print("Per provinsi: " + ", ".join(f"{k}={n}" for k, n in per_provinsi))
    if beda_kota:
        print(f"PERINGATAN: {len(beda_kota)} taman jatuh di kota/kab lain dari kolom kota_kabupaten:")
        for n, a, c in beda_kota:
            print(f" - {n}: data={a}, titik di {c}")


def selftest():
    assert kategori("Alun-Alun Kota Serang (Taman Kota)") == "alun_alun"
    assert kategori("Alun Alun Bandung") == "alun_alun"
    assert kategori("Hutan Kota Pamulang") == "rth"
    assert kategori("RTH Maya Datar") == "rth"
    assert kategori("Taman Perdamaian BSD") == "taman_kota"
    assert kategori("Taman Kota Pandancang") == "taman_kota"

    def taman(nama="Taman A", coords=(107.6, -6.9), tipe="Point"):
        return {"properties": {"nama_taman": nama, "kota_kabupaten": "Kota Bandung", "status": "Aktif"},
                "geometry": {"type": tipe, "coordinates": list(coords)}}

    row, m = siapkan_taman(taman())
    assert m == [] and row[:5] == ("Taman A", "taman_kota", "Kota Bandung", -6.9, 107.6)
    assert siapkan_taman(taman(nama=" "))[1] == ["nama kosong"]
    assert siapkan_taman(taman(coords=(200, -6.9)))[1] == ["koordinat di luar rentang"]
    assert siapkan_taman(taman(tipe="Polygon"))[1] == ["geometri bukan Point"]
    print("selftest OK")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
