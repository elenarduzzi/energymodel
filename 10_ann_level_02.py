# train ann from level 1 features
# 3_ann_v22.py  –  train ANN on new prepared data
import os
import pandas as pd
import torch
from torch import nn, optim
from joblib import load
import matplotlib.pyplot as plt
import wandb

# ─────────────────────────────────────────────────────────────
# Hard‑wired paths produced by the “prepare” script
# (adjust directory name if you moved the files)
# ─────────────────────────────────────────────────────────────
DATA_DIR         = "prepared"
TRAIN_X_CSV      = os.path.join(DATA_DIR, "train_X.csv")
TRAIN_Y_CSV      = os.path.join(DATA_DIR, "train_y.csv")
TEST_X_CSV       = os.path.join(DATA_DIR, "test_X.csv")
TEST_Y_CSV       = os.path.join(DATA_DIR, "test_y.csv")
TARGET_SCALER    = os.path.join(DATA_DIR, "target_scaler.joblib")
MODEL_OUT        = "ann_model_level02_v0.pth"
PRED_OUT         = "ann_predictions_level02_v0.csv"
RUN_NAME         = "4.18_ann_level02_v0"
# ─────────────────────────────────────────────────────────────

# 1 · Weights & Biases run -------------------------------------------------
run = wandb.init(
    name=RUN_NAME,
    entity="elenarduzzi-tu-delft",
    project="my_energy_model",
    config={
        "learning_rate": 1e-4,
        "architecture": "ANN‑v22",
        "dataset": "prepared csv",
        "epochs": 500,
        "hidden_dim": 64     # feel free to tune
    },
)
config = run.config

# 2 · Load data ------------------------------------------------------------
# keep identifiers as strings so leading zeros survive
dtype_ids = {"Pand ID": str, "Archetype ID": str, "Construction Year": str}

X_train_df = pd.read_csv(TRAIN_X_CSV, dtype=dtype_ids)
y_train_df = pd.read_csv(TRAIN_Y_CSV)
X_test_df  = pd.read_csv(TEST_X_CSV , dtype=dtype_ids)
y_test_df  = pd.read_csv(TEST_Y_CSV)

# Separate IDs (first 3 columns) from numeric features
ID_COLS = ["Pand ID", "Archetype ID", "Construction Year"]
feature_cols = X_train_df.columns[3:]          # everything after IDs

X_train = X_train_df[feature_cols].to_numpy(dtype="float32")
X_test  = X_test_df [feature_cols].to_numpy(dtype="float32")
y_train = y_train_df.to_numpy(dtype="float32")
y_test  = y_test_df .to_numpy(dtype="float32")

# Convert to tensors
X_train_t = torch.tensor(X_train)
y_train_t = torch.tensor(y_train)
X_test_t  = torch.tensor(X_test)
y_test_t  = torch.tensor(y_test)

# 3 · Define the ANN -------------------------------------------------------
class ANN(nn.Module):
    def __init__(self, in_dim, hidden_dim, out_dim=2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, out_dim)
        )
    def forward(self, x): return self.net(x)

model     = ANN(in_dim=len(feature_cols), hidden_dim=config.hidden_dim)
criterion = nn.MSELoss()
optimizer = optim.Adam(model.parameters(), lr=config.learning_rate)

# 4 · Training loop --------------------------------------------------------
train_losses, test_losses = [], []
for epoch in range(config.epochs):
    # --- train ---
    model.train()
    optimizer.zero_grad()
    pred_train = model(X_train_t)
    loss_train = criterion(pred_train, y_train_t)
    loss_train.backward()
    optimizer.step()

    # --- test ---
    model.eval()
    with torch.no_grad():
        pred_test = model(X_test_t)
        loss_test = criterion(pred_test, y_test_t)

    # record
    train_losses.append(loss_train.item())
    test_losses.append(loss_test.item())
    wandb.log({"train_loss": loss_train.item(),
               "test_loss" : loss_test.item(),
               "epoch"     : epoch+1})
    if (epoch+1) % 20 == 0:
        print(f"[{epoch+1}/{config.epochs}] "
              f"train={loss_train.item():.4f}  "
              f"test={loss_test.item():.4f}")

# 5 · Loss curves ----------------------------------------------------------
plt.figure(figsize=(7,4))
plt.plot(train_losses, label="train")
plt.plot(test_losses , label="test" )
plt.xlabel("Epoch"); plt.ylabel("MSE loss")
plt.title("Loss curves"); plt.legend(); plt.grid(True)
plt.show()

# 6 · Inverse‑transform predictions & save --------------------------------
scaler_y = load(TARGET_SCALER)

with torch.no_grad():
    preds_scaled = model(X_test_t).numpy()

preds_real   = scaler_y.inverse_transform(preds_scaled)
truth_real   = scaler_y.inverse_transform(y_test)   # ← NEW

# 7 · Build output CSV
out_df = pd.concat(
    [
        X_test_df[ID_COLS].reset_index(drop=True),
        pd.DataFrame(truth_real,
                     columns=["Annual Heating_true", "Annual Cooling_true"]),
        pd.DataFrame(preds_real,
                     columns=["Annual Heating_pred", "Annual Cooling_pred"])
    ],
    axis=1
)

out_df.to_csv(PRED_OUT, index=False)
print("Predictions & ground‑truth saved to", PRED_OUT)

# 7 · Log W&B artifacts ----------------------------------------------------
art_data = wandb.Artifact("prepared_data_v22", type="dataset",
                          description="Prepared splits v22")
for f in [TRAIN_X_CSV, TRAIN_Y_CSV, TEST_X_CSV, TEST_Y_CSV]:
    art_data.add_file(f)
run.log_artifact(art_data)

model_art = wandb.Artifact("ann_model_v22", type="model",
                           description="ANN trained on prepared v22")
torch.save(model.state_dict(), MODEL_OUT)
model_art.add_file(MODEL_OUT)
model_art.add_file(__file__)
run.log_artifact(model_art)

pred_art = wandb.Artifact("predictions_v22", type="dataset",
                          description="ANN predictions v22")
pred_art.add_file(PRED_OUT)
run.log_artifact(pred_art)

run.finish()
