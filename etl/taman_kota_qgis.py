"""Filter taman kota dari data/clean/parks_clean.geojson (dijalankan di QGIS).

Taman kota = taman publik di dalam kota yang memberi fasilitas (bermain, rekreasi, olahraga,
toilet, ruang hijau) bagi warga dan pengunjung, gratis (requirements.md Bagian 2).

Tahap 1 (aturan nama/tag OSM): setiap titik -> lolos / buang / ragu, beserta alasan.
Tahap 2 (verifikasi web): keputusan manual di data/clean/verifikasi_taman_kota.csv
(kolom osm_key, name, city_name, keputusan, sumber, catatan) menimpa hasil aturan.
Titik "ragu" yang tidak ada di CSV dibuang (alasan tidak_terverifikasi).

Keluaran (CRS84): data/clean/parks_taman_kota.geojson (dimuat ETL) dan
data/clean/parks_bukan_taman_kota.geojson (audit); di QGIS keduanya ditambahkan sebagai layer.

    QGIS Python Console : p = r"<repo>\\etl\\taman_kota_qgis.py"; exec(open(p, encoding="utf-8").read(), {"__file__": p})
    Python biasa        : python etl/taman_kota_qgis.py           (selftest)
                          python etl/taman_kota_qgis.py --ragu    (daftar titik ragu yang belum diverifikasi)
"""
import collections
import csv
import json
import os
import re
import sys

try:
    from qgis.core import QgsProject, QgsVectorLayer
except ImportError:  # dijalankan di luar QGIS
    QgsProject = None

CLEAN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "clean")
CSV_VERIFIKASI = os.path.join(CLEAN, "verifikasi_taman_kota.csv")


def _re(*kata):
    return re.compile(r"(?<![a-z0-9])(" + "|".join(kata) + r")(?![a-z0-9])", re.I)


