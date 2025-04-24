"""
Create EnergyPlus IDF files (and optionally run a simulation) for 40 000 +
3DBAG LoD 1.2 buildings **in parallel**.

* Reads surface JSONs from `INPUT_DIR`
* Writes each IDF either (a) to `OUTPUT_DIR` **or**
  (b) directly to S3 (`S3_BUCKET / OUTPUT_PREFIX/<pand_id>.idf`)
* One CPU‑core, one worker; each worker holds the base‑IDF template
  and material library in memory.
"""
from __future__ import annotations

import json, os, pathlib, sys, traceback
from io import StringIO
from typing import Dict, List, Tuple

import boto3
from concurrent.futures import ProcessPoolExecutor, as_completed

from eppy.modeleditor import IDF   # type: ignore

import re

# ───────────────────────── configuration ──────────────────────────
IDD_PATH       = r"C:/EnergyPlusV24-2-0/Energy+.idd"
BASE_IDF_PATH  = "4A_rotterdam_simple.idf"
MATERIAL_LIB   = "3B_materials_for_idf.json"

INPUT_DIR      = pathlib.Path("2A_pand_surfaces_21")
OUTPUT_DIR     = pathlib.Path("4B_pand_idfs_21")   # only used if S3_BUCKET==""

S3_BUCKET      = ""             # e.g. "my‑energyplus‑idf"
OUTPUT_PREFIX  = "idf"          # folder inside the bucket
RUN_EPLUS      = False          # set True to launch EnergyPlus in each worker

ENERGYPLUS_EXE = r"C:/EnergyPlusV24-2-0/energyplus.exe"
WEATHER_FILE   = r"4A_NLD_ZH_Rotterdam.The.Hague.AP.063440_TMYx.2009-2023.epw"

# ──────────────────────────────────────────────────────────────────


# ––––– everything below this line runs in *each* worker –––––
_base_idf_str: str = ""          # populated by init_worker()
_material_defs: Dict[str, Dict] = {}
S3 = boto3.client("s3") if S3_BUCKET else None


def init_worker() -> None:
    """Executed once per worker process – preload big, read‑only assets."""
    global _base_idf_str, _material_defs
    IDF.setiddname(IDD_PATH)

    with open(BASE_IDF_PATH, "r") as fh:
        _base_idf_str = fh.read()

    with open(MATERIAL_LIB, "r") as fh:
        _material_defs = json.load(fh)


def make_vertices(coords: List[List[float]]) -> List[Tuple[float, float, float]]:
    """→ list[(x,y,z)] in *metres* instead of millimetres."""
    return [(x / 1000, y / 1000, z / 1000) for x, y, z in coords]




PAND_REGEX = re.compile(r"^\d{16}$")  # or tweak to match your IDs

def handle_json(json_path: str) -> Tuple[str, str|None]:
    """
    Read a file that must describe exactly one building.
    - build the IDF in memory
    - write to S3 if S3_BUCKET is set, else write locally under OUTPUT_DIR
    Returns (pand_id, error_str).  error_str is None on success.
    """
    try:
        raw = json.load(open(json_path))

        # --- identify your single entry & pid ---
        if isinstance(raw, dict) and "Pand ID" in raw and "Surfaces" in raw:
            entry, pid = raw, raw["Pand ID"]
        elif isinstance(raw, dict) and len(raw)==1 and PAND_REGEX.match(next(iter(raw))):
            pid, entry = next(iter(raw.items()))
        else:
            for k,v in raw.items():
                if PAND_REGEX.match(k) and isinstance(v, dict) and "Surfaces" in v:
                    pid, entry = k, v
                    break
            else:
                raise KeyError(f"no Pand‑ID entry found in {json_path!r}")

        # --- extract archetype + surfaces + materials defs ---
        arche     = entry["Archetype ID"]
        surfaces  = entry.get("Surfaces", [])
        materials = _material_defs.get(arche, {}).get("Materials", [])

        # --- build a fresh IDF from the base template ---
        idf = IDF(StringIO(_base_idf_str))

        # add schedules, ground temps
        _add_support_objects(idf)

        # add material & construction objects
        _add_materials_and_constructions(idf, arche, materials)

        # building & zone
        bldg_name = f"Pand.{pid}"
        zone_name = f"Zone_{pid}"
        _add_zone_objects(idf, bldg_name, zone_name, arche)

        # surfaces
        for idx, surf in enumerate(surfaces):
            add_surface(idf, surf, zone_name, idx)

        # my outputs (if any)
        idf.newidfobject("OUTPUT:VARIABLE", Key_Value="*", 
            Variable_Name="Zone Ideal Loads Supply Air Total Heating Energy",
            Reporting_Frequency="Hourly")
        idf.newidfobject("OUTPUT:VARIABLE", Key_Value="*", 
            Variable_Name="Zone Ideal Loads Supply Air Total Cooling Energy",
            Reporting_Frequency="Hourly")

        # --- write it out ---
        filename = f"{bldg_name}.idf"
        if S3_BUCKET:
            body = idf.toidf().encode("utf-8")
            S3.put_object(
                Bucket=S3_BUCKET,
                Key=f"{OUTPUT_PREFIX}/{filename}",
                Body=body
            )
        else:
            OUTPUT_DIR.mkdir(exist_ok=True)
            path = OUTPUT_DIR / filename
            path.write_text(idf.toidf(), encoding="utf-8")

        return pid, None

    except Exception as e:
        who = locals().get("pid", os.path.basename(json_path))
        return who, traceback.format_exc()


