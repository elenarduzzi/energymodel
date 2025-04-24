# run energy plus simulations using MULTIPROCESSING

import os
import subprocess
import shutil
import tempfile
from multiprocessing import Pool

# input files

idf_folder = "4B_pand_idfs_21"
output_root = "5B_EP_sims_21"
eplus_exe = "C:/EnergyPlusV24-2-0/energyplus.exe"
epw_path = os.path.abspath("4A_NLD_ZH_Rotterdam.The.Hague.AP.063440_TMYx.2009-2023.epw")

os.makedirs(output_root, exist_ok=True)

def run_simulation(idf_file):
    pand_name = os.path.splitext(os.path.basename(idf_file))[0]
    pand_output = os.path.join(output_root, pand_name)
    os.makedirs(pand_output, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_idf_path = os.path.join(temp_dir, "in.idf")
        shutil.copy(idf_file, temp_idf_path)

        # use absolute path for the output directory
        abs_output = os.path.abspath(pand_output)

        subprocess.run([
            eplus_exe,
            "--weather", epw_path,
            "--output-directory", abs_output,
            "--annual",
            "--expandobjects",
            "in.idf"
        ], cwd=temp_dir, check=True)

    # keep only eso and err files 
    keep_only_eso_err(abs_output)
    print(f"Finished {pand_name}")

def keep_only_eso_err(folder):
    keep = {"eplusout.eso", "eplusout.err"}
    for fname in os.listdir(folder):
        if fname not in keep:
            os.remove(os.path.join(folder, fname))

def main():
    idf_files = [os.path.join(idf_folder, f) for f in os.listdir(idf_folder) if f.endswith(".idf")]
    with Pool() as pool:
        pool.map(run_simulation, idf_files)
    print("\nAll simulations completed.")

if __name__ == "__main__":
    main()
