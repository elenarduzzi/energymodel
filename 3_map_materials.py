# map materials, infiltrations, window objects for each archetype id
# convert excel to json 

import pandas as pd
import json

# files 

excel_path = "00_map_materials.xlsx"
json_output_path = "00_mapped_materials_for_idf.json"

# column names drop empty rows
df = pd.read_excel(excel_path, sheet_name="materials")
df.columns = [str(col).strip().replace('\n', ' ') for col in df.columns]
df = df.dropna(how='all')
df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)

# format json
structured_data = {}

for _, row in df.iterrows():
    archetype_id = row.get("Archetype ID", "Unknown")
    infiltration = row.get("Infiltration")
    material_id = row.get("Material ID")
    window_id = row.get("Window ID")

    if archetype_id not in structured_data:
        structured_data[archetype_id] = {
            "Infiltration": infiltration if pd.notna(infiltration) else None,
            "Materials": []
        }

    
    if pd.notna(infiltration):
        structured_data[archetype_id]["Infiltration"] = infiltration

    # Add material
    if pd.notna(material_id):
        material_data = {
            "Material ID": material_id,
            "Roughness": row.get("Roughness"),
            "Thickness": row.get("Thickness"),
            "Conductivity": row.get("Conductivity"),
            "Density": row.get("Density"),
            "Specific Heat Capacity": row.get("Specific Heat Capacity")
        }
        structured_data[archetype_id]["Materials"].append(material_data)

    # Add window
    elif pd.notna(window_id):
        window_data = {
            "Window ID": window_id,
            "U_Factor": row.get("U_Factor"),
            "SHGC": row.get("SHGC")
        }
        structured_data[archetype_id]["Materials"].append(window_data)

# Save to JSON
with open(json_output_path, "w") as f:
    json.dump(structured_data, f, indent=2)

print(f"JSON written to {json_output_path}")
