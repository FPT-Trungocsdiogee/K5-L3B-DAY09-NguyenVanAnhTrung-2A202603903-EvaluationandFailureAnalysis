"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []
    rows = pr.get("rows") or []
    base_rows = base.get("rows") or []
    man = pr.get("manifest") or {}
    base_man = base.get("manifest") or {}

    # 1. metric values must be finite numbers (NaN < min is False: a naive gate would pass it)
    for k, v in (pr.get("metrics") or {}).items():
        if v is None or isinstance(v, bool):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            problems.append(f"metric {k} is not a number: {v!r}")
            continue
        if not math.isfinite(f):
            problems.append(f"metric {k} is not finite: {v!r}")

    # 2. row count must match the manifest (dropped / duplicated rows)
    seeds = man.get("seeds") or []
    try:
        expected = int(man.get("items")) * len(seeds)
    except (TypeError, ValueError):
        expected = None
    if expected is None or len(rows) != expected:
        problems.append(f"rows: {len(rows)}, manifest says {man.get('items')} items x {len(seeds)} seeds = {expected}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append(f"{len(keys) - len(set(keys))} duplicated (item_id, seed) row(s)")

    # 3. same (item_id, seed) set, seeds and item count as the baseline (cherry-picked seeds/items)
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if set(keys) != base_keys:
        missing, extra = base_keys - set(keys), set(keys) - base_keys
        problems.append(f"(item_id, seed) set differs from baseline: {len(missing)} missing, {len(extra)} extra")
    if sorted(seeds) != sorted(base_man.get("seeds") or []):
        problems.append(f"seeds {seeds} differ from baseline {base_man.get('seeds')}")
    if man.get("items") != base_man.get("items"):
        problems.append(f"items {man.get('items')} differ from baseline {base_man.get('items')}")

    # 4. crashed graders: evaluator failures, or a graded metric that is None/NaN in a row
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s)")
    graded = {m["id"] for m in spec.get("metrics", [])}
    graded |= {s["metric"] for s in spec.get("slices") or [] if s.get("metric")}
    graded = {g for g in graded if any(g in r for r in rows) or any(g in r for r in base_rows)}
    bad: dict[str, int] = {}
    for r in rows:
        for g in graded:
            v = r.get(g)
            if v is None or (isinstance(v, float) and not math.isfinite(v)):
                bad[g] = bad.get(g, 0) + 1
    for g, n in sorted(bad.items()):
        problems.append(f"metric {g} is None/NaN in {n} row(s) (crashed grader?)")

    # 5. an item's slice tags must match the baseline (relabelling hides a slice regression)
    def _tags(rs: list[dict]) -> dict:
        out: dict = {}
        for r in rs:
            out.setdefault(r.get("item_id"), set()).update(r.get("slices") or [])
        return out

    pt, bt = _tags(rows), _tags(base_rows)
    relabelled = sorted(str(i) for i in set(pt) & set(bt) if pt[i] != bt[i])
    if relabelled:
        problems.append(f"slice tags differ from baseline for item(s): {', '.join(relabelled[:5])}")

    # 6. ratchet against the spec on main
    if base_spec is not None:
        problems += _ratchet(spec, base_spec)
    return problems


def _looser(th: dict, bth: dict) -> list[str]:
    out = []
    if "max" in bth and ("max" not in th or th["max"] > bth["max"]):
        out.append(f"max {bth['max']} -> {th.get('max')}")
    if "min" in bth and ("min" not in th or th["min"] < bth["min"]):
        out.append(f"min {bth['min']} -> {th.get('min')}")
    if "max_increase" in bth and ("max_increase" not in th or th["max_increase"] > bth["max_increase"]):
        out.append(f"max_increase {bth['max_increase']} -> {th.get('max_increase')}")
    if bth.get("no_significant_drop") and not th.get("no_significant_drop"):
        out.append("no_significant_drop removed")
    return out


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version: thresholds may only get stricter (metrics and slices)."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    problems: list[str] = []
    cur = {m["id"]: m for m in spec.get("metrics", [])}
    for bm in base_spec.get("metrics", []):
        m = cur.get(bm["id"])
        if m is None:
            problems.append(f"ratchet: metric {bm['id']} removed")
            continue
        if bm.get("blocking") and not m.get("blocking"):
            problems.append(f"ratchet: metric {bm['id']} became non-blocking")
        problems += [f"ratchet: metric {bm['id']} loosened: {d}"
                     for d in _looser(m.get("threshold") or {}, bm.get("threshold") or {})]
    cur_sl = {(s.get("name"), s.get("metric")): s for s in spec.get("slices") or []}
    for bs in base_spec.get("slices") or []:
        label = f"slice {bs.get('name')}/{bs.get('metric')}"
        s = cur_sl.get((bs.get("name"), bs.get("metric")))
        if s is None:
            problems.append(f"ratchet: {label} removed")
            continue
        if bs.get("blocking") and not s.get("blocking"):
            problems.append(f"ratchet: {label} became non-blocking")
        problems += [f"ratchet: {label} loosened: {d}" for d in _looser(s, bs)]
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        a = per_item(pr, metric, slice_name=name)
        b = per_item(base, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict, note = "missing", "no rows in slice"
        else:
            val = sum(a.values()) / len(a)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            keys = sorted(set(a) & set(b))
            if sl.get("no_significant_drop") and keys:
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000),
                                                   rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        th = {k: sl[k] for k in ("min", "no_significant_drop") if k in sl}
        shown = "None" if val is None else f"{val:.4f}"
        lines.append(f"  {sid:<22} {shown:<8} {json.dumps(th):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, warned, lines = [], [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok":
            # a non-blocking failure (or missing value) must still show up in the report summary
            (blocked if m.get("blocking") else warned).append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    if warned:
        lines.append(f"  {len(warned)} warning(s), non-blocking: {', '.join(warned)}")
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
