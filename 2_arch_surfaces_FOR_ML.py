# assigns surface types from defined ruleset
# ground floor = minimum of all z cooridnates, roof = maximum all z coordinates, else = wall
# inputs jsons from folder, loops individual jsons files, outputs jsons in folder

# takes level 01 features from 3dbag json: 

# "Number of Floors":
# "Wall Area": 
# "Roof Area (Flat)": 
# Roof Area (Sloped)":
# "Floor Area":
# "Shared Wall Area": 
# "Building Height (70%)" ** takes absolute value, considering ground elevation

# level 02 includes vertex data
# defines centroid for each surface, represents vertice list as distance and angle, as circle unit pair, from centroid to vertex.


from __future__ import annotations
import json, math, os, pathlib
from typing import List, Tuple, Dict, Any

# ADJUST INPUT / OUTPUT DIRECTORY PER ARCHETYPE 

INPUT_DIR  = pathlib.Path("1B_pand_jsons_6")
OUTPUT_DIR = pathlib.Path("2A_pand_surfaces_6_ML")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── helpers ───────────────────────────────────────────────────────────
def centroid_xy(verts: List[Tuple[float, float, float]]) -> Tuple[float, float]:
    cx = sum(v[0] for v in verts) / len(verts)
    cy = sum(v[1] for v in verts) / len(verts)
    return cx, cy

def order_ccw(verts: List[Tuple[float, float, float]]) -> List[Tuple[float, float, float]]:
    cx, cy = centroid_xy(verts)
    return sorted(verts, key=lambda v: math.atan2(v[1] - cy, v[0] - cx))

def dist_pair(c: Tuple[float, float], v: Tuple[float, float, float]) -> Tuple[float, List[float]]:
    dx, dy = v[0] - c[0], v[1] - c[1]
    d = math.hypot(dx, dy)
    return (d, [0.0, 0.0]) if d == 0 else (d, [dx / d, dy / d])

def surface_to_cu(ring: List[Tuple[float, float, float]], s_type: str) -> Dict[str, Any]:
    cx, cy = centroid_xy(ring)
    ring   = order_ccw(ring)
    dists, pairs = zip(*(dist_pair((cx, cy), v) for v in ring))
    return {
        "Type": s_type,
        "Centroid": {"x": cx, "y": cy},
        "Distances": list(dists),
        "UnitPairs": list(pairs)
    }

def decode_vertices(raw: List[List[int | float]],
                    scale: List[float],
                    trans: List[float]) -> List[Tuple[float, float, float]]:
    sx, sy, sz = scale
    tx, ty, tz = trans
    return [(x * sx + tx, y * sy + ty, z * sz + tz) for x, y, z in raw]

# ── main  ─────────────────────────────────────────────────────────────
for in_path in INPUT_DIR.glob("*.json"):
    geo   = json.loads(in_path.read_text())
    meta  = geo["metadata"]

    verts   = decode_vertices(meta["vertices"],
                              meta["transform"]["scale"],
                              meta["transform"]["translate"])

    z_vals  = [v[2] for v in verts]
    zmin, zmax = min(z_vals), max(z_vals)

    # ─── collect rings ───────────────────────────────────────────────
    ground = [v for v in verts if v[2] == zmin]
    roof   = [v for v in verts if v[2] == zmax]
    mid    = [v for v in verts if zmin < v[2] < zmax]    # ← NEW  (façades)

    surfaces_cu: List[Dict[str, Any]] = []
    if ground:
        surfaces_cu.append(surface_to_cu(ground, "G"))
    if mid:                                              # -----------------
        # build a single façade ring from all mid‑level vertices;
        #   remove duplicates, make sure we have ≥ 3 points
        uniq_mid = {(x, y): (x, y, z) for x, y, z in mid}.values()
        if len(uniq_mid) >= 3:
            surfaces_cu.append(surface_to_cu(list(uniq_mid), "F"))
    if roof:
        surfaces_cu.append(surface_to_cu(roof, "R"))
    # ------------------------------------------------------------------

    b   = geo["buildings"][0]            # one building per file
    pid = b["Pand ID"]

    out = {
        "Pand ID": pid,
        "Archetype ID": b.get("Archetype ID"),
        "Construction Year": b.get("Construction Year"),
        "Number of Floors": b.get("Number of Floors"),
        "Wall Area": b.get("Wall Area"),
        "Roof Area (Flat)": b.get("Roof Area (Flat)"),
        "Roof Area (Sloped)": b.get("Roof Area (Sloped)"),
        "Floor Area": b.get("Floor Area"),
        "Shared Wall Area": b.get("Shared Wall Area"),
        "Absolute Height (70%)": b["LoD 1.2 Data"].get("Building Height (70%)"),
        "Surfaces": surfaces_cu
    }

    out_path = OUTPUT_DIR / in_path.name
    out_path.write_text(json.dumps(out, indent=4))
    print(f"{pid}  →  {out_path.relative_to(OUTPUT_DIR.parent)}")
