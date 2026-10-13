"""ETL OSM -> PostGIS (requirements 6.3 dan 6.4).

Membaca data/raw/boundaries.osm.pbf dan data/raw/parks_all.osm.pbf, memilih taman
sesuai aturan 6.4, lalu memuat provinces, cities, parks. Idempoten: dijalankan ulang
pada masukan yang sama menghasilkan isi tabel yang sama (upsert berdasarkan
osm_type + osm_id, lalu hapus baris yang tidak ada pada run ini).

    docker compose run --rm etl                             # ETL penuh
    docker compose run --rm etl python load.py --selftest   # uji aturan 6.4, tanpa DB
"""
import collections
import os
import re
import sys

import osmium
import psycopg

RAW = "/data/raw"
# Bagian 4: hanya 6 provinsi Pulau Jawa (ISO 3166-2 pada relasi admin_level=4).
PROVINSI_JAWA = ["ID-BT", "ID-JK", "ID-JB", "ID-JT", "ID-YO", "ID-JI"]
ALUN = re.compile(r"alun[- ]alun", re.I)
AKSES_TERBATAS = {"private", "no", "customers", "permit"}
TERLARANG = [("tourism", "theme_park"), ("tourism", "zoo"), ("leisure", "water_park"),
             ("leisure", "golf_course"), ("landuse", "cemetery")]
WKB = osmium.geom.WKBFactory()


def classify(t):
    """Aturan 6.4 untuk satu objek (t: dict atau osmium TagList).

    -> (kategori, None)  diterima
       (None, alasan)    dibuang
       (None, None)      bukan tag utama (objek pendukung di PBF), diabaikan
    """
    leisure, landuse, place = t.get("leisure"), t.get("landuse"), t.get("place")
    if not (leisure in ("park", "garden") or landuse == "recreation_ground" or place == "square"):
        return None, None
    name = t.get("name")
    if not name:
        return None, "tanpa_nama"
    if t.get("fee") == "yes" or t.get("charge"):
        return None, "berbayar"
    if t.get("access") in AKSES_TERBATAS:
        return None, "akses_terbatas"
    if any(t.get(k) == v for k, v in TERLARANG):
        return None, "jenis_terlarang"
    taman = leisure == "park" or (leisure == "garden" and t.get("garden:type") not in ("residential", "private"))
    if not (taman or landuse == "recreation_ground" or place == "square"):
        return None, "garden_privat"
    # Nama "Alun-alun" / "Alun Alun" menentukan kategori objek ber-tag utama (bukan syarat seleksi).
    if place == "square" or ALUN.search(name):
        return "alun_alun", None
    return ("taman_kota" if taman else "rth"), None


def alamat(t):
    """address (7.1): dari tag addr:* bila ada."""
    if t.get("addr:full"):
        return t.get("addr:full")
    jalan = " ".join(x for x in (t.get("addr:street"), t.get("addr:housenumber")) if x)
    bagian = [jalan, t.get("addr:suburb"), t.get("addr:city"), t.get("addr:postcode")]
    return ", ".join(x for x in bagian if x) or None


def baca_batas(c, gagal):
    """(osm_id, level, nama, iso, wkb) relasi administrative admin_level 4/5 yang berhasil dirakit."""
    for o in osmium.FileProcessor(f"{RAW}/boundaries.osm.pbf").with_locations().with_areas():
        if not o.is_area() or o.from_way():  # hanya multipolygon dari relasi
            continue
        t = o.tags
        if t.get("boundary") != "administrative" or t.get("admin_level") not in ("4", "5"):
            continue
        level, nama = int(t.get("admin_level")), t.get("name")
        if level == 5:
            # name OSM tidak konsisten ("Blitar" untuk kota dan kabupaten); official_name
            # ("Kota Blitar" / "Kabupaten Blitar") membedakannya. Fallback ke name.
            nama = t.get("official_name") or nama
        try:
            wkb = WKB.create_multipolygon(o)
        except RuntimeError:  # relasi terpotong di tepi ekstrak (mis. provinsi luar Jawa)
            gagal.append((level, nama))
            continue
        yield o.orig_id(), level, nama, t.get("ISO3166-2"), wkb


