#!/usr/bin/env python3
import csv
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------
# Config
GEM5_BIN = Path("../build/X86/gem5.opt")
SE_SCRIPT = Path("../configs/deprecated/example/se.py")
WORKLOAD_DIR = Path("workloads")
RESULT_DIR = Path("results")

COMMON_ARGS = [
    "--caches",
    "--l2cache",
]

WORKLOADS = [
    ("compute1", "compute"),
    ("compute2", "compute"),
    ("memory1", "memory"),
    ("memory2", "memory"),
    ("branch1", "branch"),
]

ROB_POINTS = [32, 64, 128, 192]
ISSUE_WIDTH_POINTS = [2, 4, 6, 8]

# Cost model
ROB_COST_COEF = 1
ISSUE_WIDTH_COST_COEF = 16
BUDGET = 220

DEFAULT_ROB = 128
DEFAULT_ISSUE_WIDTH = 4


@dataclass
class RunResult:
    workload: str
    workload_type: str
    experiment: str
    cpu_type: str
    rob: Optional[int]
    issue_width: Optional[int]
    ipc: Optional[float]
    cpi: Optional[float]
    branch_count: Optional[float]
    branch_mispredict: Optional[float]
    branch_mispredict_rate: Optional[float]
    l1d_miss_rate: Optional[float]
    squashing_cycles: Optional[float]
    stats_path: str
    cost: Optional[int]


def run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> None:
    print("\n[CMD]", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_file_exists(path: Path, description: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{description} not found: {path}")


def compile_workloads() -> None:
    ensure_file_exists(WORKLOAD_DIR, "Workload directory")
    for name, _wtype in WORKLOADS:
        src = WORKLOAD_DIR / f"{name}.c"
        exe = WORKLOAD_DIR / name
        if exe.exists() and os.access(exe, os.X_OK):
            print(f"[OK] executable exists: {exe}")
            continue
        if not src.exists():
            raise FileNotFoundError(f"Missing workload source: {src}")
        print(f"[BUILD] {src} -> {exe}")
        run_cmd(["gcc", "-O2", str(src), "-o", str(exe)])


def clean_output_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def gem5_run(
    outdir: Path,
    workload_bin: Path,
    cpu_type: str,
    extra_params: Optional[List[str]] = None,
) -> None:
    clean_output_dir(outdir)

    cmd = [
        str(GEM5_BIN),
        "-d", str(outdir),
        str(SE_SCRIPT),
        "--cmd", str(workload_bin),
        "--cpu-type", cpu_type,
    ] + COMMON_ARGS

    if extra_params:
        cmd += extra_params

    run_cmd(cmd)


def parse_first_float(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def read_stats(stats_path: Path) -> str:
    ensure_file_exists(stats_path, "stats.txt")
    return stats_path.read_text(errors="ignore")


def extract_metrics(stats_path: Path) -> Dict[str, Optional[float]]:
    text = read_stats(stats_path)

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


def compute_cost(rob: Optional[int], issue_width: Optional[int]) -> Optional[int]:
    if rob is None or issue_width is None:
        return None
    return ROB_COST_COEF * rob + ISSUE_WIDTH_COST_COEF * issue_width


def make_run_result(
    workload: str,
    workload_type: str,
    experiment: str,
    cpu_type: str,
    rob: Optional[int],
    issue_width: Optional[int],
    stats_path: Path,
) -> RunResult:
    metrics = extract_metrics(stats_path)
    return RunResult(
        workload=workload,
        workload_type=workload_type,
        experiment=experiment,
        cpu_type=cpu_type,
        rob=rob,
        issue_width=issue_width,
        ipc=metrics["ipc"],
        cpi=metrics["cpi"],
        branch_count=metrics["branch_count"],
        branch_mispredict=metrics["branch_mispredict"],
        branch_mispredict_rate=metrics["branch_mispredict_rate"],
        l1d_miss_rate=metrics["l1d_miss_rate"],
        squashing_cycles=metrics["squashing_cycles"],
        stats_path=str(stats_path),
        cost=compute_cost(rob, issue_width),
    )


def write_summary_csv(results: List[RunResult], out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "workload",
            "workload_type",
            "experiment",
            "cpu_type",
            "rob",
            "issue_width",
            "ipc",
            "cpi",
            "branch_count",
            "branch_mispredict",
            "branch_mispredict_rate",
            "l1d_miss_rate",
            "squashing_cycles",
            "cost",
            "stats_path",
        ])
        for r in results:
            writer.writerow([
                r.workload,
                r.workload_type,
                r.experiment,
                r.cpu_type,
                r.rob,
                r.issue_width,
                r.ipc,
                r.cpi,
                r.branch_count,
                r.branch_mispredict,
                r.branch_mispredict_rate,
                r.l1d_miss_rate,
                r.squashing_cycles,
                r.cost,
                r.stats_path,
            ])


def select_best_under_budget(results: List[RunResult], out_csv: Path) -> None:
    grouped: Dict[str, List[RunResult]] = {}
    for r in results:
        if r.cpu_type != "O3CPU":
            continue
        if r.cost is None or r.ipc is None:
            continue
        if r.cost > BUDGET:
            continue
        grouped.setdefault(r.workload, []).append(r)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "workload",
            "selected_experiment",
            "rob",
            "issue_width",
            "ipc",
            "cost",
            "branch_mispredict_rate",
            "l1d_miss_rate",
            "squashing_cycles",
            "stats_path",
        ])

        for workload, items in grouped.items():
            items_sorted = sorted(
                items,
                key=lambda x: (
                    -1e30 if x.ipc is None else -x.ipc,
                    1e30 if x.cost is None else x.cost,
                )
            )
            best = items_sorted[0]
            writer.writerow([
                workload,
                best.experiment,
                best.rob,
                best.issue_width,
                best.ipc,
                best.cost,
                best.branch_mispredict_rate,
                best.l1d_miss_rate,
                best.squashing_cycles,
                best.stats_path,
            ])


