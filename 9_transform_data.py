# transform level 1 features, flatten, standard scale, split to 80/20 train test. 


INPUT_CSV = "0A_flattened_coords_21.1.csv"
OUTDIR    = "prepared"
TEST_SIZE = 0.20
SEED      = 42
ID_COLS   = ["Pand ID", "Archetype ID", "Construction Year"]
TARGETS   = ["Annual Heating", "Annual Cooling"]

import os, re, pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from joblib import dump


os.makedirs(OUTDIR, exist_ok=True)

numeric_pipe = Pipeline([
    ("impute", SimpleImputer(strategy="constant", fill_value=-1)),
    ("scale",  StandardScaler())
])

coord_pipe = Pipeline([                          # NEW
    ("impute", SimpleImputer(strategy="constant", fill_value=-1))
])



# 1 · Load and isolate identifiers (keep Pand ID as string)
dtype_map = {"Pand ID": str, "Archetype ID": str}
df  = pd.read_csv(INPUT_CSV, dtype=dtype_map)
ids = df[ID_COLS].reset_index(drop=True)         # identifiers for later
df  = df.drop(columns=ID_COLS)                   # strip from modelling set

# 2 · Separate predictors / targets
y = df[TARGETS].copy()
X = df.drop(columns=TARGETS)

# 3 · Column groups -------------------------------------------------------
unit_pair_cols = [c for c in X.columns if re.fullmatch(r"u[xy]\d+", c)]   # ⬅
numeric_cols   = X.select_dtypes(include="number").columns.tolist()
num_std_cols   = [c for c in numeric_cols if c not in unit_pair_cols]

pre_X = ColumnTransformer([
    ("num",   numeric_pipe, num_std_cols),
    ("coord", coord_pipe,   unit_pair_cols),     # use coord_pipe here
])

X_std = pre_X.fit_transform(X)    # ⬅ produce the transformed feature matrix

# 5 · Scale the targets ---------------------------------------------------
from sklearn.preprocessing import StandardScaler
scaler_y = StandardScaler()
y_std    = scaler_y.fit_transform(y)

# 6 · Train / test split (keep row indices for IDs)
idx_train, idx_test = train_test_split(
        range(len(df)), test_size=TEST_SIZE, random_state=SEED)

def slice_rows(arr, idx):
    return arr[idx] if hasattr(arr, "__getitem__") else arr.iloc[idx]

X_tr, X_te = X_std[idx_train], X_std[idx_test]
y_tr, y_te = y_std[idx_train], y_std[idx_test]
id_tr      = ids.iloc[idx_train].reset_index(drop=True)
id_te      = ids.iloc[idx_test].reset_index(drop=True)

# 7 · Save helper
def save_split(X_split, y_split, ids_df, prefix):
    X_df = (pd.DataFrame(X_split, columns=pre_X.get_feature_names_out())
              .fillna(-1))                      # ← add this
    for col in reversed(ID_COLS):
        X_df.insert(0, col, ids_df[col])
    y_df = pd.DataFrame(y_split, columns=TARGETS)
    X_df.to_csv(f"{OUTDIR}/{prefix}_X.csv", index=False, na_rep='-1')  # optional na_rep
    y_df.to_csv(f"{OUTDIR}/{prefix}_y.csv", index=False)


save_split(X_tr, y_tr, id_tr, "train")
save_split(X_te, y_te, id_te, "test")

# Optional: persist scalers for inference
dump(pre_X,   f"{OUTDIR}/input_pipeline.joblib")
dump(scaler_y, f"{OUTDIR}/target_scaler.joblib")

print("data written to", OUTDIR)