def _add_zone_objects(idf: IDF, bldg_name: str, zone_name: str, arche: str) -> None:
    idf.newidfobject(
        "BUILDING",
        Name=bldg_name,
        Terrain="City",
        Solar_Distribution="FullExterior",
    )
    idf.newidfobject("ZONE", Name=zone_name)
    idf.newidfobject("HVACTEMPLATE:ZONE:IDEALLOADSAIRSYSTEM", Zone_Name=zone_name)
    idf.newidfobject("SCHEDULE:COMPACT",
        Name="AlwaysOn", Schedule_Type_Limits_Name="Fraction",
        Field_1="Through: 12/31", Field_2="For: AllDays",
        Field_3="Until: 24:00", Field_4="1.0",
    )
    infil = _material_defs.get(arche, {}).get("Infiltration", 0)
    idf.newidfobject(
        "ZONEINFILTRATION:DESIGNFLOWRATE",
        Name=f"Infil_{zone_name}",
        Zone_or_ZoneList_or_Space_or_SpaceList_Name=zone_name,
        Schedule_Name="AlwaysOn",
        Design_Flow_Rate_Calculation_Method="Flow/Area",
        Flow_Rate_per_Floor_Area=infil,
    )


def add_surface(idf: IDF, s: Dict, zone: str, idx: int) -> None:
    st = s["Type"]
    if st not in ("G", "F", "R"):
        return
    coords = make_vertices(s["Coordinates"][0])
    names = {"G": "Floor", "F": "Wall", "R": "Roof"}
    bc    = {"G": "Ground", "F": "Outdoors", "R": "Outdoors"}

    obj = idf.newidfobject(
        "BUILDINGSURFACE:DETAILED",
        Name=f"{st}_{idx}",
        Surface_Type=names[st],
        Construction_Name=f"C_{st}",
        Zone_Name=zone,
        Outside_Boundary_Condition=bc[st],
        Number_of_Vertices=len(coords),
        Sun_Exposure="SunExposed",
        Wind_Exposure="WindExposed",
    )
    for i, (x, y, z) in enumerate(coords, 1):
        obj[f"Vertex_{i}_Xcoordinate"] = x
        obj[f"Vertex_{i}_Ycoordinate"] = y
        obj[f"Vertex_{i}_Zcoordinate"] = z


# ––––– main –––––
def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    files = list(INPUT_DIR.glob("*.json"))
    if not files:
        print("No JSON files found – check INPUT_DIR")
        sys.exit(1)

    failed: List[Tuple[str, str]] = []
    with ProcessPoolExecutor(initializer=init_worker) as exe:
        futures = {exe.submit(handle_json, str(p)): p for p in files}
        for fut in as_completed(futures):
            pid, err = fut.result()
            if err:
                failed.append((pid, err))

    if failed:
        print("Some Pand IDs failed:")
        for pid, err in failed:
            print(f"- {pid}: {err.splitlines()[-1]}")
    else:
        print("All IDFs created successfully")
