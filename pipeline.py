"""Repair group leakage while preserving complete groups and measuring class balance."""

import csv
import io
import json
import math
import re
from collections import Counter, defaultdict

TITLE = "Sample Split Auditor"
DESCRIPTION = "Audit group overlap across machine-learning splits and export a group-intact repaired manifest with class-balance measurements."
PROMPT = "Explain leaking groups and stratification tradeoffs using group size, split counts and decision evidence. Class proportions cannot establish independence, label quality or model performance."


def identifier(value, field="id"):
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,119}", value
    ):
        raise ValueError(
            f"Invalid {field}: use a short stable identifier without spaces."
        )
    return value


def objects(value, field, cap=500):
    if (
        not isinstance(value, list)
        or len(value) > cap
        or any(not isinstance(row, dict) for row in value)
    ):
        raise ValueError(f"{field} must be an array of at most {cap} objects.")
    return value


def csv_file(columns, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue()


def json_file(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def selected(evidence, approved):
    available = {item["id"]: item for item in evidence["candidates"]}
    seen = set()
    result = []
    for item in approved:
        key = item["id"]
        if key not in available or key in seen:
            raise ValueError("Approval contains an unknown or duplicate decision.")
        seen.add(key)
        result.append(available[key])
    return result


def prepare(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Provide split targets and labeled samples.")
    target = data.get("targets")
    if not isinstance(target, dict) or not 2 <= len(target) <= 8:
        raise ValueError("Provide 2–8 named target fractions.")
    for k, v in target.items():
        identifier(k, "split")
        if k == "quarantine" or type(v) not in (int, float) or not 0 < v <= 1:
            raise ValueError(
                "Use positive target fractions and reserve quarantine for unreviewed groups."
            )
    if not math.isclose(sum(target.values()), 1.0, abs_tol=1e-8):
        raise ValueError("Target fractions must sum to one.")
    groups = defaultdict(list)
    records = {}
    totals = Counter()
    initial = defaultdict(Counter)
    for item in objects(data.get("samples"), "samples", 5000):
        rid = identifier(item.get("id"))
        group = identifier(item.get("group"), "group")
        label = identifier(item.get("label"), "label")
        split = identifier(item.get("split"), "split")
        if rid in records or split not in target:
            raise ValueError("Samples must have unique IDs and use declared splits.")
        row = {"id": rid, "group": group, "label": label, "split": split}
        groups[group].append(row)
        records[rid] = row
        totals[label] += 1
        initial[split][label] += 1
    loads = {s: Counter() for s in target}
    leaks = []
    for name, members in groups.items():
        locations = {x["split"] for x in members}
        if len(locations) > 1:
            leaks.append(name)
        else:
            loads[next(iter(locations))].update(x["label"] for x in members)
    candidates = []
    for name in sorted(leaks, key=lambda n: (-len(groups[n]), n)):
        group = groups[name]
        counts = Counter(r["label"] for r in group)
        original = Counter(r["split"] for r in group)
        scores = []
        for split, fraction in target.items():
            # Marginal squared error in class counts, weighted to keep rare classes visible.
            delta = 0.0
            for label, amount in counts.items():
                expected = totals[label] * fraction
                before = loads[split][label] - expected
                delta += ((before + amount) ** 2 - before**2) / max(1, expected)
            scores.append((delta, -original[split], split))
        scores.sort()
        for rank, (score, _, split) in enumerate(scores):
            candidates.append(
                {
                    "id": f"assign:{len(name)}:{name}:{split}",
                    "action": "Keep group in one split",
                    "group": name,
                    "destination": split,
                    "choice": "recommended" if rank == 0 else "alternative",
                    "evidence_ids": sorted(r["id"] for r in group),
                    "moved_samples": len(group) - original[split],
                    "class_counts": dict(sorted(counts.items())),
                    "score_delta": round(score, 4),
                }
            )
        loads[scores[0][2]].update(counts)
    return {
        "summary": f"{len(leaks)} of {len(groups)} groups span more than one split.",
        "metrics": {
            "Samples": len(records),
            "Groups": len(groups),
            "Leaking groups": len(leaks),
            "Classes": len(totals),
        },
        "records": [records[k] for k in sorted(records)],
        "candidates": candidates,
        "initial_class_counts": {
            s: dict(sorted(initial[s].items())) for s in sorted(target)
        },
    }


def export(data, evidence, approved):
    decisions = {}
    for c in selected(evidence, approved):
        if c["group"] in decisions:
            raise ValueError("Choose only one destination per group.")
        decisions[c["group"]] = c["destination"]
    leaks = {c["group"] for c in evidence["candidates"]}
    rows = []
    balances = defaultdict(Counter)
    for r in evidence["records"]:
        dest = decisions.get(
            r["group"], "quarantine" if r["group"] in leaks else r["split"]
        )
        rows.append([r["id"], r["group"], r["label"], r["split"], dest])
        balances[dest][r["label"]] += 1
    labels = sorted({r["label"] for r in evidence["records"]})
    global_counts = Counter(r["label"] for r in evidence["records"])
    distribution = [
        [s, l, balances[s][l], round(global_counts[l] * f, 3)]
        for s, f in sorted(data["targets"].items())
        for l in labels
    ]
    return {
        "split-manifest.csv": csv_file(
            ["id", "group", "label", "original_split", "split"], rows
        ),
        "stratification.csv": csv_file(
            ["split", "label", "assigned_samples", "target_count"], distribution
        ),
        "quarantined-groups.json": json_file(sorted(leaks - decisions.keys())),
    }