def main() -> None:
    ensure_file_exists(GEM5_BIN, "gem5 binary")
    ensure_file_exists(SE_SCRIPT, "se.py script")
    compile_workloads()

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    all_results: List[RunResult] = []

    #--------------------------------------------------------
    #
    # O3 baseline + in-order baseline
    
    for workload, wtype in WORKLOADS:
        workload_bin = WORKLOAD_DIR / workload
    
        o3_out = RESULT_DIR / workload / "baseline_o3"
        gem5_run(o3_out, workload_bin, "O3CPU")
        all_results.append(
            make_run_result(
                workload, wtype, "baseline_o3", "O3CPU",
                DEFAULT_ROB, DEFAULT_ISSUE_WIDTH,
                o3_out / "stats.txt"
            )
        )
    
        timing_out = RESULT_DIR / workload / "baseline_timing"
        gem5_run(timing_out, workload_bin, "TimingSimpleCPU")
        all_results.append(
            make_run_result(
                workload, wtype, "baseline_timing", "TimingSimpleCPU",
                None, None,
                timing_out / "stats.txt"
            )
        )

    #--------------------------------------------------------
    #2) Sweep ROB entries
    
    for workload, wtype in WORKLOADS:
        workload_bin = WORKLOAD_DIR / workload
        for rob in ROB_POINTS:
            exp_name = f"rob_{rob}"
            outdir = RESULT_DIR / workload / exp_name
            gem5_run(
                outdir,
                workload_bin,
                "O3CPU",
                extra_params=[f'--param=system.cpu[0].numROBEntries={rob}']
            )
            all_results.append(
                make_run_result(
                    workload, wtype, exp_name, "O3CPU",
                    rob, DEFAULT_ISSUE_WIDTH,
                    outdir / "stats.txt"
                )
            )

    # --------------------------------------------------------
    # 3) Sweep issue width
    for workload, wtype in WORKLOADS:
        workload_bin = WORKLOAD_DIR / workload
        for issue_width in ISSUE_WIDTH_POINTS:
            exp_name = f"issue_{issue_width}"
            outdir = RESULT_DIR / workload / exp_name
            gem5_run(
                outdir,
                workload_bin,
                "O3CPU",
                extra_params=[f'--param=system.cpu[0].issueWidth={issue_width}']
            )
            all_results.append(
                make_run_result(
                    workload, wtype, exp_name, "O3CPU",
                    DEFAULT_ROB, issue_width,
                    outdir / "stats.txt"
                )
            )

    # --------------------------------------------------------
    # 4) Write outputs
    summary_csv = RESULT_DIR / "summary_issue_only.csv"
    write_summary_csv(all_results, summary_csv)

    best_csv = RESULT_DIR / "best_under_budget_issue_only.csv"
    select_best_under_budget(all_results, best_csv)

    print("\n============================================================")
    print("Issue-width sweep finished.")
    print(f"Summary CSV: {summary_csv}")
    print(f"Best-under-budget CSV: {best_csv}")
    print("Cost model:")
    print(f"  cost = {ROB_COST_COEF} * ROB + {ISSUE_WIDTH_COST_COEF} * issueWidth")
    print(f"  budget = {BUDGET}")
    print("============================================================")


if __name__ == "__main__":
    main()