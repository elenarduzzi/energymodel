# parse all .eso files, obtain annual heating and cooling demands
# output heating and cooling demands per floor area. 
# write a new json file with output heating and cooling demands per foor area. 1 json for all pand ids. 

import json
import os
import glob


# files

# base_directory = "5B_EP_sims_seq_21.1"
# geometry_folder = "2_pand_surfaces_21.1"   
# output_file = "6A_energy_outputs_21.1_per_area.json"

# base_directory = "5B_EP_sims_seq_21.2"
# geometry_folder = "2_pand_surfaces_21.2"   
# output_file = "6A_energy_outputs_21.2_per_area.json"


# base_directory = "5B_EP_sims_seq_21.3"
# geometry_folder = "2_pand_surfaces_21.3"   
# output_file = "6A_energy_outputs_21.3_per_area.json"


# files

base_directory = "5B_EP_sims_seq_21.2"
geometry_folder = "2_pand_surfaces_21.2"   
output_file = "6A_energy_outputs_21.2_per_area.json"



def load_geometry_data_from_folder(folder_path):
    """
    Read each .json in `folder_path`. Each file is named like '0599100000013220.json'.
    Inside, we assume there's a dict with key 'NL.IMBAG.Pand.<pand_num>', e.g.:
    {
      "NL.IMBAG.Pand.0599100000013220": {
          "Archetype ID": "D.1965",
          "Floor Area": 175.5,
          "Number of Floors": 1,
          "Surfaces": [...]
      }
    }
    We parse out Floor Area, Number of Floors, etc., then store them in a dict:
        geometry_lookup[pand_num] = total_floor_area
    """
    geometry_lookup = {}

    for file_name in os.listdir(folder_path):
        if not file_name.endswith('.json'):
            continue
        
        # pand_num is the file name without '.json'
        pand_num = os.path.splitext(file_name)[0]  # e.g. '0599100000013220'

        file_path = os.path.join(folder_path, file_name)
        with open(file_path, 'r') as f:
            geo_data = json.load(f)

        # Usually the top-level key is something like 'NL.IMBAG.Pand.0599100000013220'
        # We find it and parse the content
        # If there's only one key in the file, we can do:
        if len(geo_data) != 1:
            print(f"Warning: geometry file {file_name} has multiple or no keys. Skipping.")
            continue
        
        pand_key = list(geo_data.keys())[0]
        building_info = geo_data[pand_key]

        # Safely parse floor area and # floors
        floor_area = building_info.get('Floor Area', 0.0) or 0.0
        num_floors = building_info.get('Number of Floors', 1.0) or 1.0

        total_floor_area = floor_area * num_floors
        geometry_lookup[pand_num] = total_floor_area

    return geometry_lookup


def process_eso_file(file_path):
    """
    Parse the .eso file and extract annual heating / cooling in kWh.
    """
    building_id = os.path.basename(os.path.dirname(file_path))

    with open(file_path, 'r') as f:
        lines = f.readlines()

    heating_id, cooling_id = None, None
    annual_heating_kwh, annual_cooling_kwh = 0.0, 0.0
    data_dict_section = True

    for line in lines:
        line = line.strip()

        if line == "End of Data Dictionary":
            data_dict_section = False
            continue

        if data_dict_section:
            if "Zone Ideal Loads Supply Air Total Heating Energy" in line:
                heating_id = int(line.split(',')[0])
            elif "Zone Ideal Loads Supply Air Total Cooling Energy" in line:
                cooling_id = int(line.split(',')[0])
        else:
            # Once out of data dictionary section, look for lines that begin with heating_id or cooling_id
            if heating_id and line.startswith(f"{heating_id},"):
                # Convert Joules -> kWh
                annual_heating_kwh += float(line.split(',')[1]) / 3600000
            elif cooling_id and line.startswith(f"{cooling_id},"):
                annual_cooling_kwh += float(line.split(',')[1]) / 3600000

    return {
        'Pand ID': building_id,  # e.g. "Pand.0599100000013220"
        'Annual Heating [kWh]': annual_heating_kwh,
        'Annual Cooling [kWh]': annual_cooling_kwh
    }


def process_all_eso_files(base_dir, geometry_folder, output_file):
    """
    1) Load geometry from individual JSON files in geometry_folder,
    2) Find all eplusout.eso files in base_dir,
    3) Extract annual heating & cooling,
    4) Convert from kWh to kWh/m2 using geometry data,
    5) Write to a new JSON file with only per-area demands.
    """
    # 1. Load geometry
    geometry_lookup = load_geometry_data_from_folder(geometry_folder)
    if not geometry_lookup:
        print(f"No geometry data loaded from {geometry_folder}. Exiting.")
        return

    # 2. Gather ESO files
    pattern = os.path.join(base_dir, "*/eplusout.eso")
    eso_files = glob.glob(pattern)

    if not eso_files:
        print(f"No ESO files found in {base_dir}")
        return

    print(f"Found {len(eso_files)} ESO files to process.")
    results = []

    # 3. For each .eso
    for file_path in eso_files:
        try:
            result = process_eso_file(file_path)
            # building_id is "Pand.0599100000013220", so remove "Pand." prefix
            pand_num = result['Pand ID'].replace("Pand.", "")

            # 4. Lookup floor area
            floor_area = geometry_lookup.get(pand_num, 0.0)
            if floor_area <= 0.0:
                print(f"Warning: no valid floor area for Pand {pand_num}, skipping.")
                continue

            # Convert to kWh/m2
            heating_kwh_m2 = result['Annual Heating [kWh]'] / floor_area
            cooling_kwh_m2 = result['Annual Cooling [kWh]'] / floor_area

            # Store final result
            new_rec = {
                "Pand ID": pand_num,
                "Annual Heating [kWh/m2]": heating_kwh_m2,
                "Annual Cooling [kWh/m2]": cooling_kwh_m2
            }
            results.append(new_rec)

            print(f"Processed {pand_num}")
            print(f"  - Heating per area: {heating_kwh_m2:.2f} kWh/m2")
            print(f"  - Cooling per area: {cooling_kwh_m2:.2f} kWh/m2")

        except Exception as e:
            print(f"Error processing {file_path}: {str(e)}")

    # 5. Write out final JSON
    if results:
        with open(output_file, 'w') as jf:
            json.dump({"buildings": results}, jf, indent=4)
        print(f"Per-area energy data saved to {output_file}")
    else:
        print("No valid results were obtained.")


if __name__ == "__main__":
    process_all_eso_files(base_directory, geometry_folder, output_file)
