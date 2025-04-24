# assigns surface types from defined ruleset
# ground floor = minimum of all z cooridnates, roof = maximum all z coordinates, else = wall
# inputs jsons from folder, loops individual jsons files, outputs jsons in folder

# takes level 1 features from 3dbag json: 

# "Number of Floors":
# "Wall Area": 
# "Roof Area (Flat)": 
# Roof Area (Sloped)":
# "Floor Area":
# "Shared Wall Area": 
# "Building Height (70%)" ** takes absolute value, considering ground elevation

# write surface x,y,z coordinates and surface types 

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
    buildings = {}
    if "buildings" in data:
        for building in data["buildings"]:
            if all(k in building for k in ["Pand ID", "Vertices", "Boundaries (LoD 1.2)", "Archetype ID"]):
                pand_id = building["Pand ID"]
                archetype_id = building["Archetype ID"]

                num_floors = building.get("Number of Floors")
                wall_area = building.get("Wall Area")
                roof_area_flat = building.get("Roof Area (Flat)")
                roof_area_sloped = building.get("Roof Area (Sloped)")
                floor_area = building.get("Floor Area")
                shared_wall_area = building.get("Shared Wall Area")

                # Retrieve Construction Year
                construction_year = building.get("Construction Year")

                # Retrieve LoD 1.2 data
                lod_data = building.get("LoD 1.2 Data", {})
                building_height_70 = lod_data.get("Building Height (70%)")

                # Attempt to retrieve ground elevation
                ground_elev = building.get("Ground Elevation (NAP)")  # 'b3_h_maaiveld'

                # Compute Absolute Height (70%) if both values exist
                abs_height_70 = None
                if building_height_70 is not None and ground_elev is not None:
                    abs_height_70 = building_height_70 - ground_elev
                    # ensure it is non-negative
                    if abs_height_70 < 0:
                        abs_height_70 = -abs_height_70

                vertices = building["Vertices"]
                boundaries = building["Boundaries (LoD 1.2)"]

                mapped_boundaries = []
                for boundary_group in boundaries:
                    for boundary in boundary_group:
                        mapped_boundaries.append({
                            "Coordinates": [[vertices[idx] for idx in sublist] for sublist in boundary]
                        })

                buildings[pand_id] = {
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
    return buildings



def classify_surfaces(buildings):
    for pand_data in buildings.values():
        surfaces = pand_data["Surfaces"]
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
        buildings = extract_vertices_and_boundaries(data)
        classify_surfaces(buildings)
        write_json(buildings, output_path)
        print(f"saved: {filename}")
