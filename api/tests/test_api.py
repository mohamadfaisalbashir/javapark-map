"""Uji black box API terhadap layanan yang sedang berjalan: TC-08, TC-09, TC-10 + bentuk kontrak.

Jalankan (layanan db, api sudah up dan ETL sudah dimuat):
    docker compose exec -T api python -m unittest discover -s tests -v
"""
import json
import os
import unittest
import urllib.error
import urllib.request

import psycopg

API = os.environ.get("API_URL", "http://localhost:8000")
DB = os.environ["DATABASE_URL"]

# Lima titik uji TC-10, tersebar di Jawa (Monas, Bandung, Tugu Yogyakarta, Surabaya, Semarang).
TITIK = [(-6.1754, 106.8272), (-6.9218, 107.6048), (-7.7829, 110.3671), (-7.2575, 112.7521), (-6.9932, 110.4203)]


def get(path):
    try:
        with urllib.request.urlopen(API + path, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def sql(query, *params):
    with psycopg.connect(DB) as conn:
        return conn.execute(query, params).fetchall()


class Kontrak(unittest.TestCase):
    def test_health(self):
        self.assertEqual(get("/api/health"), (200, {"status": "ok"}))

    def test_regions(self):
        status, data = get("/api/regions")
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 6)  # 6 provinsi Jawa (Bagian 4)
        for prov in data:
            self.assertEqual(set(prov), {"id", "name", "cities"})
            self.assertTrue(prov["cities"])
            self.assertEqual(set(prov["cities"][0]), {"id", "name"})

    def test_bbox(self):
        _, regions = get("/api/regions")
        prov = regions[0]
        for tipe, id_ in (("province", prov["id"]), ("city", prov["cities"][0]["id"])):
            status, data = get(f"/api/regions/{tipe}/{id_}/bbox")
            self.assertEqual(status, 200)
            min_lon, min_lat, max_lon, max_lat = data["bbox"]
            self.assertLess(min_lon, max_lon)
            self.assertLess(min_lat, max_lat)

    def test_parks_geojson_per_provinsi(self):
        _, regions = get("/api/regions")
        pid = regions[0]["id"]
        status, fc = get(f"/api/parks?province_id={pid}")
        self.assertEqual(status, 200)
        self.assertEqual(fc["type"], "FeatureCollection")
        ada = sql("SELECT count(*) FROM parks p JOIN cities c ON c.id = p.city_id WHERE c.province_id = %s", pid)[0][0]
        self.assertEqual(len(fc["features"]), ada)
        f = fc["features"][0]
        self.assertEqual(set(f["properties"]), {"id", "name", "category", "address", "city", "province"})
        self.assertEqual(f["geometry"]["type"], "Point")
        lon, lat = f["geometry"]["coordinates"]  # urutan GeoJSON
        self.assertTrue(105 < lon < 115 and -9 < lat < -5)

    def test_stats(self):
        status, data = get("/api/stats/parks-per-city?limit=20")
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 20)
        self.assertEqual(set(data[0]), {"city_id", "city_name", "count"})
        counts = [d["count"] for d in data]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_stats_satu_kota(self):
        _, regions = get("/api/regions")
        cid = regions[0]["cities"][0]["id"]
        status, data = get(f"/api/stats/parks-per-city?city_id={cid}")
        self.assertEqual(status, 200)
        self.assertEqual([d["city_id"] for d in data], [cid])

    def test_404_id_tidak_ada(self):
        for path in ("/api/regions/city/999999/bbox", "/api/parks?province_id=999999",
                     "/api/stats/parks-per-city?city_id=999999"):
            status, body = get(path)
            self.assertEqual(status, 404, path)
            self.assertIsInstance(body["detail"], str)


class DataDanTerdekat(unittest.TestCase):
    def test_tc08_tidak_ada_taman_berbayar(self):
        """TC-08: query DB fee_tag = 'yes' -> 0 baris."""
        self.assertEqual(sql("SELECT count(*) FROM parks WHERE fee_tag = 'yes'")[0][0], 0)

    def test_tc09_parameter_tidak_valid_400(self):
        """TC-09: lat=999 -> 400 dengan {"detail": "<pesan>"}."""
        for path in ("/api/parks/nearest?lat=999&lon=0", "/api/parks/nearest?lat=0&lon=181",
                     "/api/parks/nearest?lat=0", "/api/parks/nearest?lat=abc&lon=0",
                     "/api/parks/nearest?lat=0&lon=0&limit=51", "/api/parks/nearest?lat=0&lon=0&radius_km=51"):
            status, body = get(path)
            self.assertEqual(status, 400, path)
            self.assertIsInstance(body["detail"], str)

    def test_tc10_terdekat_sama_dengan_sql_manual(self):
        """TC-10: urutan dan jarak identik dengan query SQL manual untuk 5 titik."""
        for lat, lon in TITIK:
            status, hasil = get(f"/api/parks/nearest?lat={lat}&lon={lon}")
            self.assertEqual(status, 200)
            manual = sql("""
                WITH t AS (SELECT ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography AS g)
                SELECT p.id::text, ST_Distance(p.geom, t.g) AS d FROM parks p, t
                WHERE ST_Distance(p.geom, t.g) <= 10000 ORDER BY d LIMIT 10""", lon, lat)
            self.assertTrue(hasil, f"tidak ada taman dalam 10 km dari {lat},{lon}")
            self.assertEqual([h["id"] for h in hasil], [m[0] for m in manual])
            for h, m in zip(hasil, manual):
                self.assertAlmostEqual(h["distance_m"], m[1], places=6)
            self.assertEqual(set(hasil[0]), {"id", "name", "category", "latitude", "longitude", "distance_m"})
            self.assertEqual([h["distance_m"] for h in hasil], sorted(h["distance_m"] for h in hasil))

    def test_terdekat_di_laut_kosong(self):
        status, hasil = get("/api/parks/nearest?lat=-10.5&lon=110")  # Samudra Hindia
        self.assertEqual((status, hasil), (200, []))

    def test_limit_dan_radius(self):
        _, hasil = get("/api/parks/nearest?lat=-6.9218&lon=107.6048&limit=3&radius_km=2")
        self.assertLessEqual(len(hasil), 3)
        self.assertTrue(all(h["distance_m"] <= 2000 for h in hasil))


if __name__ == "__main__":
    unittest.main()