# Alasan pertama yang cocok dipakai.
BUANG = [
    ("privat_hunian", _re(r"perumahan", r"perum", r"perumnas", r"cluster", r"klaster", r"residen\w*", r"regency",
                          r"village", r"estate", r"komplek", r"kompleks", r"villa", r"vila", r"griya", r"apartemen\w*",
                          r"towers?", r"kost?", r"kontrakan", r"rumah", r"house", r"home", r"rusunawa", r"fasum",
                          r"fasos", r"blok", r"sektor", r"palazzo", r"club ?house", r"bsd", r"metland",
                          r"grand wisata", r"meikarta", r"citraland", r"pakuwon", r"ifolia", r"jgc", r"emerald\w*",
                          r"kiarasari", r"bintaro jaya")),
    ("pendidikan", _re(r"sekolah", r"school", r"sd", r"sdn", r"smp\w*", r"sma\w?", r"smk\w?", r"smansa", r"smaga",
                       r"mts\w?", r"madrasah", r"tk", r"paud", r"slb", r"kanak-kanak", r"kinder", r"kampus",
                       r"universit\w+", r"politeknik", r"polinema", r"institut", r"fakultas", r"rektorat",
                       r"pascasarjana", r"postgraduate", r"magister", r"stikes", r"lppm", r"ugm", r"ui", r"its",
                       r"itb", r"uns", r"uny", r"ub", r"um", r"ut", r"unej", r"undip", r"unpad", r"upi", r"upn",
                       r"uii", r"umy", r"umm", r"ipb", r"ubl", r"uksw", r"amikom", r"fisip", r"fishipol", r"fisipol",
                       r"fishum", r"fiai", r"feb", r"fip", r"ft", r"fkm", r"mipa", r"filkom", r"fbipk", r"unsoed",
                       r"telkom", r"unrespati", r"iainu", r"uniss", r"stta", r"itenas", r"polman", r"stks", r"unesa",
                       r"untag", r"usm", r"utm", r"isi", r"saintek", r"mercu buana", r"jurusan", r"baak",
                       r"pondok pesant?ren", r"pon ?pes\.?", r"pmdg", r"gontor", r"aula", r"lembaga mahasiswa",
                       r"ukm", r"statistika", r"sosiologi", r"planologi", r"plano", r"geografi", r"teknik",
                       r"kimia", r"metrologi", r"perminyakan", r"sains", r"alumni", r"wisdom park", r"ubm", r"ptik",
                       r"pusat studi", r"syariah", r"tarbiyah", r"literasi uns", r"tunas bangsa fisip", r"pizza")),
    ("ibadah", _re(r"masjid", r"mesjid", r"musholl?a", r"mosque", r"surau", r"gereja", r"gkj", r"vihara", r"pura",
                   r"klenteng", r"goa maria", r"taman doa", r"islamic center", r"islam", r"ka'bah", r"tajug",
                   r"religi", r"at-?taqwa", r"al[- ]\w+", r"jami'?", r"baitul", r"ashabul kahfi", r"stella maris",
                   r"muhamm?addiyah", r"pusdai", r"gema quran", r"nurul (ikhlas|taubah)", r"mutma ?inah",
                   r"lumbini")),
    ("makam", _re(r"makam", r"pemakaman", r"tpu", r"kuburan", r"pesarean", r"astana\w*", r"memorial park",
                  r"punden")),
    ("instansi", _re(r"kantor", r"kecamatan", r"kelurahan", r"kelirahan", r"pengadilan", r"polres", r"polsek",
                     r"mapolres", r"polisi", r"koramil", r"brimob", r"mako", r"batalion", r"armed", r"tni",
                     r"pom au", r"marinir", r"brigif", r"kemenkeu", r"kementerian", r"pupr", r"djp", r"bpn", r"ojk",
                     r"lipi", r"bkpm", r"bp3ip", r"bbws", r"bppkad", r"kpp", r"pajak", r"bea cukai", r"setda",
                     r"dinas", r"dprd?", r"pemda", r"pemkab", r"rumah sakit", r"rs", r"rsu", r"puskesmas", r"klinik",
                     r"posyandu", r"pmi", r"peruri", r"pertamina", r"perhutani", r"ptpn", r"pln", r"bri", r"bank",
                     r"semen", r"balai penelitian", r"balai desa", r"balai padukuhan", r"balai warga", r"pendopo",
                     r"pendapa", r"penpodo", r"kawedanan", r"kadipaten", r"kepatihan", r"keraton", r"kraton",
                     r"kabupaten lama", r"bupati", r"walikota", r"korpri", r"rest area", r"tol", r"toll",
                     r"landfill", r"tpst", r"incenerator", r"pengolahan air", r"menara air", r"water tower",
                     r"stasiun cuaca", r"gardu", r"pos kamling", r"pos satpam", r"tzu chi", r"terminal",
                     r"stasiun", r"halte", r"lpm", r"pkk", r"karang taruna", r"humaniora", r"veteran",
                     r"himpunan wanita", r"pelni", r"sasana", r"budiarto", r"mpm motor", r"kemhan", r"tiara")),
    ("komersial", _re(r"hotel", r"resort", r"cottage", r"homestay", r"spa", r"mall", r"supermarket", r"plaza st\.?",
                      r"caf+e+", r"kafe", r"coffee", r"resto\w*", r"restaurant", r"warung", r"food ?court",
                      r"food veranda", r"food center", r"kuliner", r"wiskul", r"umkm", r"pt\.?", r"spbu",
                      r"pameran", r"brownies", r"strategic square", r"sampoerna", r"intercon", r"maspion",
                      r"twin lagoon", r"lagoon ville", r"scbd", r"thamrin 10", r"icon centro", r"pasar",
                      r"commercial", r"ciwalk", r"eatboss", r"rumah mode", r"setiabudhi supermarket",
                      r"bassura", r"gading walk", r"baywalk", r"sentul", r"discovery park")),
    ("wisata_berbayar_alam", _re(r"wisata", r"agrowisata", r"agro\w*", r"tourism", r"camp\w*", r"perkemahan",
                                 r"outbo?u?nd", r"glamping", r"water ?park", r"waterboom", r"water world",
                                 r"kolam renang", r"pemandian", r"hot spring", r"air panas", r"pantai", r"beach",
                                 r"curug", r"waterfall", r"goa", r"gua", r"gunung", r"bukit", r"hills?", r"highland",
                                 r"puncak", r"candi", r"situs", r"benteng", r"museum", r"musper", r"cagar alam",
                                 r"taman nasional", r"hutan lindung", r"hutan raya", r"hutan penelitian",
                                 r"hutan bambu", r"kebun raya", r"botani\w*", r"botanical", r"taman safari",
                                 r"kebun binatang", r"zoo", r"satwa", r"rusa", r"menjangan", r"penangkaran",
                                 r"theme park", r"amusement", r"taman mini", r"mini borobudur", r"sky ?view",
                                 r"view point", r"panorama\w*", r"ocean view", r"rekreasi", r"adventure", r"xtreme",
                                 r"edupark", r"educreation", r"ecopark", r"eco ?park", r"eco-edu", r"telaga",
                                 r"tlogo", r"embung", r"waduk", r"bendungan", r"situ", r"setu", r"danau", r"lake",
                                 r"umbul", r"sendang", r"sumber", r"tirta", r"kenjeran", r"ancol", r"dunia kartun",
                                 r"enchanting", r"heha", r"canyon", r"rockland", r"atas awan", r"jendela langit",
                                 r"mekarsari", r"pacuan kuda", r"sirkuit", r"offroad", r"paralayang",
                                 r"aeromodell?ing", r"gantole", r"stable", r"horse", r"kuda", r"kampung",
                                 r"kampoeng", r"lokawisata", r"taman budaya", r"budaya", r"seni", r"ismail marzuki",
                                 r"bilabong", r"pintar", r"bonsai", r"anggrek ragunan", r"bunga nusantara",
                                 r"sky garden", r"flower", r"celosia", r"love garden", r"rose", r"tea garden",
                                 r"teh", r"dayu", r"hiburan", r"remaja", r"festival", r"tarekot", r"kandank",
                                 r"jakarta escape", r"kiara artha", r"sriwedari", r"balekambang", r"taman kaliurang",
                                 r"labirin", r"pemancingan", r"kerang", r"kandang rusa", r"apung", r"bakau",
                                 r"mangrove", r"klorofil", r"maerakaca", r"maerokoco", r"selomangleng",
                                 r"keputran", r"kapur")),
    ("bukan_ruang_taman", _re(r"kebun", r"kebon", r"perkebunan", r"perekebunan", r"lahan", r"sawah",
                              r"persawahan", r"tegal", r"ladang", r"tebu", r"padi", r"jagung", r"farm\w*",
                              r"peternakan", r"ternak", r"kandang", r"nursery", r"pembibitan", r"persemaian",
                              r"bibit", r"petik", r"strawberry", r"apel", r"organic", r"orgnic", r"toga", r"toka",
                              r"herbal", r"apotik hidup", r"green ?house", r"pohon", r"rumput", r"parkir\w*",
                              r"parking", r"pakiran", r"titik kumpul", r"tempat (istirahat|peristirahatan|umum)",
                              r"ruang tunggu", r"smoking", r"gates?", r"gapuro", r"gerbang", r"batas desa",
                              r"perbatasan", r"jembatan", r"kali", r"kanal", r"irigasi", r"sungai", r"river\w*",
                              r"bantaran", r"sempadan", r"jalur hijau", r"jalur", r"median", r"pinggir jalan",
                              r"tengah jalan", r"jalan", r"jl\.?", r"penghijauan", r"vertical garden",
                              r"pedestrian", r"sideway", r"selasar", r"jogging\w*", r"bundaran", r"bunderan",
                              r"simpang\w*", r"pertigaan", r"perempatan", r"pertelon", r"segitiga", r"segi delapan",
                              r"triangle", r"triangel", r"tugu", r"patung", r"statue", r"monumen\w*", r"monument",
                              r"relief", r"prasasti", r"air mancur", r"fountain", r"kilometer nol", r"km \d+",
                              r"titik 0", r"0km", r"nol kilometer", r"pancer", r"green ?zone", r"gz", r"rfcgz",
                              r"gazebo", r"amphit\w+", r"court", r"ground", r"field", r"skate\w*", r"bmx",
                              r"archery", r"basket\w*", r"volley\w*", r"voli", r"volly", r"tenn?is", r"futsal",
                              r"bulu ?tangkis", r"takraw", r"cricket", r"gate ?ball", r"gor", r"gelanggang",
                              r"gelora", r"stadion", r"stadiun", r"sport\w*", r"olah ?raga", r"gymnasium", r"fitness",
                              r"strong arms", r"lomba burung", r"bird", r"burung", r"pet park",
                              r"kolam", r"pool", r"irigasi", r"tandon", r"viaduk", r"viaduct", r"lokomotif",
                              r"kereta", r"foto", r"film", r"potret", r"embung", r"magot", r"kelinci", r"layur",
                              r"bolder", r"oval", r"radio", r"rt ?\d+", r"rw ?[\dxvi]+", r"rt\.? ?\d+",
                              r"rw\.? ?[\dxvi]+", r"dawis", r"warga", r"lingkungan", r"tingkat rw", r"desa",
                              r"dusun", r"kecil", r"mini", r"mini park", r"kids?", r"bebskid", r"playgroud",
                              r"tire park", r"telur", r"teletubb?ies", r"unyil", r"superhero", r"kartun",
                              r"tematik", r"nabi", r"lansia", r"manula", r"balita")),
    ("lapangan", re.compile(r"^\s*(lapang\w*|lap\.?|lapanag\w*)(\s|$)", re.I)),
]

