#!/usr/bin/env python3
import re
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import matplotlib.pyplot as plt

RESULT_DIR = Path("results")
PLOT_DIR = RESULT_DIR / "plots"

WORKLOAD_TYPES = {
    "compute1": "compute",
    "compute2": "compute",
    "memory1": "memory",
    "memory2": "memory",
    "branch1": "branch",
}

ROB_COST_COEF = 1
ISSUE_WIDTH_COST_COEF = 16
DEFAULT_ROB = 128
DEFAULT_ISSUE_WIDTH = 4


def parse_first_float(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def extract_metrics(stats_path: Path) -> Dict[str, Optional[float]]:
    text = stats_path.read_text(errors="ignore")

    ipc = parse_first_float(r"^system\.cpu\.ipc\s+([0-9eE+\-.]+)", text)
    cpi = parse_first_float(r"^system\.cpu\.cpi\s+([0-9eE+\-.]+)", text)

    branch_count = parse_first_float(
        r"^system\.cpu\.bac\.branches\s+([0-9eE+\-.]+)", text
    )
    branch_mispredict = parse_first_float(
        r"^system\.cpu\.bac\.branchMisspredict\s+([0-9eE+\-.]+)", text
    )

    branch_mispredict_rate = None
    if branch_count is not None and branch_count > 0 and branch_mispredict is not None:
        branch_mispredict_rate = branch_mispredict / branch_count

    l1d_miss_rate = parse_first_float(
        r"^system\.cpu\.dcache\.overallMissRate::total\s+([0-9eE+\-.]+)",
        text,
    )

    squashing_cycles = parse_first_float(
        r"^system\.cpu\.decode\.status::Squashing\s+([0-9eE+\-.]+)",
        text,
    )

    return {
        "ipc": ipc,
        "cpi": cpi,
        "branch_count": branch_count,
        "branch_mispredict": branch_mispredict,
        "branch_mispredict_rate": branch_mispredict_rate,
        "l1d_miss_rate": l1d_miss_rate,
        "squashing_cycles": squashing_cycles,
    }


def infer_experiment_fields(exp_name: str):
    cpu_type = "O3CPU"
    rob = None
    issue_width = None

    if exp_name == "baseline_o3":
        cpu_type = "O3CPU"
        rob = DEFAULT_ROB
        issue_width = DEFAULT_ISSUE_WIDTH
    elif exp_name == "baseline_timing":
        cpu_type = "TimingSimpleCPU"
    elif exp_name.startswith("rob_"):
        rob = int(exp_name.split("_")[1])
        issue_width = DEFAULT_ISSUE_WIDTH
    elif exp_name.startswith("issue_"):
        rob = DEFAULT_ROB
        issue_width = int(exp_name.split("_")[1])

    return cpu_type, rob, issue_width


def compute_cost(rob: Optional[int], issue_width: Optional[int]) -> Optional[int]:
    if rob is None or issue_width is None:
        return None
    return ROB_COST_COEF * rob + ISSUE_WIDTH_COST_COEF * issue_width


def collect_results() -> pd.DataFrame:
    rows: List[Dict] = []

    for workload_dir in sorted(RESULT_DIR.iterdir()):
        if not workload_dir.is_dir():
            continue
        workload = workload_dir.name
        if workload == "plots":
            continue
        if workload not in WORKLOAD_TYPES:
            continue

        for exp_dir in sorted(workload_dir.iterdir()):
            if not exp_dir.is_dir():
                continue
            stats_path = exp_dir / "stats.txt"
            if not stats_path.exists():
                continue

            metrics = extract_metrics(stats_path)
            cpu_type, rob, issue_width = infer_experiment_fields(exp_dir.name)

            rows.append({
                "workload": workload,
                "workload_type": WORKLOAD_TYPES[workload],
                "experiment": exp_dir.name,
                "cpu_type": cpu_type,
                "rob": rob,
                "issue_width": issue_width,
                "ipc": metrics["ipc"],
                "cpi": metrics["cpi"],
                "branch_count": metrics["branch_count"],
                "branch_mispredict": metrics["branch_mispredict"],
                "branch_mispredict_rate": metrics["branch_mispredict_rate"],
                "l1d_miss_rate": metrics["l1d_miss_rate"],
                "squashing_cycles": metrics["squashing_cycles"],
                "cost": compute_cost(rob, issue_width),
                "stats_path": str(stats_path),
            })

    return pd.DataFrame(rows)


def save_dataframe(df: pd.DataFrame):
    out_csv = RESULT_DIR / "parsed_summary.csv"
    df.to_csv(out_csv, index=False)
    print(f"Saved parsed summary to: {out_csv}")


def plot_baseline_ipc(df: pd.DataFrame):
    base = df[df["experiment"].isin(["baseline_o3", "baseline_timing"])].copy()
    if base.empty:
        return

    workloads = list(base["workload"].drop_duplicates())
    x = range(len(workloads))

    o3_vals = []
    timing_vals = []

    for w in workloads:
        o3 = base[(base["workload"] == w) & (base["experiment"] == "baseline_o3")]["ipc"]
        tm = base[(base["workload"] == w) & (base["experiment"] == "baseline_timing")]["ipc"]
        o3_vals.append(float(o3.iloc[0]) if not o3.empty else 0.0)
        timing_vals.append(float(tm.iloc[0]) if not tm.empty else 0.0)

    plt.figure(figsize=(9, 5))
    width = 0.35
    plt.bar([i - width / 2 for i in x], o3_vals, width=width, label="O3CPU")
    plt.bar([i + width / 2 for i in x], timing_vals, width=width, label="TimingSimpleCPU")
    plt.xticks(list(x), workloads, rotation=20)
    plt.ylabel("IPC")
    plt.title("IPC Comparison")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "ipc.png", dpi=200)
    plt.close()


