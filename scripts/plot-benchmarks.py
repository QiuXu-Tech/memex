#!/usr/bin/env python3
"""Render the benchmark PNGs from the checked-in measurement files."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


ASSETS = Path(__file__).resolve().parents[1] / "docs/assets/benchmarks"


def load(name):
    return json.loads((ASSETS / name).read_text())


compaction = load("results-compaction.json")
repeat = load("results-compaction-repeat.json")
scale = load("results-scale.json")["results"]
scale_repeat = load("results-scale-repeat.json")["results"]
capacity = load("results-capacity.json")["runs"][1]
metadata = load("run-metadata.json")

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "text.color": "#eef2fb",
    "axes.labelcolor": "#dbe4f4",
    "xtick.color": "#c1cee1",
    "ytick.color": "#c1cee1",
    "axes.edgecolor": "#53617a",
    "axes.facecolor": "#131e33",
    "figure.facecolor": "#0b1222",
    "savefig.facecolor": "#0b1222",
    "axes.titleweight": "bold",
})
BLUE, TEAL, GOLD, RED = "#6f98ff", "#25c5b3", "#e6c65b", "#f48386"


def setup(ax, axis="y"):
    ax.set_axisbelow(True)
    ax.grid(axis=axis, color="#43516a", alpha=0.38, linewidth=0.7)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def heading(fig, title, subtitle):
    fig.text(0.065, 0.94, title, fontsize=20, weight="bold", va="top")
    fig.text(0.065, 0.885, subtitle, fontsize=11, color="#aebdd4", va="top")


def footnote(fig, text):
    fig.text(0.065, 0.035, text, fontsize=9, color="#aebdd4", va="bottom")


def save(fig, name):
    fig.savefig(ASSETS / name, dpi=140)
    plt.close(fig)


# Availability counts for the first two methods and target-record hits for DSH.
fig, ax = plt.subplots(figsize=(12.8, 6.8))
heading(fig, "Synthetic long-horizon probes", f"v{metadata['testedVersion']} · 160K estimated-token history · 80K window · 40 probes")
fig.subplots_adjust(left=0.085, right=0.965, top=0.79, bottom=0.23)
setup(ax)
all_values = [compaction["truncation"]["accuracy"] * 100,
              compaction["compaction"]["accuracy"] * 100,
              compaction["dshMemory"]["hit5"] * 100]
old_values = [0, compaction["compaction"]["oldFactRecovery"] * 100,
              sum(d["cold"] and 0 <= d["rank"] < 5 for d in compaction["dshMemory"]["details"]) / compaction["compaction"]["oldFacts"] * 100]
positions = list(range(3))
width = 0.32
for x, overall, old in zip(positions, all_values, old_values):
    ax.bar(x - width / 2, overall, width, color=BLUE)
    ax.bar(x + width / 2, old, width, color=TEAL)
    ax.text(x - width / 2, overall + 2, f"{overall:.0f}%", ha="center", fontsize=12)
    ax.text(x + width / 2, old + 2, f"{old:.0f}%", ha="center", fontsize=12)
ax.set_xticks(positions, ["Truncated tail", "Prior summary + tail", "dsh-memory search"])
ax.set_ylabel("Share of probes")
ax.set_ylim(0, 120)
ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
ax.legend(["All 40 probes", "20 probes in old span"], loc="upper left", ncol=2,
          frameon=False, labelcolor="#dbe4f4")
footnote(fig, "First two bars: fact/cue availability. DSH bars: target-record hit@5; not model answer accuracy.")
save(fig, "fact-recall.png")

# Window/history is a ratio, not an observed no-memory recall score.
fig, axes = plt.subplots(1, 2, figsize=(12.8, 6.8))
heading(fig, "Synthetic scaling: two different measures", f"v{metadata['testedVersion']} · 1M window · 40 identifier-based probes per history size")
fig.subplots_adjust(left=0.08, right=0.965, top=0.75, bottom=0.19, wspace=0.26)
labels = ["1M", "5M", "10M"]
for ax, title in [(axes[0], "Window / history ratio"), (axes[1], "Target-record hit@5")]:
    setup(ax)
    ax.set_title(title, loc="left", pad=12, fontsize=13)
    ax.set_ylim(0, 118)
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100))
    ax.set_xlabel("Synthetic history size (estimated tokens)")
coverage = [r["noMemoryAvailability"] * 100 for r in scale]
axes[0].bar(labels, coverage, color=GOLD, width=0.52)
for i, value in enumerate(coverage):
    label = f"{value:.1f}%" if 90 < value < 99.95 else f"{value:.0f}%"
    axes[0].text(i, value + 2, label, ha="center", fontsize=12)
for i, (first, second) in enumerate(zip(scale, scale_repeat)):
    for offset, run, color in [(-0.17, first, BLUE), (0.17, second, TEAL)]:
        value = run["dshMemoryHit5"] * 100
        axes[1].bar(i + offset, value, color=color, width=0.32)
        axes[1].text(i + offset, value + 2, f"{value:.0f}%", ha="center", fontsize=10)
axes[1].set_xticks(range(3), labels)
axes[1].legend(["First", "Repeat"], loc="upper left", ncol=2, frameon=False, labelcolor="#dbe4f4")
footnote(fig, "The coverage ratio is not a measured no-memory recall rate or a universal ceiling.")
save(fig, "recall-scaling.png")

# Search latency excludes opening a record or a model call.
fig, axes = plt.subplots(1, 2, figsize=(12.8, 6.8), gridspec_kw={"width_ratios": [1.35, 1]})
heading(fig, "Search latency and estimated context cost", f"v{metadata['testedVersion']} · quiet-start gate met · shared machine · search only")
fig.subplots_adjust(left=0.08, right=0.965, top=0.75, bottom=0.21, wspace=0.3)
latencies = [r["medianLatencyMs"] for r in scale]
latencies_repeat = [r["medianLatencyMs"] for r in scale_repeat]
setup(axes[0])
axes[0].set_title("Scaling: p50 of 40 searches per run", loc="left", pad=12, fontsize=13)
for i, (first, second) in enumerate(zip(latencies, latencies_repeat)):
    for offset, value, color in [(-0.17, first, BLUE), (0.17, second, TEAL)]:
        axes[0].bar(i + offset, value, color=color, width=0.32)
        axes[0].text(i + offset, value + max(latencies + latencies_repeat) * 0.035,
                     f"{value:.1f}", ha="center", fontsize=10)
axes[0].set_xticks(range(3), labels)
axes[0].legend(["First", "Repeat"], loc="upper left", ncol=2, frameon=False, labelcolor="#dbe4f4")
axes[0].set_ylim(0, max(latencies + latencies_repeat) * 1.3)
axes[0].set_ylabel("Search p50 (ms)")
axes[0].set_xlabel("Synthetic history size")
repeats = [compaction["dshMemory"]["medianLatencyMs"], repeat["dshMemory"]["medianLatencyMs"]]
setup(axes[1])
axes[1].set_title("160K run: two repeats", loc="left", pad=12, fontsize=13)
axes[1].bar(["First", "Repeat"], repeats, color=[BLUE, TEAL], width=0.48)
for i, value in enumerate(repeats):
    axes[1].text(i, value + max(repeats) * 0.035, f"{value:.2f} ms", ha="center", fontsize=11)
axes[1].set_ylim(0, max(repeats) * 1.3)
axes[1].set_ylabel("Search p50 (ms)")
footnote(fig, f"Estimated cards + one hypothetical body: {compaction['dshMemory']['tokensPerQuestion']:,} tokens/probe; "
              f"old span: {compaction['oldSpanTokens']:,}. Counts use character-based estimates.")
save(fig, "cost-latency.png")

# 100M-token synthetic pool: timed cold GC deletes the removed records.
fig, axes = plt.subplots(1, 2, figsize=(12.8, 6.8), gridspec_kw={"width_ratios": [1.18, 1]})
heading(fig, "Synthetic 100M-token pool", "10,000 records · 10,000 assigned tokens per record · quiet-start gate met")
fig.subplots_adjust(left=0.2, right=0.955, top=0.75, bottom=0.19, wspace=0.45)
storage_names = ["Index after write", "Index after cold spill", "Original body files"]
storage = [capacity["indexAfterWriteMiB"], capacity["indexAfterColdMiB"], capacity["bodyFilesMiB"]]
setup(axes[0], axis="x")
axes[0].set_title("Storage footprint", loc="left", pad=12, fontsize=13)
axes[0].barh(storage_names, storage, color=[BLUE, TEAL, GOLD], height=0.55)
axes[0].invert_yaxis()
axes[0].set_xlim(0, max(storage) * 1.25)
axes[0].set_xlabel("MiB")
for i, value in enumerate(storage):
    axes[0].text(value + 5, i, f"{value:.1f}", va="center", fontsize=11)
operations = [capacity["writeSeconds"], capacity["coldSpillSeconds"], capacity["gcSeconds"]]
setup(axes[1], axis="x")
axes[1].set_title("Operations, one run", loc="left", pad=12, fontsize=13)
axes[1].barh(["Write 100M", "Cold spill 50M", "Cold GC 25M"], operations, color=[BLUE, TEAL, RED], height=0.55)
axes[1].invert_yaxis()
axes[1].set_xlim(0, max(operations) * 1.35)
axes[1].set_xlabel("Seconds")
for i, value in enumerate(operations):
    axes[1].text(value + max(operations) * 0.025, i, f"{value:.2f}", va="center", fontsize=11)
footnote(fig, "Cold spill moves records; cold GC deletes them. Token sizes are assigned synthetic values.")
save(fig, "capacity.png")
