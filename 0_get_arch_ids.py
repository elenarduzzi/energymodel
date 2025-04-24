# take input excel pand ids and archetype ids output as json file

import pandas as pd
import json

# batch file paths 

# "0A_clean_archetype_6.xlsx"
# "0B_pand_arch_map_6.json"

# "0A_clean_archetype_7.xlsx"
# "0B_pand_arch_map_7.json"

# "0A_clean_archetype_8.xlsx"
# "0B_pand_arch_map_8.json"

# "0A_clean_archetype_21.xlsx"
# "0B_pand_arch_map_21.json"

excel_path = "0A_clean_archetype_21.xlsx"
output_path = "0B_pand_arch_map_21.json"


# select relevant columns
df = pd.read_excel(excel_path)
df_filtered = df[["Pand_ID", "Archetype_ID"]].dropna()

# convert to string to maintain leading zero for pand ids, * using 16 characters
mapping = {
    str(int(pand_id)).zfill(16): archetype
    for pand_id, archetype in zip(df_filtered["Pand_ID"], df_filtered["Archetype_ID"])
}

# write to json
with open(output_path, "w") as json_file:
    json.dump(mapping, json_file, indent=2)

print(f"JSON file created: {output_path}")