def plot_baseline_speedup(df: pd.DataFrame):
    base = df[df["experiment"].isin(["baseline_o3", "baseline_timing"])].copy()
    if base.empty:
        return

    workloads = list(base["workload"].drop_duplicates())
    speedups = []

    for w in workloads:
        o3 = base[(base["workload"] == w) & (base["experiment"] == "baseline_o3")]["ipc"]
        tm = base[(base["workload"] == w) & (base["experiment"] == "baseline_timing")]["ipc"]
        if not o3.empty and not tm.empty and float(tm.iloc[0]) != 0:
            speedups.append(float(o3.iloc[0]) / float(tm.iloc[0]))
        else:
            speedups.append(0.0)

    plt.figure(figsize=(8, 5))
    plt.bar(workloads, speedups)
    plt.ylabel("Speedup (O3 IPC / Timing IPC)")
    plt.title("Speedup")
    plt.xticks(rotation=20)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "speedup.png", dpi=200)
    plt.close()


def plot_rob_sweep(df: pd.DataFrame):
    rob_df = df[df["experiment"].str.startswith("rob_", na=False)].copy()
    if rob_df.empty:
        return

    plt.figure(figsize=(9, 6))
    for workload in sorted(rob_df["workload"].unique()):
        sub = rob_df[rob_df["workload"] == workload].sort_values("rob")
        plt.plot(sub["rob"], sub["ipc"], marker="o", label=workload)

    plt.xlabel("ROB Entries")
    plt.ylabel("IPC")
    plt.title("ROB Sweep")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "rob_sweep_ipc.png", dpi=200)
    plt.close()


def plot_issue_sweep(df: pd.DataFrame):
    issue_df = df[df["experiment"].str.startswith("issue_", na=False)].copy()
    if issue_df.empty:
        return

    plt.figure(figsize=(9, 6))
    for workload in sorted(issue_df["workload"].unique()):
        sub = issue_df[issue_df["workload"] == workload].sort_values("issue_width")
        plt.plot(sub["issue_width"], sub["ipc"], marker="o", label=workload)

    plt.xlabel("Issue Width")
    plt.ylabel("IPC")
    plt.title("Issue Width Sweep")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "issue_width_sweep_ipc.png", dpi=200)
    plt.close()