# Lolos langsung oleh aturan (tetap dapat dikoreksi lewat CSV verifikasi).
LOLOS = [
    ("alun_alun", re.compile(r"alun[\s-]*alun|aloon[\s-]*aloon", re.I)),
    ("rptra", _re(r"rptra")),
    ("hutan_kota", re.compile(r"hutan\s+(taman\s+)?kota|urban forest", re.I)),
    ("taman_kota", re.compile(r"taman\s+kota\s+\S|city park", re.I)),
    ("taman_publik", _re(r"taman lalu[ -]?lintas", r"taman lalulintas", r"taman interaktif( rw \d+)?",
                         r"taman inetraktif", r"taman interaksi( sosial)?", r"taman interasi sosial", r"taman cerdas",
                         r"rth publik( aktif)?", r"taman publik", r"ruang terbuka publik", r"taman ramah anak",
                         r"taman bermain kota layak anak", r"public park", r"public square")),
]
# Lolos tetap gugur bila namanya menunjukkan kawasan privat/kampus/ibadah/makam (instansi tidak:
# "Alun-alun Kecamatan X" tetap alun-alun publik).
BUANG_KUAT = BUANG[:4]

# Kandidat yang perlu bukti web: nama berawalan Taman / RTH / Ruang Terbuka / Hutan, atau ber-Park/Garden.
KANDIDAT = re.compile(r"^\s*(taman|tama |taan |tamab |tanam |tamkul|rth|ruang terbuka|ruang interaksi|ruang limpah|hutan|paru)"
                      r"|park|garden|square|plaza|forest|monas", re.I)
