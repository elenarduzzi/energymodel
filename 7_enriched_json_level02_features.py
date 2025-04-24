# write a new json file with level 01 input features, surface vertices, 
# reads .eso file, output heating and cooling demands per floor area. 

import os
import json

# files
input_json_folder = '2_pand_surfaces_level02_21.3'
input_energy = '6A_energy_outputs_per_area_21.3.json'
output_folder = '7B_enriched_perPand_level02_21.3'

os.makedirs(output_folder, exist_ok=True)

# 1) Load energy consumption data from the JSON
with open(input_energy, 'r') as energy_file:
    energy_data = json.load(energy_file)

# 2) Build a lookup dict for energy data by Pand number (e.g., "0599100000013220")
energy_lookup = {}
for bldg in energy_data['buildings']:
    # This might be "Pand.0599100000013220" or "0599100000013220"
    pand_num = bldg['Pand ID'].replace('Pand.', '')
    energy_lookup[pand_num] = bldg

# 3) Iterate over geometry JSONs, merging with the existing energy data
for geo_filename in os.listdir(input_json_folder):
    if not geo_filename.endswith('.json'):
        continue  # skip non-JSON files

    geo_path = os.path.join(input_json_folder, geo_filename)
    with open(geo_path, 'r') as geo_file:
        geo_data = json.load(geo_file)
        
    # geo_data keys are like "NL.IMBAG.Pand.0599100000013220"
    for pand_key, building_info in geo_data.items():
        # extract just the pand number ("0599100000013220")
        pand_num = pand_key.split('.')[-1]

        if pand_num not in energy_lookup:
            print(f"No energy data for {pand_key}; skipping.")
            continue

        # Get the precomputed heating/cooling from the lookup
        energy_rec = energy_lookup[pand_num]

        # combine geometry + energy
        enriched = {
            'Pand ID': pand_num,
            'Archetype ID': building_info.get("Archetype ID"),
            'Construction Year': building_info.get("Construction Year"),
            'Number of Floors': building_info.get('Number of Floors', 1.0),
            'Wall Area': building_info.get("Wall Area"),
            'Roof Area (Flat)': building_info.get("Roof Area (Flat)"),
            'Roof Area (Sloped)': building_info.get("Roof Area (Sloped)"),
            'Floor Area': building_info.get('Floor Area', 0.0),
            'Shared Wall Area': building_info.get('Shared Wall Area', 0.0),
            'Absolute Height (70%)': building_info.get("Absolute Height (70%)"),
            'simulation_results': {
                'Annual Heating [kWh/m2]': energy_rec.get('Annual Heating [kWh/m2]'),
                'Annual Cooling [kWh/m2]': energy_rec.get('Annual Cooling [kWh/m2]')
            },
            'Surfaces': building_info.get('Surfaces', [])
        }

        # outputs
        out_name = f"{pand_num}.json"
        out_path = os.path.join(output_folder, out_name)
        with open(out_path, 'w') as outfile:
            json.dump(enriched, outfile, indent=4)

        print(f"Created enriched JSON for {pand_num} -> {out_path}")

print("Done creating enriched JSONs.")
