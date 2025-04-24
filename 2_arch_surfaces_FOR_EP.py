# assigns surface types from defined ruleset
# ground floor = minimum of all z cooridnates, roof = maximum all z coordinates, else = wall
# inputs jsons from folder, loops individual jsons files, outputs jsons in folder
# assigns surface types from defined ruleset
# ground floor = minimum of all z cooridnates, roof = maximum all z coordinates, else = wall
# inputs jsons from folder, loops individual jsons files, outputs jsons in folder

import json
import os

# file paths
input_dir = "1B_pand_jsons_21"
output_dir = "2B_pand_surfaces_21_EPLUS"

os.makedirs(output_dir, exist_ok=True)

def load_json(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def extract_vertices_and_boundaries(data):
    global_vertices = data["metadata"]["vertices"]

    if "buildings" in data:
        for building in data["buildings"]:
            if all(k in building for k in ["Pand ID", "Boundaries (LoD 1.2)", "Archetype ID"]):
                pand_id = building["Pand ID"]
                archetype_id = building["Archetype ID"]

                num_floors = building.get("Number of Floors")
                wall_area = building.get("Wall Area")
                roof_area_flat = building.get("Roof Area (Flat)")
                roof_area_sloped = building.get("Roof Area (Sloped)")
                floor_area = building.get("Floor Area")
                shared_wall_area = building.get("Shared Wall Area")
                construction_year = building.get("Construction Year")

                lod_data = building.get("LoD 1.2 Data", {})
                building_height_70 = lod_data.get("Building Height (70%)")
                ground_elev = building.get("Ground Elevation (NAP)")

                abs_height_70 = None
                if building_height_70 is not None and ground_elev is not None:
                    abs_height_70 = abs(building_height_70 - ground_elev)

                boundaries = building["Boundaries (LoD 1.2)"]

                mapped_boundaries = []
                for boundary_group in boundaries:
                    for surface in boundary_group:
                        for ring_group in surface:
                            for ring in ring_group:
                                coords = [global_vertices[idx] for idx in ring]
                                mapped_boundaries.append({
                                    "Coordinates": [coords]
                                })

                return {
                    "Pand ID": pand_id,
                    "Archetype ID": archetype_id,
                    "Construction Year": construction_year, 
                    "Number of Floors": num_floors,
                    "Wall Area": wall_area,
                    "Roof Area (Flat)": roof_area_flat,
                    "Roof Area (Sloped)": roof_area_sloped,
                    "Floor Area": floor_area,
                    "Shared Wall Area": shared_wall_area,
                    "Absolute Height (70%)": abs_height_70,
                    "Surfaces": mapped_boundaries
                }
    return {}

def classify_surfaces(building):
    surfaces = building["Surfaces"]
    all_z_values = [z for surface in surfaces for coords_list in surface["Coordinates"] for _, _, z in coords_list]
    min_z = min(all_z_values)
    max_z = max(all_z_values)

    for surface in surfaces:
        z_values = [z for coords_list in surface["Coordinates"] for _, _, z in coords_list]
        if all(z == min_z for z in z_values):
            surface_type = "G"
        elif all(z == max_z for z in z_values):
            surface_type = "R"
        else:
            surface_type = "F"
        surface["Type"] = surface_type

def write_json(data, output_file):
    with open(output_file, 'w') as file:
        json.dump(data, file, indent=4)

# Process each file in the folder
for filename in os.listdir(input_dir):
    if filename.endswith(".json"):
        input_path = os.path.join(input_dir, filename)
        output_path = os.path.join(output_dir, filename)

        data = load_json(input_path)
        building_data = extract_vertices_and_boundaries(data)
        if building_data:
            classify_surfaces(building_data)
            write_json(building_data, output_path)
            print(f"saved: {filename}")
