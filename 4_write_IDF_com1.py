# generate IDF files from classified surface JSONs using multiprocessing
import os
import json
from eppy.modeleditor import IDF
from io import StringIO
from multiprocessing import Pool
import boto3

# paths & config
idd_path = "C:/EnergyPlusV24-2-0/Energy+.idd"
input_dir = "2B_pand_surfaces_6_EPLUS"
output_dir = "4B_pand_idfs_6"
materials_file_path = "3B_materials_for_idf.json"
base_idf_path = "4A_rotterdam_simple.idf"
S3_BUCKET = ""  # e.g. "my-energyplus-idfs"
OUTPUT_PREFIX = "idf_files"

s3 = boto3.client("s3") if S3_BUCKET else None
os.makedirs(output_dir, exist_ok=True)
IDF.setiddname(idd_path)

with open(base_idf_path, 'r') as f:
    base_idf_str = f.read()

with open(materials_file_path, 'r') as f:
    material_defs = json.load(f)

def make_vertices(coords):
    return [(x, y, z) for x, y, z in coords]

def save_idf(idf, filename):
    if S3_BUCKET:
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile("w+", delete=False, suffix=".idf") as tmp:
            idf.save(tmp.name)
            tmp.flush()
            s3.upload_file(tmp.name, S3_BUCKET, f"{OUTPUT_PREFIX}/{filename}")
        print(f"uploaded to S3: {S3_BUCKET}/{OUTPUT_PREFIX}/{filename}")
    else:
        out_path = os.path.join(output_dir, filename)
        idf.save(out_path)
        print(f"idf saved to: {out_path}")