TANPA_IDENTITAS = re.compile(r"^\s*(taman|park|rth|ruang terbuka( hijau)?|green area|open space|playground|play ground"
                             r"|small park|taman (kecil|mungil|sederhana|tanpanama|terbuka( hijau)?|hijau|desa|kota"
                             r"|bermain( anak)?|lingkungan|masjid|sari|rt|rw|publik( \d+)?|segitiga)"
                             r"|ruang terbuka publik|rth publik|taman \w)\s*$", re.I)


def hstore(s):
    """other_tags GDAL: "k"=>"v","k2"=>"v2" (cukup untuk tag access/garden:type)."""
    return dict(re.findall(r'"((?:[^"\\]|\\.)*)"=>"((?:[^"\\]|\\.)*)"', s or ""))


def osm_key(p):
    return f"way/{p['osm_way_id']}" if p.get("osm_way_id") else f"osm/{p['osm_id']}"


def klasifikasi(nama, other_tags=None):
    """-> (status, alasan). status: lolos / buang / ragu."""
    nama = (nama or "").strip()
    t = hstore(other_tags)
    if t.get("access") in ("private", "no", "customers", "permit") or t.get("garden:type") in ("residential", "private"):
        return "buang", "akses_privat"
    if not re.search(r"[a-z]{2}", nama, re.I) or TANPA_IDENTITAS.match(nama):
        return "buang", "nama_generik"  # tidak dapat diverifikasi
    for alasan, pola in LOLOS:
        if pola.search(nama):
            for alasan_b, pola_b in BUANG_KUAT:
                if pola_b.search(nama):
                    return "buang", alasan_b
            return "lolos", alasan
    for alasan, pola in BUANG:
        if pola.search(nama):
            return "buang", alasan
    if KANDIDAT.search(nama):
        return "ragu", "perlu_verifikasi"
    return "buang", "nama_bukan_taman"


def baca_geojson():
    with open(os.path.join(CLEAN, "parks_clean.geojson"), encoding="utf-8") as f:
        return json.load(f)


def baca_verifikasi():
    if not os.path.exists(CSV_VERIFIKASI):
        return {}
    with open(CSV_VERIFIKASI, encoding="utf-8", newline="") as f:
        return {r["osm_key"]: r for r in csv.DictReader(f)}


