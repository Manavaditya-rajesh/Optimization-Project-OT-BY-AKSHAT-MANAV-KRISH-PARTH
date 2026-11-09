"""Generate the follow-up report from complete, independently verified records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", default="enhancement_validation")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    folder = root / "results" / args.study
    data = json.loads((folder / "summary.json").read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    verification = json.loads((folder / "verification.json").read_text())
    assert verification["status"] == "PASS"
    tests_path=folder / "tests_before_validation.txt"
    tests_summary=tests_path.read_text().strip().splitlines()[-1] if tests_path.exists() else "No test log supplied for this study"
    lookup = {(r["size"],r["protocol"],r["method"]):r for r in data["summary"]}
    lines = ["# Enhancing the timetable optimizer: held-out follow-up study", "",
             "This report uses saved synthetic measurements. Historical benchmark records remain unchanged. "
             "The follow-up changes search operators and selection policies, while preserving the original "
             "generator, constraints, objectives, normalization, hypervolume reference and greedy scheduling policy.", "",
             "All objectives are minimized: student internal teaching gaps plus half faculty gaps (excluding lunch); "
             "duration-weighted unused room-seat fraction; and population SD of faculty teaching load divided "
             "by weekly allowance. Hard constraints are never traded against these quality measures.", "",
             "## What changed and why", "",
             "Over 90% of the original enhanced method's raw offspring required repair. "
             "The new method seeds the full population feasibly and replaces destructive categorical crossover "
             "with resource-checked mutation. It genuinely retains NSGA-II rank/crowding tournaments and "
             "elitist parent–offspring survival; it is explicitly a mutation-only memetic NSGA-II variant.", "",
             "Five neighborhoods move sessions, improve room assignments, swap events, jointly reinsert an "
             "offering under a new teacher, or exchange teachers of two offerings. A bounded deterministic "
             "branch-and-bound step reassigns up to eight whole offerings at fixed times/rooms. With common "
             "weekly allowances, minimizing the squared load sum minimizes true workload SD. Node limits "
             "prevent an unbounded local solve; no global optimality guarantee is implied. Faculty compactness "
             "can worsen, so every feasible proposal is evaluated on all three original objectives.", "",
             "The scalar-local ablation receives the same initial constructive population and proposal family. "
             "It uses independent fixed positive scalar directions instead of the NSGA-II selection/survival bundle. "
             "This tests the bundle, not a single causal component. Later parent states and candidate streams diverge.", "",
             "## Development and frozen validation", "",
             "Development used previously declared seeds 9000+. A twelve-run pilot at 240 full evaluations "
             "covered one instance/solver seed (9000) at each size and four methods. Those exploratory values "
             "are separate from held-out results; the larger development configuration is supplied but was "
             "not executed in full. No operator rates, instance settings or quality indicators were changed "
             "in response to validation outcomes.", "",
             f"Frozen source SHA-256: `{manifest['source_sha256']}`. The manifest records exact "
             "configuration/runtime versions; `source_snapshot/` preserves the measured package files. "
             f"Saved pre-validation test record: **{tests_summary}**.", "",
             "| Size | Instance seeds | Solver seeds | Evaluations per run | Wall-time allowance |",
             "|---|---|---|---:|---:|"]
    config = manifest["config"]
    for scenario in config["scenarios"]:
        lines.append(f"| {scenario['size']} | {scenario.get('instance_seeds',config['instance_seeds'])} | "
                     f"{scenario.get('solver_seeds',config['solver_seeds'])} | {scenario['budget']} | {scenario['wall_time_seconds']} s |")
    lines += ["", "Four methods were compared: unchanged multi-start greedy, original enhanced NSGA-II, "
              "feasible memetic NSGA-II and scalar-local search. Every initialization and full candidate check "
              "is charged. Direct resource checks and partial workload search are timed rather than relabeled "
              "as full evaluations. Initializations are included, constructor caches reset per run, and methods "
              "run sequentially in rotated order. Native algorithm bookkeeping plus a common observer are timed.", "",
              "Wall-time quality includes only full objective results available by the common allocation. "
              "Bounded atomic work can overrun the deadline; late results receive no quality credit, actual "
              "overrun is recorded, and no background optimizer continues after the run. Timing hardware/load "
              "still limit generalization. Evaluation and wall-time protocols answer different resource questions.", "",
              "## Measured comparison with greedy", "",
              "| Size | Protocol | Greedy HV | New NSGA-II HV | Relative change | Paired new wins/ties/losses |",
              "|---|---|---:|---:|---:|---|"]
    primary_wins = []
    for size in ["small","medium","large"]:
        for protocol in ["evaluations","wall_time"]:
            g,m = lookup[size,protocol,"greedy"],lookup[size,protocol,"memetic"]
            relative = (m["hypervolume_mean"]/g["hypervolume_mean"]-1)*100 if g["hypervolume_mean"] else None
            result = data["comparisons"][f"{size}/{protocol}/memetic_vs_greedy"]["paired_run_descriptive"]
            change = f"{relative:+.2f}%" if relative is not None else "undefined"
            lines.append(f"| {size} | {protocol} | {g['hypervolume_mean']:.6f} | {m['hypervolume_mean']:.6f} | "
                         f"{change} | {result['wins']}/{result['ties']}/{result['losses']} |")
            if size != "small":
                primary_wins.append(m["hypervolume_mean"] > g["hypervolume_mean"])
    lines += ["", ("The new population method had higher mean hypervolume on both primary sizes under both resource protocols."
                    if all(primary_wins) else "Primary-size outcomes are mixed; the enhancement does not win every aggregate resource comparison."), "",
              "These are observed comparisons on the declared synthetic instances, not universal superiority or "
              "global Pareto optimality. Repeated solver seeds are clustered within instances. Three independent "
              "instances per primary size give low statistical power: even three consistent instance-mean wins "
              "yield a minimum two-sided sign-test p-value of 0.25. The one small validation instance is a "
              "regression case, and every unfavorable small result is retained.", "",
              "## Does NSGA-II selection add value?", "",
              "| Size | Protocol | New NSGA-II HV | Scalar-local HV | NSGA-II wins/ties/losses |",
              "|---|---|---:|---:|---|"]
    for size in ["small","medium","large"]:
        for protocol in ["evaluations","wall_time"]:
            m,l = lookup[size,protocol,"memetic"],lookup[size,protocol,"ablation_local"]
            result = data["comparisons"][f"{size}/{protocol}/memetic_vs_ablation_local"]["paired_run_descriptive"]
            lines.append(f"| {size} | {protocol} | {m['hypervolume_mean']:.6f} | {l['hypervolume_mean']:.6f} | "
                         f"{result['wins']}/{result['ties']}/{result['losses']} |")
    lines += ["", "Interpret this ablation separately from beating greedy. If local search matches or exceeds "
              "NSGA-II, the feasible-initialization/variation/intensification bundle deserves the credit; the evidence "
              "does not establish a benefit for population selection on that condition. This study does not "
              "separately isolate full feasible initialization, each neighborhood and faculty branch-and-bound.", "",
              "## Full result table", "", (folder / "summary.md").read_text().split("\n",1)[1], "",
              "## Raw objective changes", "",
              "Means below are each run's best feasible value per objective, conditional on runs with a feasible archive. Columns can belong to different "
              "timetables, so they are not one simultaneously attained ideal vector. Final schedule exports "
              "show whole feasible alternatives with explicit preferences.", "",
              "| Size | Protocol | Method | Best gaps, mean | Best unused capacity, mean | Best relative-load SD, mean |",
              "|---|---|---|---:|---:|---:|"]
    for size in ["small","medium","large"]:
        for protocol in ["evaluations","wall_time"]:
            for method in ["greedy","memetic"]:
                row=lookup[size,protocol,method]
                values=row["mean_run_best_objectives_conditional"]
                if values:
                    lines.append(f"| {size} | {protocol} | {method} | {values[0]:.3f} | {values[1]:.6f} | {values[2]:.6f} |")
    lines += ["", "A hypervolume gain can come from useful workload-balanced alternatives while room fit or "
              "faculty gaps worsen. The conservative fixed gap scale makes some gap changes weakly visible; "
              "a coordinator should examine the raw objectives and actual grids instead of treating HV as an "
              "administrative utility. Reference/scale sensitivity remains future work.", "",
              "## Verification and reproducibility", "",
              f"Independent post-search verification rechecked **{verification['runs']} runs**, "
              f"**{verification['archived_feasible_schedules']} archived feasible schedules**, and "
              f"**{verification['certificates']} separate feasibility certificates**. It reconstructed every "
              f"cutoff front from on-time recorded discoveries and verified exclusion of "
              f"**{verification['excluded_late_evaluations']} late completed evaluations**. "
              f"Empty feasible archives: **{verification['empty_archives']}**. "
              "Verification uses the common checker outside search; operator constraints, hand calculations, "
              "exact workload-subproblem tests and the original CP-SAT checks supply additional cross-checks.", "",
              "```bash", "python -m pytest -q", f"python main.py compare --config experiments/enhancement_validation.json --resume",
              f"python experiments/verify_enhancement.py --study {args.study}",
              f"python experiments/plot_enhancement.py --study {args.study}",
              f"python experiments/export_enhancement.py --study {args.study}",
              f"python experiments/report_enhancement.py --study {args.study}", "```", "",
              "Resume requires the measured source, configuration and runtime. For new measurements, copy "
              "the JSON configuration, change its `name`, and run `compare` with that new file. "
              "Wall-time trajectories naturally vary between machines. Historical `results/benchmark/` "
              "remains associated with published source commit `9947d9d`; use its verification/plot scripts "
              "or a new study name rather than trying to resume it under changed source.", "",
              "## Remaining limitations", "",
              "All data are still planted-feasible synthetic college instances, with disjoint atomic cohorts, "
              "generic lab types, equal periods and a deterministic repeating week. No real-institution or "
              "ITC validation is claimed. Bounded faculty search supports common weekly allowances; it returns "
              "unchanged for unequal allowances, while the other feasible moves remain usable. Historical small "
              "instances with a certified singleton ideal cannot be strictly improved beyond that ideal. The new "
              "small instance must be assessed on its own, and no new global-optimality claim is inferred from a plot.", "",
              "No development or validation result authorizes a broad statistical or operational superiority claim. "
              "Larger independent instance samples, tighter resource distributions, component ablations and "
              "coordinator-defined preference studies remain important. The follow-up was first reviewed "
              "locally and is published with the final report/presentation under explicit user authorization. "
              "Publication does not establish administrative approval or weekly student participation."]
    whole = ["## Whole-timetable examples", "",
             "First configured instance/solver seed of each primary size, wall-time protocol. "
             "Both methods use the same stated lexicographic preference: gaps/room/SD or SD/gaps/room. "
             "These are complete schedules, so all columns are attained together.", "",
             "| Instance | Method | Preference | Gaps | Unused capacity | Load SD | Student gaps | Faculty gaps | Faculty load range |",
             "|---|---|---|---:|---:|---:|---:|---:|---|"]
    representatives=json.loads((folder / "representatives.json").read_text())
    for row in representatives:
        vals=row["objectives"]
        metrics=row["metrics"]
        loads=list(metrics["faculty_loads"].values())
        whole.append(f"| {row['instance']} | {row['method']} | {row['selection']} | {vals[0]:g} | {vals[1]:.6f} | {vals[2]:.6f} | "
                     f"{metrics['student_gaps']} | {metrics['faculty_gaps']} | {min(loads)}–{max(loads)} |")
    whole += ["", "![Medium sampled anytime prefixes](../figures/"+args.study+"/medium_anytime.png)",
              "![Large sampled anytime prefixes](../figures/"+args.study+"/large_anytime.png)", "",
              "Shading is descriptive one-SD variability across solver runs, not an independent-instance "
              "confidence interval. Pareto figures are saved per fixed instance; they pool observed per-run "
              "archives without asserting a global front.", ""]
    proof=["## Additional mathematical workload checks", "",
           "With equal weekly allowances and fixed integer total teaching load, the unconstrained "
           "minimum squared-load sum assigns floor(Q/m) or ceil(Q/m) periods to each teacher. "
           "Moving one unit between loads differing by at least two reduces their square sum. "
           "Dropping offering indivisibility, eligibility and time interactions makes this a valid "
           "relaxation bound. An actual feasible timetable attaining it certifies the workload objective's "
           "global minimum, even though it does not certify the other objectives or a global Pareto front. "
           "Nonattainment of this loose bound does not prove a schedule nonoptimal.", "",
           "| Instance | Integer squared-load lower bound | Best observed squared loads | Methods with a feasible attaining certificate |",
           "|---|---:|---:|---|"]
    for identity,bound in verification.get("workload_integer_relaxation",{}).items():
        methods=sorted({c["method"] for c in bound["attaining_certificates"]})
        proof.append(f"| {identity} | {bound['integer_sum_squares_lower_bound']} | {bound['best_observed_integer_sum_squares']} | {', '.join(methods) or 'No attainment certificate'} |")
    proof += ["", "The verification JSON stores the exact variance fractions, attaining run/index references "
              "and integer load vectors. These checks were added to post-study verification; they are not "
              "a changed search objective, a solver seed, or a replacement for the predeclared HV comparison.", ""]
    small_path=folder / "small_ideal_certificates.json"
    if small_path.exists():
        small=json.loads(small_path.read_text())
        for identity,record in small.items():
            if record["status"] == "CERTIFIED_GLOBAL_IDEAL_VECTOR":
                certificate=record["attaining_feasible_certificate"]
                proof += [f"A separate stronger offering-partition certificate also establishes the singleton "
                          f"global ideal `(0,14/55,sqrt(1/450))` for **{identity}**, attained in "
                          f"`{certificate['run']}` at archive index {certificate['archive_index']}. "
                          "This exact integer/rational proof is in `small_ideal_certificates.json`. "
                          "One successful small run does not erase the unfavorable small-case mean or prove reliable attainment across seeds.", ""]
    output=root / "report" / "enhancement_report.md"
    text="\n".join(lines)+"\n"
    text=text.replace("## Verification and reproducibility", "\n".join(whole)+"\n## Verification and reproducibility")
    text=text.replace("## Remaining limitations", "\n".join(proof)+"\n## Remaining limitations")
    output.write_text(text)
    print(f"Generated {output.relative_to(root)}")


if __name__ == "__main__":
    main()
