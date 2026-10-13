"""API read-only taman kota Pulau Jawa (requirements Bagian 9).

Koordinat GeoJSON berurutan [longitude, latitude]. Tidak ada endpoint tulis.
"""
import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import create_engine, text

engine = create_engine(
    os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1),
    pool_pre_ping=True,
)

app = FastAPI(title="Taman Kota Pulau Jawa")
app.add_middleware(GZipMiddleware, minimum_size=1000)  # GeoJSON se-Jawa: NFR-01
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])


@app.exception_handler(RequestValidationError)
async def parameter_tidak_valid(_, exc: RequestValidationError):
    """Bagian 9: parameter tidak valid -> 400 {"detail": "<pesan>"} (bukan 422)."""
    pesan = "; ".join(f"{'.'.join(str(x) for x in e['loc'][1:])}: {e['msg']}" for e in exc.errors())
    return JSONResponse({"detail": f"Parameter tidak valid - {pesan}"}, status_code=400)


def rows(sql, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).mappings().all()


def pastikan_ada(tabel, id_, label):
    if id_ is not None and not rows(f"SELECT 1 FROM {tabel} WHERE id = :id", id=id_):
        raise HTTPException(404, f"{label} dengan id {id_} tidak ditemukan")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/regions")
def regions():
    return [dict(r) for r in rows("""
        SELECT p.id, p.name,
               coalesce(json_agg(json_build_object('id', c.id, 'name', c.name) ORDER BY c.name)
                        FILTER (WHERE c.id IS NOT NULL), '[]'::json) AS cities
        FROM provinces p LEFT JOIN cities c ON c.province_id = p.id
        GROUP BY p.id ORDER BY p.name""")]


@app.get("/api/regions/{type}/{id}/bbox")
def bbox(type: Literal["province", "city"], id: int):
    tabel = "provinces" if type == "province" else "cities"
    r = rows(f"""
        SELECT ST_XMin(b) AS min_lon, ST_YMin(b) AS min_lat, ST_XMax(b) AS max_lon, ST_YMax(b) AS max_lat
        FROM (SELECT ST_Extent(geom) AS b FROM {tabel} WHERE id = :id) s""", id=id)[0]
    if r["min_lon"] is None:
        raise HTTPException(404, f"Wilayah {type} dengan id {id} tidak ditemukan")
    return {"bbox": [r["min_lon"], r["min_lat"], r["max_lon"], r["max_lat"]]}


@app.get("/api/parks")
def parks(province_id: int | None = None, city_id: int | None = None):
    pastikan_ada("provinces", province_id, "Provinsi")
    pastikan_ada("cities", city_id, "Kota/kabupaten")
    # GeoJSON dirakit di SQL dan dikirim apa adanya (tanpa serialisasi ulang di Python).
    geojson = rows("""
        SELECT json_build_object('type', 'FeatureCollection', 'features', coalesce(json_agg(
                 json_build_object(
                   'type', 'Feature',
                   'geometry', ST_AsGeoJSON(p.geom::geometry, 6)::json,
                   'properties', json_build_object('id', p.id, 'name', p.name, 'category', p.category,
                                                   'address', p.address, 'city', c.name, 'province', pr.name))
                 ORDER BY p.name, p.id), '[]'::json))::text AS g
        FROM parks p
        JOIN cities c ON c.id = p.city_id
        JOIN provinces pr ON pr.id = c.province_id
        WHERE (CAST(:pid AS int) IS NULL OR pr.id = CAST(:pid AS int))
          AND (CAST(:cid AS int) IS NULL OR c.id = CAST(:cid AS int))""",
                  pid=province_id, cid=city_id)[0]["g"]
    return Response(geojson, media_type="application/json")


@app.get("/api/parks/nearest")
def nearest(lat: float = Query(..., ge=-90, le=90),
            lon: float = Query(..., ge=-180, le=180),
            limit: int = Query(10, ge=1, le=50),
            radius_km: float = Query(10, gt=0, le=50)):
    return [dict(r) for r in rows("""
        WITH t AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS g)
        SELECT p.id, p.name, p.category,
               p.latitude::float8 AS latitude, p.longitude::float8 AS longitude,
               ST_Distance(p.geom, t.g) AS distance_m
        FROM parks p, t
        WHERE ST_DWithin(p.geom, t.g, :radius_m)
        ORDER BY p.geom <-> t.g
        LIMIT :limit""", lat=lat, lon=lon, radius_m=radius_km * 1000, limit=limit)]


@app.get("/api/stats/parks-per-city")
def parks_per_city(province_id: int | None = None, city_id: int | None = None,
                   limit: int | None = Query(None, ge=1)):
    pastikan_ada("provinces", province_id, "Provinsi")
    pastikan_ada("cities", city_id, "Kota/kabupaten")
    return [dict(r) for r in rows("""
        SELECT c.id AS city_id, c.name AS city_name, count(p.id) AS count
        FROM cities c LEFT JOIN parks p ON p.city_id = c.id
        WHERE (CAST(:pid AS int) IS NULL OR c.province_id = CAST(:pid AS int))
          AND (CAST(:cid AS int) IS NULL OR c.id = CAST(:cid AS int))
        GROUP BY c.id
        ORDER BY count DESC, c.name
        LIMIT CAST(:limit AS int)""", pid=province_id, cid=city_id, limit=limit)]
