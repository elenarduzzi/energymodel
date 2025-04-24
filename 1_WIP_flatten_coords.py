# iterates over all .json files in folder, extracts surface data
# flattens 
#  writes to a single CSV (one row per building).

# C:/Users/emily/OneDrive/Documents/2_school/build_tech/Thesis/4_code/my_energy_model/1_lod_1.2_worklow/7B_enriched_perPand_level02_21.2


import os, json, csv, itertools, math

# Paths
INPUT_DIR="C:/Users/emily/OneDrive/Documents/2_school/build_tech/Thesis/4_code/my_energy_model/1_lod_1.2_worklow/7B_enriched_perPand_level02_21.3"
OUTPUT_CSV="0A_flattened_coords_21.3.csv"


# 1) Figure out the maximum # of vertices any surface has (so we can pad columns)
max_verts = 0
for fn in os.listdir(INPUT_DIR):
    if not fn.lower().endswith(".json"): continue
    data = json.load(open(os.path.join(INPUT_DIR, fn), encoding="utf-8"))
    for s in data.get("Surfaces", []):
        max_verts = max(max_verts, len(s.get("Distances", [])))

# 2) Build CSV header
base_cols = [
    "Pand ID","Archetype ID","Construction Year",
    "Floor Area","Number of Floors","Wall Area",
    "Roof Area (Flat)","Roof Area (Sloped)","Shared Wall Area",
    "Absolute Height (70%)","Annual Heating","Annual Cooling",
    "Surface Index","Surface Type","Centroid X","Centroid Y"
]
# distance columns d1, d2, …, dN
dist_cols = [f"d{i+1}" for i in range(max_verts)]
# unit‐vector columns ux1, uy1, ux2, uy2, …
uv_cols   = list(itertools.chain.from_iterable((f"ux{i+1}", f"uy{i+1}") for i in range(max_verts)))
header = base_cols + dist_cols + uv_cols

# 3) Write out the CSV
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as outf:
    w = csv.writer(outf)
    w.writerow(header)

    for fn in os.listdir(INPUT_DIR):
        if not fn.lower().endswith(".json"): continue
        b = json.load(open(os.path.join(INPUT_DIR, fn), encoding="utf-8"))

        # top‐level metadata & simulation results
        sim = b.get("simulation_results", {})
        meta = [
            b.get("Pand ID"),
            b.get("Archetype ID"),
            b.get("Construction Year"),
            b.get("Floor Area"),
            b.get("Number of Floors"),
            b.get("Wall Area"),
            b.get("Roof Area (Flat)"),
            b.get("Roof Area (Sloped)"),
            b.get("Shared Wall Area"),
            b.get("Absolute Height (70%)"),
            sim.get("Annual Heating [kWh/m2]"),
            sim.get("Annual Cooling [kWh/m2]")
        ]

        for idx, s in enumerate(b.get("Surfaces", [])):
            cent = s.get("Centroid", {})
            dists = s.get("Distances", [])
            uv    = s.get("UnitPairs", [])

            row = (
                meta +
                [idx, s.get("Type"), cent.get("x"), cent.get("y")] +
                dists + [""]*(max_verts - len(dists)) +
                list(itertools.chain.from_iterable(uv)) +
                [""]*((max_verts - len(uv)) * 2)
            )
            w.writerow(row)

print(f"written {OUTPUT_CSV}")

