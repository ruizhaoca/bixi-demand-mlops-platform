"""Generate the model-performance results slide (PNG) for the final presentation.

Numbers are the real values from the committed cloud-2024 run:
  artifacts/streamlit-community-cloud/cloud-2024/<target>/metadata/metrics.json
  artifacts/streamlit-community-cloud/cloud-2024/departure/monitoring/fairness_report.json
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

# Palette (BIXI red + neutrals)
RED = "#b91c1c"
RED_LT = "#fca5a5"
GREY = "#9ca3af"
DARK = "#1f2937"
INK = "#111827"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": "#d1d5db",
    "axes.linewidth": 0.8,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": DARK,
    "ytick.color": DARK,
})

# Real numbers ---------------------------------------------------------------
# Validation (May-2025): naive baseline vs tuned model
naive_rmse = {"Departure": 1.040, "Arrival": 1.027}
model_rmse_val = {"Departure": 0.994, "Arrival": 0.976}
# Per-tier R2 (departure, test set)
tier_r2 = {"Low": 0.018, "Medium": 0.066, "High": 0.394}
# Headline table rows: target, split, rmse, mae, r2
table_rows = [
    ["Departure", "Val (May-25)", "0.994", "0.565", "0.327"],
    ["Departure", "Test (Oct-25)", "1.035", "0.591", "0.334"],
    ["Arrival", "Val (May-25)", "0.976", "0.554", "0.339"],
    ["Arrival", "Test (Oct-25)", "1.026", "0.585", "0.339"],
]

fig = plt.figure(figsize=(13.33, 7.5), dpi=200)
fig.patch.set_facecolor("white")
gs = GridSpec(2, 2, figure=fig, height_ratios=[1.25, 1.0],
              left=0.055, right=0.965, top=0.80, bottom=0.075,
              wspace=0.22, hspace=0.42)

# Title band
fig.text(0.055, 0.935, "Model Performance",
         fontsize=30, fontweight="bold", color=INK)
fig.text(0.055, 0.885,
         "Optuna-tuned LightGBM  ·  15-minute demand  ·  departures & arrivals  ·  ~1,100 stations",
         fontsize=13.5, color=DARK)
fig.text(0.055, 0.852,
         "Units: trips per 15-minute slot (mean target = 0.33).  Validation = May 2025, Test = October 2025.",
         fontsize=11, color=GREY, style="italic")

# ---------------------------------------------------------------------------
# Panel 1: Validation RMSE — model vs naive baseline
# ---------------------------------------------------------------------------
ax1 = fig.add_subplot(gs[0, 0])
targets = ["Departure", "Arrival"]
x = range(len(targets))
w = 0.36
b1 = ax1.bar([i - w / 2 for i in x], [naive_rmse[t] for t in targets], w,
             label="Naive baseline", color=GREY)
b2 = ax1.bar([i + w / 2 for i in x], [model_rmse_val[t] for t in targets], w,
             label="Tuned model", color=RED)
ax1.set_xticks(list(x))
ax1.set_xticklabels(targets, fontsize=12)
ax1.set_ylabel("Validation RMSE", fontsize=11.5)
ax1.set_ylim(0.9, 1.07)
ax1.set_title("Tuned model vs naive baseline  (lower is better)",
              fontsize=13, fontweight="bold", loc="left", pad=8)
for bars in (b1, b2):
    for bar in bars:
        ax1.annotate(f"{bar.get_height():.3f}",
                     (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                     ha="center", va="bottom", fontsize=10.5, color=INK)
ax1.legend(frameon=False, fontsize=10.5, loc="upper right", ncol=2)
ax1.spines[["top", "right"]].set_visible(False)
ax1.tick_params(length=0)
# delta callout — sits in the gap between the two target groups
ax1.annotate("-4% RMSE\n+6 pts R²\nvs naive", (0.5, 0.42), xycoords="axes fraction",
             ha="center", va="center", fontsize=10, color=RED, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.4", fc="#fef2f2", ec=RED, lw=0.8))

# ---------------------------------------------------------------------------
# Panel 2: R2 by demand tier (concentration story)
# ---------------------------------------------------------------------------
ax2 = fig.add_subplot(gs[0, 1])
tiers = ["Low", "Medium", "High"]
colors = [RED_LT, "#f87171", RED]
bars = ax2.bar(tiers, [tier_r2[t] for t in tiers], color=colors, width=0.6)
ax2.set_ylabel("R²  (departure, test)", fontsize=11.5)
ax2.set_ylim(0, 0.46)
ax2.set_title("Where the model explains variance  ·  R² by demand tier",
              fontsize=13, fontweight="bold", loc="left", pad=8)
for bar in bars:
    ax2.annotate(f"{bar.get_height():.3f}",
                 (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                 ha="center", va="bottom", fontsize=11, color=INK, fontweight="bold")
ax2.spines[["top", "right"]].set_visible(False)
ax2.tick_params(length=0)
ax2.annotate("Predictive power is concentrated\nin high-demand stations",
             (0.04, 0.95), xycoords="axes fraction",
             fontsize=10, color=DARK, va="top")

# ---------------------------------------------------------------------------
# Panel 3: headline metrics table
# ---------------------------------------------------------------------------
ax3 = fig.add_subplot(gs[1, 0])
ax3.axis("off")
ax3.set_title("Headline metrics", fontsize=13, fontweight="bold", loc="left", y=0.98)
col_labels = ["Target", "Split", "RMSE", "MAE", "R²"]
tbl = ax3.table(cellText=table_rows, colLabels=col_labels,
                cellLoc="center", colLoc="center", loc="center",
                bbox=[0.0, 0.05, 1.0, 0.80])
tbl.auto_set_font_size(False)
tbl.set_fontsize(11)
for (r, c), cell in tbl.get_celld().items():
    cell.set_edgecolor("#e5e7eb")
    if r == 0:
        cell.set_facecolor(RED)
        cell.set_text_props(color="white", fontweight="bold")
    else:
        cell.set_facecolor("#ffffff" if r % 2 else "#f9fafb")
        if c == 0:
            cell.set_text_props(fontweight="bold")

# ---------------------------------------------------------------------------
# Panel 4: takeaways
# ---------------------------------------------------------------------------
ax4 = fig.add_subplot(gs[1, 1])
ax4.axis("off")
ax4.set_title("Takeaways", fontsize=13, fontweight="bold", loc="left", y=0.98)
bullets = [
    ("Robust", "stable across two unseen months — no overfitting"),
    ("Honest lift", "lower RMSE / higher R² than naive (MAE a touch higher)"),
    ("Operational", "RMSE ≈ 1 trip / 15-min; typical error (MAE) ≈ 0.6"),
    ("Targeted", "strongest exactly where it matters — busy stations"),
]
y = 0.80
for head, body in bullets:
    ax4.annotate("●", (0.0, y), xycoords="axes fraction", fontsize=11, color=RED,
                 va="center")
    ax4.annotate(f"  {head} — ", (0.03, y), xycoords="axes fraction", fontsize=11.5,
                 color=INK, fontweight="bold", va="center")
    ax4.annotate(body, (0.03, y - 0.105), xycoords="axes fraction", fontsize=10.5,
                 color=DARK, va="center")
    y -= 0.24

out = "docs/presentation/results_performance_slide.png"
fig.savefig(out, dpi=200, facecolor="white", bbox_inches="tight")
print(f"wrote {out}")
