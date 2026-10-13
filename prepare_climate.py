"""
Build country x month climate data from WorldClim historical monthly weather (CRU-TS 4.09).

Downloads WorldClim 2.1 monthly tmin, tmax and precipitation (10 arc-minute) for 2005-2024
and Natural Earth country borders, then computes an area-weighted mean for each country and month.

Output (small, used by script.ipynb):
    data/climate_country_month.csv   columns: iso3, year, month, tmin, tmax, prec
    data/wahis_country_iso3.csv      WAHIS country name -> ISO3 code

Usage:
    python prepare_climate.py             # downloads ~1.2 GB, deletes raw files when done
    python prepare_climate.py --keep-raw  # keep the downloaded zips in data/raw/

Source: Fick & Hijmans (2017) WorldClim 2; Harris et al. (2020) CRU TS. https://www.worldclim.org/data/monthlywth.html
"""
import argparse
import logging
import urllib.request
import zipfile
from pathlib import Path

import country_converter as coco
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize

YEARS = range(2005, 2025)
VARIABLES = ["tmin", "tmax", "prec"]
PERIODS = ["2000-2009", "2010-2019", "2020-2024"]
WORLDCLIM_URL = "https://geodata.ucdavis.edu/climate/worldclim/2_1/hist/cts4.09/wc2.1_cruts4.09_10m_{var}_{period}.zip"
BORDERS_URL = "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip"

# WAHIS names that country_converter can't resolve
MANUAL_ISO3 = {
    "Central African (Rep.)": "CAF",
    "Congo (Rep. of the)": "COG",
    "Ceuta": "ESP",
    "Melilla": "ESP",
    "Serbia and Montenegro": "SRB",
}

DATA = Path("data")
RAW = DATA / "raw"


def download(url, dest):
    if dest.exists():
        return dest
    print(f"  downloading {dest.name} ...", flush=True)
    tmp = dest.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dest)
    return dest


def wahis_country_codes():
    logging.getLogger("country_converter").setLevel(logging.ERROR)
    names = pd.read_csv("WAHIS_data.csv", usecols=["Country"])["Country"].drop_duplicates().sort_values()
    iso3 = coco.convert(names.tolist(), to="ISO3", not_found=None)
    codes = pd.DataFrame({"Country": names.values, "iso3": iso3})
    codes["iso3"] = codes["Country"].map(MANUAL_ISO3).fillna(codes["iso3"])
    return codes


def country_grid(template_tif):
    """Rasterise country borders onto the WorldClim grid. Returns (grid of country ids, list of iso3)."""
    borders = gpd.read_file(f"zip://{download(BORDERS_URL, RAW / 'ne_10m_admin_0_countries.zip')}")
    # Natural Earth uses -99 for a few ISO codes (e.g. France, Norway); fall back to the ADM0 code
    borders["iso3"] = borders["ISO_A3"].where(borders["ISO_A3"] != "-99", borders["ADM0_A3"])
    borders = borders.dissolve("iso3").reset_index()
    codes = borders["iso3"].tolist()

    with rasterio.open(template_tif) as src:
        shape, transform = src.shape, src.transform
    shapes = [(geom, i + 1) for i, geom in enumerate(borders.geometry)]
    grid = rasterize(shapes, out_shape=shape, transform=transform, fill=0, dtype="int32")

    # Small islands may cover no cell centre; give them any cell they touch that is still empty
    missing = set(range(1, len(codes) + 1)) - set(np.unique(grid))
    if missing:
        touched = rasterize([s for s in shapes if s[1] in missing], out_shape=shape,
                            transform=transform, fill=0, all_touched=True, dtype="int32")
        grid = np.where((grid == 0) & (touched > 0), touched, grid)

    # Cell area shrinks with latitude
    rows = np.arange(shape[0])
    lat = transform.f + (rows + 0.5) * transform.e
    weights = np.repeat(np.cos(np.deg2rad(lat))[:, None], shape[1], axis=1)
    return grid, weights, codes


def country_means(arr, nodata, grid, weights, n):
    valid = (grid > 0) & np.isfinite(arr) & (arr != nodata)
    ids, w = grid[valid], weights[valid]
    total = np.bincount(ids, weights=w * arr[valid], minlength=n + 1)
    wsum = np.bincount(ids, weights=w, minlength=n + 1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return total / wsum


def main(keep_raw):
    RAW.mkdir(parents=True, exist_ok=True)
    codes = wahis_country_codes()
    codes.to_csv(DATA / "wahis_country_iso3.csv", index=False)
    print(f"Mapped {codes['iso3'].notna().sum()} of {len(codes)} WAHIS countries to ISO3")

    records, grid = [], None
    for var in VARIABLES:
        for period in PERIODS:
            zpath = download(WORLDCLIM_URL.format(var=var, period=period), RAW / f"wc2.1_cruts4.09_10m_{var}_{period}.zip")
            with zipfile.ZipFile(zpath) as z:
                tifs = sorted(n for n in z.namelist() if n.endswith(".tif"))
            print(f"  {var} {period}: {len(tifs)} monthly rasters", flush=True)
            for name in tifs:
                year, month = map(int, Path(name).stem.split("_")[-1].split("-"))
                if year not in YEARS:
                    continue
                path = f"zip://{zpath}!{name}"
                if grid is None:
                    grid, weights, iso_list = country_grid(path)
                with rasterio.open(path) as src:
                    arr = src.read(1).astype("float64")
                    nodata = src.nodata
                means = country_means(arr, nodata, grid, weights, len(iso_list))
                for i, iso in enumerate(iso_list, start=1):
                    if np.isfinite(means[i]):
                        records.append((iso, year, month, var, means[i]))
            if not keep_raw:
                zpath.unlink()

    climate = (pd.DataFrame(records, columns=["iso3", "year", "month", "var", "value"])
               .pivot_table(index=["iso3", "year", "month"], columns="var", values="value")
               .reset_index())
    climate.columns.name = None
    climate.to_csv(DATA / "climate_country_month.csv", index=False)
    covered = set(climate["iso3"])
    no_climate = codes[~codes["iso3"].isin(covered)]["Country"].tolist()
    print(f"Saved {len(climate):,} country-months for {len(covered)} countries")
    print(f"WAHIS countries with no climate cells: {no_climate}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep-raw", action="store_true", help="keep downloaded zip files in data/raw/")
    main(parser.parse_args().keep_raw)