def baca_taman(c):
    """(osm_type, osm_id, name, category, address, fee_tag, wkb) untuk node dan area terpilih."""
    for o in osmium.FileProcessor(f"{RAW}/parks_all.osm.pbf").with_locations().with_areas():
        if o.is_node():
            tipe = "node"
        elif o.is_area():
            tipe = "way" if o.from_way() else "relation"
        else:
            continue  # way/relasi mentah sudah terwakili oleh areanya
        kategori, alasan = classify(o.tags)
        if kategori is None:
            if alasan:
                c[alasan] += 1
            continue
        try:
            wkb = WKB.create_point(o) if tipe == "node" else WKB.create_multipolygon(o)
        except RuntimeError:
            c["geometri_tidak_valid"] += 1
            continue
        t = o.tags
        yield (tipe, o.id if tipe == "node" else o.orig_id(), t.get("name"),
               kategori, alamat(t), t.get("fee"), wkb)


GEOM = "ST_GeomFromWKB(decode(%s, 'hex'), 4326)"
POLIGON = "ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3))"


def main():
    c = collections.Counter()
    gagal = []
    batas = list(baca_batas(c, gagal))
    taman = list(baca_taman(c))
    print(f"Dibaca: {len(batas)} batas, {len(taman)} taman lolos aturan tag", flush=True)

    # Satu transaksi: gagal di tengah jalan = tidak ada perubahan.
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE stg_batas (osm_id bigint, level int, name text, iso text, geom geometry) ON COMMIT DROP")
        cur.execute("CREATE TEMP TABLE stg_taman (osm_type text, osm_id bigint, name text, category text,"
                    " address text, fee_tag text, geom geometry) ON COMMIT DROP")
        cur.executemany(f"INSERT INTO stg_batas VALUES (%s, %s, %s, %s, {GEOM})", batas)
        cur.executemany(f"INSERT INTO stg_taman VALUES (%s, %s, %s, %s, %s, %s, {GEOM})", taman)

        cur.execute(f"""
            INSERT INTO provinces (osm_id, name, geom)
            SELECT osm_id, name, {POLIGON} FROM stg_batas WHERE level = 4 AND iso = ANY(%s)
            ON CONFLICT (osm_id) DO UPDATE SET name = EXCLUDED.name, geom = EXCLUDED.geom
            RETURNING id""", (PROVINSI_JAWA,))
        prov = [r[0] for r in cur.fetchall()]
        if len(prov) != len(PROVINSI_JAWA):
            sys.exit(f"GAGAL: provinsi Jawa terbaca {len(prov)}, seharusnya {len(PROVINSI_JAWA)}")

        # Kota -> provinsi: titik-di-permukaan kota berada di dalam poligon provinsi (7.1).
        cur.execute(f"""
            INSERT INTO cities (province_id, osm_id, name, geom)
            SELECT DISTINCT ON (a.osm_id) p.id, a.osm_id, a.name, a.geom
            FROM (SELECT osm_id, name, {POLIGON} AS geom FROM stg_batas WHERE level = 5) a
            JOIN provinces p ON p.id = ANY(%s) AND ST_Contains(p.geom, ST_PointOnSurface(a.geom))
            ORDER BY a.osm_id, p.id
            ON CONFLICT (osm_id) DO UPDATE
              SET province_id = EXCLUDED.province_id, name = EXCLUDED.name, geom = EXCLUDED.geom
            RETURNING id""", (prov,))
        kota = [r[0] for r in cur.fetchall()]

        # Titik taman = ST_PointOnSurface; city_id = ST_Contains; di luar semua kota dibuang.
        # Bila kota bertumpang tindih, pilih yang terkecil (paling spesifik).
        cur.execute(f"""
            CREATE TEMP TABLE located ON COMMIT DROP AS
            SELECT DISTINCT ON (s.osm_type, s.osm_id)
                   s.osm_type, s.osm_id, s.name, s.category, s.address, s.fee_tag, s.geom, s.pt, c.id AS city_id
            FROM (SELECT *, ST_PointOnSurface(geom) AS pt FROM (
                    SELECT osm_type, osm_id, name, category, address, fee_tag,
                           CASE WHEN GeometryType(geom) = 'POINT' THEN geom ELSE {POLIGON} END AS geom
                    FROM stg_taman) v) s
            JOIN cities c ON c.id = ANY(%s) AND ST_Contains(c.geom, s.pt)
            ORDER BY s.osm_type, s.osm_id, ST_Area(c.geom), c.id""", (kota,))
        # Deduplikasi 6.4: node bernama sama dalam <= 100 m dari poligon -> simpan poligon saja.
        cur.execute("""
            CREATE TEMP TABLE kept ON COMMIT DROP AS
            SELECT l.* FROM located l
            WHERE NOT (l.osm_type = 'node' AND EXISTS (
                SELECT 1 FROM located q
                WHERE q.osm_type <> 'node'
                  AND lower(btrim(q.name)) = lower(btrim(l.name))
                  AND ST_DWithin(l.pt::geography, q.geom::geography, 100)))""")

        cur.execute("""
            INSERT INTO parks (city_id, osm_type, osm_id, name, category, address, latitude, longitude, geom, fee_tag)
            SELECT city_id, osm_type, osm_id, name, category, address,
                   round(ST_Y(pt)::numeric, 6), round(ST_X(pt)::numeric, 6), pt::geography, fee_tag
            FROM kept
            ON CONFLICT (osm_type, osm_id) DO UPDATE SET
              city_id = EXCLUDED.city_id, name = EXCLUDED.name, category = EXCLUDED.category,
              address = EXCLUDED.address, latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude,
              geom = EXCLUDED.geom, fee_tag = EXCLUDED.fee_tag, updated_at = now()""")
        # Hapus yang tidak ada pada run ini (urutan: taman -> kota -> provinsi, patuh FK).
        cur.execute("DELETE FROM parks p WHERE NOT EXISTS"
                    " (SELECT 1 FROM kept k WHERE k.osm_type = p.osm_type AND k.osm_id = p.osm_id)")
        cur.execute("DELETE FROM cities WHERE id <> ALL(%s)", (kota,))
        cur.execute("DELETE FROM provinces WHERE id <> ALL(%s)", (prov,))
        cur.execute("ANALYZE provinces; ANALYZE cities; ANALYZE parks")

        cur.execute("SELECT count(*) FROM located")
        n_located = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM kept")
        n_kept = cur.fetchone()[0]
        cur.execute("SELECT category, count(*) FROM parks GROUP BY category ORDER BY category")
        per_kategori = cur.fetchall()

    print("=== Ringkasan ETL ===")
    print(f"Provinsi: {len(prov)} | Kota/Kab: {len(kota)}")
    if gagal:
        print("Batas gagal dirakit (diabaikan): " + ", ".join(f"{n} (level {l})" for l, n in sorted(gagal)))
    print("Dibuang per alasan:", ", ".join(f"{k}={v}" for k, v in sorted(c.items())) or "-")
    print(f"Dibuang di luar batas kota: {len(taman) - n_located}")
    print(f"Dibuang duplikat node-poligon: {n_located - n_kept}")
    print(f"Taman tersimpan: {n_kept} (" + ", ".join(f"{k}={v}" for k, v in per_kategori) + ")")