def plot_baseline_scatter(
    df: pd.DataFrame,
    x_col: str,
    filename: str,
    xlabel: str,
    title: str,
):
    plot_df = df[df["experiment"].isin(["baseline_o3", "baseline_timing"])].copy()
    plot_df = plot_df[plot_df[x_col].notna() & plot_df["ipc"].notna()]
    if plot_df.empty:
        return

    plt.figure(figsize=(8, 5))
    markers = {
        "baseline_o3": "o",
        "baseline_timing": "s",
    }

    for workload_type in sorted(plot_df["workload_type"].unique()):
        for exp in ["baseline_o3", "baseline_timing"]:
            sub = plot_df[
                (plot_df["workload_type"] == workload_type) &
                (plot_df["experiment"] == exp)
            ]
            if not sub.empty:
                plt.scatter(
                    sub[x_col],
                    sub["ipc"],
                    label=f"{workload_type}-{exp}",
                    marker=markers[exp],
                    s=70,
                )

    for _, row in plot_df.iterrows():
        plt.annotate(
            f'{row["workload"]}:{row["experiment"]}',
            (row[x_col], row["ipc"]),
            fontsize=7,
            xytext=(4, 4),
            textcoords="offset points",
        )

    plt.xlabel(xlabel)
    plt.ylabel("IPC")
    plt.title(title)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(PLOT_DIR / filename, dpi=200)
    plt.close()


def plot_cost_vs_ipc(df: pd.DataFrame):
    plot_df = df[(df["cpu_type"] == "O3CPU") & df["cost"].notna() & df["ipc"].notna()].copy()
    if plot_df.empty:
        return

    plt.figure(figsize=(8, 5))
    for workload_type in sorted(plot_df["workload_type"].unique()):
        sub = plot_df[plot_df["workload_type"] == workload_type]
        plt.scatter(sub["cost"], sub["ipc"], label=workload_type, s=60)

    best_points = []
    for workload in sorted(plot_df["workload"].unique()):
        sub = plot_df[plot_df["workload"] == workload].copy()
        if sub.empty:
            continue
        sub = sub.sort_values(["ipc", "cost"], ascending=[False, True])
        best_points.append(sub.iloc[0])

    for row in best_points:
        plt.annotate(
            f'{row["workload"]}:{row["experiment"]}',
            (row["cost"], row["ipc"]),
            fontsize=7,
            xytext=(4, 4),
            textcoords="offset points",
        )

    plt.xlabel("Cost")
    plt.ylabel("IPC")
    plt.title("Cost vs IPC")
    plt.legend()
    plt.tight_layout()
    plt.savefig(PLOT_DIR / "cost_vs_ipc.png", dpi=200)
    plt.close()


def main():
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    df = collect_results()
    if df.empty:
        print("No results found.")
        return

    save_dataframe(df)

    plot_baseline_ipc(df)
    plot_baseline_speedup(df)
    plot_rob_sweep(df)
    plot_issue_sweep(df)

    plot_baseline_scatter(
        df,
        x_col="l1d_miss_rate",
        filename="l1d_miss_vs_ipc_baseline.png",
        xlabel="L1D Overall Miss Rate",
        title="L1D Miss Rate vs IPC (Baseline Only)",
    )

    plot_baseline_scatter(
        df,
        x_col="branch_mispredict_rate",
        filename="branch_mispredict_vs_ipc_baseline.png",
        xlabel="Branch Mispredict Rate",
        title="Branch Mispredict Rate vs IPC (Baseline Only)",
    )

    plot_baseline_scatter(
        df,
        x_col="squashing_cycles",
        filename="squashing_vs_ipc_baseline.png",
        xlabel="Decode Squashing Cycles",
        title="Squashing vs IPC (Baseline Only)",
    )

    plot_cost_vs_ipc(df)

    print(f"Plots saved under: {PLOT_DIR}")


if __name__ == "__main__":
    main()