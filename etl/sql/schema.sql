-- Skema Bagian 7. Idempoten; SRID 4326 untuk semua geometri.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS provinces (
    id     serial PRIMARY KEY,
    osm_id bigint NOT NULL UNIQUE,
    name   text   NOT NULL,
    geom   geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS provinces_geom_gix ON provinces USING gist (geom);

CREATE TABLE IF NOT EXISTS cities (
    id          serial PRIMARY KEY,
    province_id int    NOT NULL REFERENCES provinces (id),
    osm_id      bigint NOT NULL UNIQUE,
    name        text   NOT NULL,
    geom        geometry(MultiPolygon, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS cities_geom_gix ON cities USING gist (geom);
CREATE INDEX IF NOT EXISTS cities_province_idx ON cities (province_id);

CREATE TABLE IF NOT EXISTS parks (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    city_id    int          NOT NULL REFERENCES cities (id),
    name       text         NOT NULL,
    category   text         NOT NULL CHECK (category IN ('taman_kota', 'rth', 'alun_alun')),
    address    text,
    latitude   numeric(9,6) NOT NULL,
    longitude  numeric(9,6) NOT NULL,
    geom       geography(Point, 4326) NOT NULL,
    fee_tag    text,
    updated_at timestamptz  NOT NULL DEFAULT now(),
    UNIQUE (city_id, name)
);
-- FR-06: titik tur 360° (etl/cek_pano.py): "lat,lon;lat,lon" di dalam taman, atau "lat,lon,heading" dari tepi.
-- Koordinat panorama Street View, bukan pano_id (Google: jangan dipersist).
ALTER TABLE parks DROP COLUMN IF EXISTS vr_source, DROP COLUMN IF EXISTS mapillary_id;
ALTER TABLE parks ADD COLUMN IF NOT EXISTS pano_titik text;
-- FR-11: fasilitas (kunci = FASILITAS di etl/load.py) dan apakah sudah diverifikasi tim (false = draf OSM).
-- ALTER agar DB lama ikut termigrasi: docker compose exec -T db psql -U taman -d taman < etl/sql/schema.sql
ALTER TABLE parks ADD COLUMN IF NOT EXISTS facilities text[] NOT NULL DEFAULT '{}';
ALTER TABLE parks ADD COLUMN IF NOT EXISTS facilities_verified boolean NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS parks_geom_gix ON parks USING gist (geom);
CREATE INDEX IF NOT EXISTS parks_city_idx ON parks (city_id);
