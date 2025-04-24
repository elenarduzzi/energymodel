import pandas as pd, matplotlib.pyplot as plt

df = pd.read_csv("ann_predictions_level02_v0.csv")

plt.scatter(df["Annual Heating_true"], df["Annual Heating_pred"])
plt.xlabel("True heating (kWh/m²)"); plt.ylabel("Predicted"); plt.grid(True)
plt.show()