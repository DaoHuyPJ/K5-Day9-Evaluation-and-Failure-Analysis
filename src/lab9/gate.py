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
from lab9.graders import GRADERS


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
    graded = _graded_metrics(spec, base)
    for who, rep in (("PR", pr), ("baseline", base)):
        problems += [f"{who}: {p}" for p in _report_problems(rep, spec, graded)]
    problems += _coverage_problems(pr, base)
    problems += _slice_tag_problems(pr, base)
    if base_spec is not None:
        problems += _ratchet_problems(spec, base_spec, pr, base)
    return problems


def _finite(v) -> bool:
    return not isinstance(v, float) or math.isfinite(v)


def _graded_metrics(spec: dict, base: dict) -> list[str]:
    """Spec metrics scored row by row: those a grader produces, or that the baseline rows carry."""
    base_keys = {k for r in base.get("rows") or [] for k in r}
    return [m["id"] for m in spec["metrics"] if m["id"] in GRADERS or m["id"] in base_keys]


def _report_problems(rep: dict, spec: dict, graded: list[str]) -> list[str]:
    """One report on its own: finite numbers, full grid, no duplicates, no crashed graders,
    and headline metrics that are what its own rows say (no hand-edited numbers)."""
    out: list[str] = []
    rows, man = rep.get("rows") or [], rep.get("manifest") or {}
    out += [f"metric {k} = {v!r} is not finite" for k, v in (rep.get("metrics") or {}).items() if not _finite(v)]
    want = man.get("items", 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        out.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        out.append(f"duplicated (item, seed) rows: {', '.join(f'{i}@{s}' for i, s in dup[:5])}")
    seeds = set(man.get("seeds") or [])
    off = sorted({str(s) for _, s in keys if s not in seeds})
    if off:
        out.append(f"rows with seeds not in the manifest: {', '.join(off)}")
    if rep.get("evaluator_failures"):
        out.append(f"{len(rep['evaluator_failures'])} evaluator failure(s), first: {rep['evaluator_failures'][0]}")
    for m in graded:
        bad = [f"{r.get('item_id')}@{r.get('seed')}" for r in rows if not isinstance(r.get(m), bool)]
        if bad:
            out.append(f"{len(bad)} row(s) with no boolean score for graded metric {m} (e.g. {bad[0]}): "
                       f"a crashed grader drops out of the mean")
    for r in rows:
        if "cost" in r and not (isinstance(r["cost"], (int, float)) and _finite(float(r["cost"]))):
            out.append(f"row {r.get('item_id')}@{r.get('seed')} cost {r['cost']!r} is not a finite number")
            break
    out += _recompute_problems(rep, spec, graded)
    return out


def _recompute_problems(rep: dict, spec: dict, graded: list[str]) -> list[str]:
    from lab9.eval import aggregate

    rows, reported = rep.get("rows") or [], rep.get("metrics") or {}
    present = [m for m in graded if rows and all(isinstance(r.get(m), bool) for r in rows)]
    if not present:
        return []
    kinds = {m["id"]: m.get("kind") for m in spec["metrics"]}
    if all("cost" in r for r in rows):
        expect = aggregate(rows, present, k_values=spec.get("pass_k", []))
    else:   # rows without cost: recompute only the per-row metrics
        expect = {}
        for m in present:
            vals = [r[m] for r in rows]
            expect[m] = sum(vals) if kinds.get(m) == "safety" or m in ("secret_leak", "approval_bypass") \
                else round(sum(vals) / len(vals), 4)
    out = []
    for k, want in expect.items():
        got = reported.get(k)
        if isinstance(want, (int, float)) and isinstance(got, (int, float)) and _finite(got):
            if not math.isclose(float(got), float(want), abs_tol=1e-4):
                out.append(f"metric {k} = {got} but its rows give {want}")
        elif isinstance(want, (int, float)) and k in kinds and got is None:
            out.append(f"metric {k} missing but its rows give {want}")
    return out


def _coverage_problems(pr: dict, base: dict) -> list[str]:
    """PR and baseline must cover the same (item, seed) grid: no cherry-picked seeds or items."""
    out = []
    pm, bm = pr.get("manifest") or {}, base.get("manifest") or {}
    if sorted(pm.get("seeds") or []) != sorted(bm.get("seeds") or []):
        out.append(f"seeds {pm.get('seeds')} differ from the baseline's {bm.get('seeds')}")
    if pm.get("items") != bm.get("items"):
        out.append(f"{pm.get('items')} items, baseline has {bm.get('items')}")
    a = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows") or []}
    b = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if a != b:
        miss, extra = sorted(b - a, key=str), sorted(a - b, key=str)
        out.append(f"(item, seed) set differs from the baseline: {len(miss)} missing "
                   f"{' '.join(f'{i}@{s}' for i, s in miss[:5])}, {len(extra)} extra "
                   f"{' '.join(f'{i}@{s}' for i, s in extra[:5])}".rstrip())
    return out


def _slice_tags(rep: dict) -> tuple[dict[str, frozenset], list[str]]:
    tags: dict[str, frozenset] = {}
    clash = []
    for r in rep.get("rows") or []:
        t = frozenset(r.get("slices") or [])
        if tags.setdefault(r.get("item_id"), t) != t:
            clash.append(r.get("item_id"))
    return tags, sorted(set(clash), key=str)


def _slice_tag_problems(pr: dict, base: dict) -> list[str]:
    pt, pclash = _slice_tags(pr)
    bt, _ = _slice_tags(base)
    out = [f"item {i}: slice tags differ between its own rows" for i in pclash]
    for i in sorted(set(pt) & set(bt), key=str):
        if pt[i] != bt[i]:
            out.append(f"item {i}: slice tags {sorted(pt[i])} differ from the baseline's {sorted(bt[i])}")
    return out


def _looser(new: dict, old: dict) -> list[str]:
    """Threshold fields of `new` that are laxer than `old`."""
    out = []
    if "max" in old and not ("max" in new and new["max"] <= old["max"]):
        out.append(f"max {old['max']} -> {new.get('max')}")
    if "min" in old and not ("min" in new and new["min"] >= old["min"]):
        out.append(f"min {old['min']} -> {new.get('min')}")
    if "max_increase" in old and not ("max_increase" in new and new["max_increase"] <= old["max_increase"]):
        out.append(f"max_increase {old['max_increase']} -> {new.get('max_increase')}")
    if old.get("no_significant_drop") and not new.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    return out


def _ratchet_problems(spec: dict, base_spec: dict, pr: dict, base: dict) -> list[str]:
    """Same eval set => thresholds may only get stricter. Bumping the version label while the eval
    set bytes are unchanged does not open a new version."""
    same_set = (pr.get("manifest") or {}).get("eval_set_sha") == (base.get("manifest") or {}).get("eval_set_sha")
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        if not same_set:
            return []
        out = [f"RATCHET eval_set_version {base_spec.get('eval_set_version')!r} -> "
               f"{spec.get('eval_set_version')!r} but the eval set is unchanged"]
    else:
        out = []
    new = {m["id"]: m for m in spec["metrics"]}
    for m in base_spec["metrics"]:
        n = new.get(m["id"])
        if n is None:
            out.append(f"RATCHET metric {m['id']} removed")
            continue
        if m.get("blocking") and not n.get("blocking"):
            out.append(f"RATCHET metric {m['id']} no longer blocking")
        if m.get("kind") == "safety" and n.get("kind") != "safety":
            out.append(f"RATCHET metric {m['id']} kind safety -> {n.get('kind')}")
        out += [f"RATCHET metric {m['id']} {x}" for x in _looser(n.get("threshold") or {}, m.get("threshold") or {})]
    new_sl = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        sid = f"slice:{s['name']}/{s['metric']}"
        n = new_sl.get((s["name"], s["metric"]))
        if n is None:
            out.append(f"RATCHET {sid} removed")
            continue
        if s.get("blocking") and not n.get("blocking"):
            out.append(f"RATCHET {sid} no longer blocking")
        out += [f"RATCHET {sid} {x}" for x in _looser(n, s)]
    ob, nb = base_spec.get("bootstrap") or {}, spec.get("bootstrap") or {}
    if nb.get("confidence", 0.95) > ob.get("confidence", 0.95):
        out.append(f"RATCHET bootstrap confidence {ob.get('confidence', 0.95)} -> {nb.get('confidence')} widens the CI")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        sid = f"slice:{name}/{metric}"
        a = per_item(pr, metric, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"            # an empty slice cannot vouch for anything
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in s and val < s["min"]:
                verdict = "fail"
            if s.get("no_significant_drop"):
                b = per_item(base, metric, slice_name=name)
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000),
                                                       rng=bs.get("rng", 2027),
                                                       confidence=bs.get("confidence", 0.95))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<22} {val!s:<8} n={len(a):<3} {json.dumps(th):<34} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
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
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
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