def selftest():
    taman = {"leisure": "park", "name": "Taman A"}
    kasus = [
        (taman, ("taman_kota", None)),
        ({"leisure": "park"}, (None, "tanpa_nama")),
        ({"place": "square", "name": "Lapangan B"}, ("alun_alun", None)),
        ({**taman, "name": "Alun-Alun Kota"}, ("alun_alun", None)),
        ({**taman, "name": "ALUN ALUN Selatan"}, ("alun_alun", None)),
        ({"landuse": "recreation_ground", "name": "RTH C"}, ("rth", None)),
        ({**taman, "fee": "yes"}, (None, "berbayar")),
        ({**taman, "fee": "no"}, ("taman_kota", None)),
        ({**taman, "charge": "5000"}, (None, "berbayar")),
        ({**taman, "access": "private"}, (None, "akses_terbatas")),
        ({**taman, "access": "permissive"}, ("taman_kota", None)),
        ({**taman, "access": "destination"}, ("taman_kota", None)),
        ({**taman, "tourism": "zoo"}, (None, "jenis_terlarang")),
        ({"landuse": "recreation_ground", "leisure": "golf_course", "name": "Golf"}, (None, "jenis_terlarang")),
        ({"leisure": "garden", "name": "Kebun", "garden:type": "residential"}, (None, "garden_privat")),
        ({"leisure": "garden", "name": "Kebun"}, ("taman_kota", None)),
        ({"leisure": "garden", "name": "Kebun", "garden:type": "private", "landuse": "recreation_ground"}, ("rth", None)),
        ({"highway": "pedestrian", "name": "Jalan Alun-Alun"}, (None, None)),
    ]
    for tag, harapan in kasus:
        hasil = classify(tag)
        assert hasil == harapan, f"{tag} -> {hasil}, harapan {harapan}"
    print(f"selftest OK ({len(kasus)} kasus)")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
