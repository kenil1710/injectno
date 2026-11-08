import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, numpy as np
from matplotlib.patches import FancyBboxPatch
from matplotlib.lines import Line2D
SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"
ORIG, PG, OURS = "#eb6834", "#1baf7a", "#2a78d6"   # validated palette slots 2, 3, 1
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 12})

def style(ax, xmax, step):
    ax.set_facecolor(SURF); ax.xaxis.grid(True, color=GRID, lw=0.8); ax.set_axisbelow(True)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID); ax.tick_params(axis="x", colors=INK2); ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, xmax); ax.set_xticks(range(0, xmax + 1, step)); ax.set_xticklabels([f"{t}%" for t in range(0, xmax + 1, step)])

def bar(ax, x0, yc, w, h, col):
    ax.add_patch(FancyBboxPatch((x0, yc - h / 2), max(w, 0.4), h, boxstyle="round,pad=0,rounding_size=0.06", lw=0, fc=col, mutation_aspect=0.35))

# Chart 1
labels = ["Benchmark v3 test\n(140 attacks)", "Benchmark v2 test\n(184 attacks)", "Original v1 test\n(384 attacks)", "Hand-written emails\n(40 attacks)"]
a, b = [43.6, 38.0, 41.4, 25.0], [0.7, 0.0, 0.8, 2.5]
na, nb = ["61", "70", "159", "10"], ["1", "0", "3", "1"]
fig, ax = plt.subplots(figsize=(10, 5.6), dpi=160); fig.patch.set_facecolor(SURF)
style(ax, 60, 10)
y = np.arange(len(labels))[::-1] * 1.0; h = 0.34
for yi, va, vb, ca, cb in zip(y, a, b, na, nb):
    bar(ax, 0, yi + h / 2 + 0.02, va, h, ORIG); ax.text(max(va, 0.4) + 0.8, yi + h / 2 + 0.02, f"{va:.1f}%  ({ca})", va="center", fontsize=11, color=INK)
    bar(ax, 0, yi - h / 2 - 0.02, vb, h, OURS); ax.text(max(vb, 0.4) + 0.8, yi - h / 2 - 0.02, f"{vb:.1f}%  ({cb})", va="center", fontsize=11, color=INK)
ax.set_yticks(y); ax.set_yticklabels(labels, color=INK, fontsize=12); ax.set_ylim(y.min() - 0.7, y.max() + 0.7)
fig.suptitle("Attacks that made the agent do what the attacker wanted", x=0.02, ha="left", fontsize=15, fontweight="bold", color=INK, y=0.98)
fig.text(0.02, 0.905, "Lower is better. Same base model, same prompts, greedy decoding. Counts in brackets.", fontsize=11, color=INK2)
leg = [Line2D([0], [0], marker="s", ls="", ms=11, mfc=ORIG, mec=ORIG, label="Aya Expanse 8B (original)"),
       Line2D([0], [0], marker="s", ls="", ms=11, mfc=OURS, mec=OURS, label="InjectNo (Aya Expanse 8B + LoRA)")]
fig.legend(handles=leg, loc="lower left", bbox_to_anchor=(0.02, 0.0), ncol=2, frameon=False, fontsize=11, labelcolor=INK)
plt.subplots_adjust(left=0.22, right=0.97, top=0.86, bottom=0.14)
fig.savefig("chart1_attacks.png", facecolor=SURF)

# Chart 2: every defence on the same benchmark (identity carried by row labels; colour only separates baselines from InjectNo)
sys_ = ["Aya Expanse 8B\n(no defence)", "Meta Prompt Guard 2\n+ Aya", "Aya + security\nsystem prompt", "Aya + prompt +\nspotlighting", "InjectNo"]
att = [43.6, 43.6, 39.3, 24.3, 0.7]; nor = [64.9, 64.9, 72.8, 47.4, 95.6]
cols = [ORIG, ORIG, ORIG, ORIG, OURS]
fig, axs = plt.subplots(1, 2, figsize=(10.5, 5.6), dpi=160); fig.patch.set_facecolor(SURF)
for ax, vals, title, sub in ((axs[0], att, "Attacks that worked (140)", "lower is better"),
                             (axs[1], nor, "Normal emails done right (114)", "higher is better")):
    style(ax, 115, 25); ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"])
    yy = np.arange(5)[::-1]
    for yi, v, c in zip(yy, vals, cols):
        bar(ax, 0, yi, v, 0.6, c); ax.text(max(v, 0.4) + 2, yi, f"{v:.1f}%", va="center", fontsize=12, color=INK)
    ax.set_ylim(-0.7, 4.7); ax.set_yticks(yy); ax.set_yticklabels(sys_ if ax is axs[0] else [""] * 5, fontsize=11, color=INK)
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold", color=INK, pad=22)
    ax.text(0, 4.85, sub, fontsize=10.5, color=INK2)
fig.suptitle("Filters and prompts vs. training the agent (same 254 emails, benchmark v3 test)", x=0.02, ha="left", fontsize=14.5, fontweight="bold", color=INK)
fig.text(0.02, 0.025, "Prompt Guard flagged 0 of 318 emails. Spotlighting cut attacks to 24% but raised false alarms on normal emails to 37%.\nNormal emails: correct action and no false alarm. Orange = no training; blue = InjectNo.", fontsize=9.8, color=INK2)
plt.subplots_adjust(left=0.19, right=0.97, top=0.8, bottom=0.17, wspace=0.12)
fig.savefig("chart2_promptguard.png", facecolor=SURF)
print("ok")