def process_file(json_path):
    try:
        with open(json_path, 'r') as f:
            surface_data = json.load(f)

        for pand_id, entry in surface_data.items():
            archetype_id = entry["Archetype ID"]
            surfaces = entry["Surfaces"]
            materials = material_defs.get(archetype_id, {}).get("Materials", [])

            pand_code = pand_id.split('.')[-1]
            building_name = f"Pand.{pand_code}"
            zone_name = f"Zone_{pand_code}"

            idf = IDF(StringIO(base_idf_str))

            # Ensure needed limits
            existing_limits = [obj.Name.upper() for obj in idf.idfobjects["SCHEDULETYPELIMITS"]]
            if "TEMPERATURE" not in existing_limits:
                idf.newidfobject("SCHEDULETYPELIMITS", Name="Temperature", Lower_Limit_Value=-100,
                                 Upper_Limit_Value=100, Numeric_Type="CONTINUOUS", Unit_Type="Temperature")
            if "FRACTION" not in existing_limits:
                idf.newidfobject("SCHEDULETYPELIMITS", Name="Fraction", Lower_Limit_Value=0,
                                 Upper_Limit_Value=1, Numeric_Type="CONTINUOUS", Unit_Type="Dimensionless")

            idf.newidfobject("SITE:GROUNDTEMPERATURE:BUILDINGSURFACE", **{f"{month}_Ground_Temperature": 18 for month in [
                "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]})

            idf.newidfobject("BUILDING", Name=building_name, North_Axis=0.0, Terrain="City",
                             Loads_Convergence_Tolerance_Value=0.04,
                             Temperature_Convergence_Tolerance_Value=0.4,
                             Solar_Distribution="FullExterior", Maximum_Number_of_Warmup_Days=25)

            idf.newidfobject("ZONE", Name=zone_name, Direction_of_Relative_North=0.0,
                             X_Origin=0.0, Y_Origin=0.0, Z_Origin=0.0, Type=1, Multiplier=1,
                             Ceiling_Height="Autocalculate", Volume="Autocalculate")

            idf.newidfobject("HVACTEMPLATE:ZONE:IDEALLOADSAIRSYSTEM", Zone_Name=zone_name)

            idf.newidfobject("SCHEDULE:COMPACT", Name=f"HeatingSetpoint_{zone_name}",
                             Schedule_Type_Limits_Name="Temperature", Field_1="Through: 12/31",
                             Field_2="For: AllDays", Field_3="Until: 24:00", Field_4="21.0")
            idf.newidfobject("SCHEDULE:COMPACT", Name=f"CoolingSetpoint_{zone_name}",
                             Schedule_Type_Limits_Name="Temperature", Field_1="Through: 12/31",
                             Field_2="For: AllDays", Field_3="Until: 24:00", Field_4="24.0")

            idf.newidfobject("THERMOSTATSETPOINT:DUALSETPOINT", Name=f"Thermostat_{zone_name}",
                             Heating_Setpoint_Temperature_Schedule_Name=f"HeatingSetpoint_{zone_name}",
                             Cooling_Setpoint_Temperature_Schedule_Name=f"CoolingSetpoint_{zone_name}")

            idf.newidfobject("ZONECONTROL:THERMOSTAT", Name=f"ThermostatControl_{zone_name}",
                             Zone_or_ZoneList_Name=zone_name, Control_Type_Schedule_Name="DualSetpointControlType",
                             Control_1_Object_Type="ThermostatSetpoint:DualSetpoint",
                             Control_1_Name=f"Thermostat_{zone_name}")

            idf.newidfobject("SCHEDULETYPELIMITS", Name="Control Type", Lower_Limit_Value=0,
                             Upper_Limit_Value=4, Numeric_Type="DISCRETE")
            idf.newidfobject("SCHEDULE:COMPACT", Name="DualSetpointControlType",
                             Schedule_Type_Limits_Name="Control Type", Field_1="Through: 12/31",
                             Field_2="For: AllDays", Field_3="Until: 24:00", Field_4="4")
            idf.newidfobject("SCHEDULE:COMPACT", Name="AlwaysOn", Schedule_Type_Limits_Name="Fraction",
                             Field_1="Through: 12/31", Field_2="For: AllDays", Field_3="Until: 24:00", Field_4="1.0")

            infiltration_qv = material_defs.get(archetype_id, {}).get("Infiltration", 0)
            idf.newidfobject("ZONEINFILTRATION:DESIGNFLOWRATE", Name=f"Infil_{zone_name}",
                             Zone_or_ZoneList_or_Space_or_SpaceList_Name=zone_name, Schedule_Name="AlwaysOn",
                             Design_Flow_Rate_Calculation_Method="Flow/Area", Flow_Rate_per_Floor_Area=infiltration_qv)

            for surf_type in ['G', 'F', 'R']:
                mat_id = f"{surf_type}.{archetype_id}"
                mat = next((m for m in materials if isinstance(m, dict) and m.get("Material ID") == mat_id), None)
                if mat:
                    idf.newidfobject("MATERIAL", Name=mat_id, Roughness=mat["Roughness"],
                                     Thickness=mat["Thickness"], Conductivity=mat["Conductivity"],
                                     Density=mat["Density"], Specific_Heat=mat["Specific Heat Capacity"],
                                     Thermal_Absorptance=0.9, Solar_Absorptance=0.7)
                    idf.newidfobject("CONSTRUCTION", Name=f"C_{surf_type}", Outside_Layer=mat_id)

            for mat in materials:
                if "Window ID" in mat:
                    idf.newidfobject("WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM", Name=mat["Window ID"],
                                     UFactor=mat["U_Factor"], Solar_Heat_Gain_Coefficient=mat["SHGC"],
                                     Visible_Transmittance=0.6)

            for i, surface in enumerate(surfaces):
                coords = surface["Coordinates"][0]  # outer ring only
                coords_3d = [(x / 1000, y / 1000, z / 1000) for x, y, z in coords]
                surface_type = surface["Type"]
                surf_name = f"{surface_type}_{i}"
                surf_map = {'G': 'Floor', 'R': 'Roof', 'F': 'Wall'}
                bc_map = {'G': 'Ground', 'R': 'Outdoors', 'F': 'Outdoors'}
                if surface_type not in surf_map:
                    continue

                idf_surface = idf.newidfobject("BUILDINGSURFACE:DETAILED", Name=surf_name,
                                               Surface_Type=surf_map[surface_type],
                                               Construction_Name=f"C_{surface_type}",
                                               Zone_Name=zone_name,
                                               Outside_Boundary_Condition=bc_map[surface_type],
                                               Sun_Exposure="SunExposed", Wind_Exposure="WindExposed",
                                               View_Factor_to_Ground=0.5, Number_of_Vertices=len(coords_3d))

                for j, (x, y, z) in enumerate(coords_3d):
                    idf_surface[f"Vertex_{j+1}_Xcoordinate"] = x
                    idf_surface[f"Vertex_{j+1}_Ycoordinate"] = y
                    idf_surface[f"Vertex_{j+1}_Zcoordinate"] = z

            idf.newidfobject("OUTPUT:VARIABLE", Key_Value="*",
                             Variable_Name="Zone Ideal Loads Supply Air Total Heating Energy",
                             Reporting_Frequency="Hourly")
            idf.newidfobject("OUTPUT:VARIABLE", Key_Value="*",
                             Variable_Name="Zone Ideal Loads Supply Air Total Cooling Energy",
                             Reporting_Frequency="Hourly")

            save_idf(idf, f"{building_name}.idf")

    except Exception as e:
        print(f"Error writing IDF from {json_path}: {e}")

if __name__ == '__main__':
    files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.endswith('.json')]
    with Pool() as pool:
        pool.map(process_file, files)

    print(f"\nIDFs written to: {output_dir}" if not S3_BUCKET else f"\nIDFs uploaded to: s3://{S3_BUCKET}/{OUTPUT_PREFIX}")
