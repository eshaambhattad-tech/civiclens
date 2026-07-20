"""Load unit boundaries into `units`.

Real data: Census TIGER/Line 2024 shapefiles —
  County Subdivisions (townships): tl_2024_17_cousub.zip
  Incorporated Places (municipalities): tl_2024_17_place.zip
Clip to Cook County (COUNTYFP 031) happens here for cousub; places are
intersected against the Cook boundary.

Fixture mode (no shapefiles yet): --fixtures loads ingest/fixtures/units.geojson.
"""
import argparse
import datetime as dt
import json
import os
import re

import geopandas as gpd

from db import apply_schema, connect

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "units.geojson")


def slugify(name, prefix="cook"):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{prefix}-{s}"


def upsert_unit(conn, row):
    conn.execute(
        """
        insert into units (id, name, type, county, geom, as_of)
        values (%(id)s, %(name)s, %(type)s, 'Cook',
                ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)), %(as_of)s)
        on conflict (id) do update set
          name = excluded.name, type = excluded.type,
          geom = excluded.geom, as_of = excluded.as_of
        """,
        row,
    )


def load_gdf(conn, gdf, unit_type, name_col, suffix=""):
    today = dt.date.today()
    n = 0
    for _, r in gdf.iterrows():
        name = r[name_col] + suffix
        geom = r.geometry
        if geom.geom_type == "Polygon":
            geom = gpd.GeoSeries([geom]).union_all()
        upsert_unit(conn, {
            "id": slugify(name),
            "name": name,
            "type": unit_type,
            "geom": json.dumps(geom.__geo_interface__),
            "as_of": today,
        })
        n += 1
    return n


def load_tiger(conn, cousub_path=None, place_path=None):
    total = 0
    cook = None
    if cousub_path:
        gdf = gpd.read_file(cousub_path).to_crs(4326)
        gdf = gdf[gdf["COUNTYFP"] == "031"]
        gdf = gdf[~gdf["NAME"].str.contains("not defined", case=False)]
        cook = gdf.union_all()
        total += load_gdf(conn, gdf, "township", "NAME", suffix=" Township")
        # county row: union of all townships
        upsert_unit(conn, {
            "id": "cook-county",
            "name": "Cook County",
            "type": "county",
            "geom": json.dumps(gpd.GeoSeries([cook]).union_all().__geo_interface__),
            "as_of": dt.date.today(),
        })
        total += 1
    if place_path:
        gdf = gpd.read_file(place_path).to_crs(4326)
        if cook is not None:
            gdf = gdf[gdf.geometry.intersects(cook)]
        total += load_gdf(conn, gdf, "municipality", "NAME")
    return total


def load_fixtures(conn):
    with open(FIXTURES) as f:
        fc = json.load(f)
    today = dt.date.today()
    for feat in fc["features"]:
        p = feat["properties"]
        upsert_unit(conn, {
            "id": p["id"],
            "name": p["name"],
            "type": p["type"],
            "geom": json.dumps(feat["geometry"]),
            "as_of": today,
        })
        if p.get("population"):
            conn.execute("update units set population=%s where id=%s", (p["population"], p["id"]))
    return len(fc["features"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true")
    ap.add_argument("--cousub", help="path to tl_2024_17_cousub shapefile/zip")
    ap.add_argument("--place", help="path to tl_2024_17_place shapefile/zip")
    args = ap.parse_args()

    conn = connect()
    apply_schema(conn)
    if args.fixtures:
        n = load_fixtures(conn)
    else:
        n = load_tiger(conn, args.cousub, args.place)
    conn.commit()
    print(f"loaded {n} units")