def putuskan(p, verifikasi):
    """Tambahkan status, alasan, validasi, sumber, catatan ke properti p (in place); -> True bila taman kota."""
    status, alasan = klasifikasi(p.get("name"), p.get("other_tags"))
    v = verifikasi.get(osm_key(p))
    if v:
        lolos = v["keputusan"] == "lolos"
        p.update(validasi="web", sumber=v["sumber"] or None, catatan=v["catatan"] or None,
                 alasan=(alasan if status == "lolos" else "terverifikasi_web") if lolos else "ditolak_web")
    else:
        lolos = status == "lolos"
        p.update(validasi="aturan", sumber=None, catatan=None,
                 alasan="tidak_terverifikasi" if status == "ragu" else alasan)
    p["status"] = "lolos" if lolos else "buang"
    return lolos


def proses():
    sumber, verifikasi = baca_geojson(), baca_verifikasi()
    lolos, buang = [], []
    for fitur in sumber["features"]:
        (lolos if putuskan(fitur["properties"], verifikasi) else buang).append(fitur)
    keluaran = {}
    for nama, fs in (("parks_taman_kota", lolos), ("parks_bukan_taman_kota", buang)):
        keluaran[nama] = path = os.path.join(CLEAN, f"{nama}.geojson")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({**sumber, "name": nama, "features": fs}, f, ensure_ascii=False)
    print(f"Taman kota: {len(lolos)} | dibuang: {len(buang)} | total: {len(sumber['features'])}")
    print("Alasan lolos:", dict(collections.Counter(f["properties"]["alasan"] for f in lolos).most_common()))
    print("Alasan dibuang:", dict(collections.Counter(f["properties"]["alasan"] for f in buang).most_common()))
    return keluaran


def jalankan_qgis():
    proj = QgsProject.instance()
    for nama, path in proses().items():
        for lama in proj.mapLayersByName(nama):
            proj.removeMapLayer(lama)
        lyr = QgsVectorLayer(path, nama, "ogr")
        assert lyr.isValid(), path
        proj.addMapLayer(lyr)


def daftar_ragu():
    verifikasi = baca_verifikasi()
    for f in baca_geojson()["features"]:
        p = f["properties"]
        if klasifikasi(p["name"], p.get("other_tags"))[0] != "buang" and osm_key(p) not in verifikasi:
            print(osm_key(p), p["name"], p["city_name"], klasifikasi(p["name"])[0], sep="|")


def selftest():
    kasus = {
        "Alun-Alun Kota Bandung": ("lolos", "alun_alun"),
        "Alun-alun UM": ("buang", "pendidikan"),
        "Alun-Alun Kecamatan Periuk": ("lolos", "alun_alun"),
        "RPTRA Akasia": ("lolos", "rptra"),
        "Hutan Kota Unesa": ("buang", "pendidikan"),
        "Taman Kota Salatiga": ("lolos", "taman_kota"),
        "Taman Lalu Lintas Kota Bekasi": ("lolos", "taman_publik"),
        "Taman Bungkul": ("ragu", "perlu_verifikasi"),
        "Taman Makam Pahlawan Pati": ("buang", "makam"),
        "Kompleks Perumahan Si Pitung": ("buang", "privat_hunian"),
        "Taman Emeralda Citra": ("buang", "privat_hunian"),
        "Taman Magister UGM": ("buang", "pendidikan"),
        "Lapangan Desa Watualang": ("buang", "bukan_ruang_taman"),
        "Lapangan Banteng": ("buang", "lapangan"),
        "Taman Bundaran Peruri": ("buang", "instansi"),
        "Taman": ("buang", "nama_generik"),
        "Taman Kota": ("buang", "nama_generik"),
        "2": ("buang", "nama_generik"),
        "Admerson": ("buang", "nama_bukan_taman"),
        "Taman Suropati": ("ragu", "perlu_verifikasi"),
        "Tebet Eco Park": ("buang", "wisata_berbayar_alam"),
    }
    salah = [(n, klasifikasi(n), h) for n, h in kasus.items() if klasifikasi(n) != h]
    assert not salah, salah
    assert klasifikasi("Taman Bungkul", '"access"=>"private"') == ("buang", "akses_privat")
    assert hstore('"fee"=>"no","access"=>"yes"') == {"fee": "no", "access": "yes"}
    assert osm_key({"osm_way_id": "5", "osm_id": None}) == "way/5" and osm_key({"osm_way_id": None, "osm_id": "7"}) == "osm/7"
    print(f"selftest OK ({len(kasus) + 3} kasus)")


if QgsProject is not None:
    jalankan_qgis()
elif __name__ == "__main__":
    daftar_ragu() if "--ragu" in sys.argv else selftest()
