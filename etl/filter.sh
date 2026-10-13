#!/usr/bin/env sh
# Langkah 1 Pipeline ETL (requirements 6.3). Sudah dijalankan manual oleh tim;
# disimpan di sini sebagai dokumentasi agar ekstraksi dapat diulang.
# Masukan: java-261006.osm.pbf (Geofabrik, 6 Oktober 2026). Keluaran: data/raw/.
set -eu

osmium tags-filter java-261006.osm.pbf nwr/leisure=park,garden nwr/landuse=recreation_ground nwr/place=square -o parks_all.osm.pbf
osmium tags-filter java-261006.osm.pbf r/boundary=administrative -o admin_all.osm.pbf
osmium tags-filter admin_all.osm.pbf r/admin_level=4,5 -o boundaries.osm.pbf
