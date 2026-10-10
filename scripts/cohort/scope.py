"""Resolve the adopted indication scope from the pinned MeSH classification.

The ontology of record is ``analysis/cohort1/out/indication_scope.csv``, the
saved output of the September 2026 report. Its ``tree_numbers`` column is the
only ontology input this build reads; the raw MeSH cache that produced it is
absent from the checkout and D14 forbids substituting a fresh fetch for it.

Three things happen here, in this order:

1.  The report's S0 core scope is **recomputed** from ``tree_numbers`` using
    the core roots and boundary-exclusion rule it was built with, and checked
    against the saved ``in_core_scope`` column. A mismatch is fatal. Without
    this the additions below would be layered onto a base nobody had verified.
2.  The whole saved Pain tree is added, because D02 adopted it.
3.  An explicit inclusion set is applied, which overrides the boundary
    exclusions. This is what actually delivers the user's neuropathic-pain and
    fibromyalgia requirement: the Pain tree alone does not reach trigeminal
    neuralgia, facial neuralgia or fibromyalgia, none of which carries a
    Pain-tree placement.

Every descriptor ends up with the list of reasons it is in scope, so a
molecule admitted through it can say which one admitted it.
"""

from __future__ import annotations

import collections
import csv
import dataclasses

from . import common


@dataclasses.dataclass(frozen=True)
class Descriptor:
    mesh_id: str
    label: str
    tree_numbers: tuple[str, ...]
    in_core: bool
    core_trees: tuple[str, ...]
    boundary_classes: tuple[str, ...]
    in_scope: bool
    scope_reasons: tuple[str, ...]


def under(tree_numbers, roots) -> list[str]:
    """Tree numbers of this descriptor that fall inside any of ``roots``.

    A tree number is inside a root when it equals it or continues it after a
    period. ``C10.551`` is inside ``C10``; ``C105`` is not.
    """
    hits = []
    for tn in tree_numbers:
        for root in roots:
            if tn == root or tn.startswith(root + "."):
                hits.append(tn)
                break
    return hits


def load(policy: dict | None = None) -> dict[str, Descriptor]:
    """Classify every pinned descriptor against the adopted scope."""
    policy = policy or common.load_policy("cohort1_selection.json")
    scope = policy["indication_scope"]

    core_roots = [r["tree"] for r in scope["core_roots"]]
    exclusions = scope["core_boundary_exclusions"]
    pain_trees = [t for c in scope["additive_classes"] if c["adopted"] for t in c["trees"]]
    explicit = scope["explicit_inclusions"]
    explicit_roots = [r["tree"] for r in explicit["tree_roots"]]
    # Each descriptor names its own reason; the neuropathic ones predate the
    # field and default to it. D16's psychiatric and anaesthesia headings,
    # which MeSH files under Behavior (F01) and Procedures (E03), are
    # explicit_cns_heading - saying "neuropathic" of Anxiety would be false.
    explicit_ids = {d["mesh_id"]: d.get("scope_reason", "explicit_neuropathic")
                    for d in explicit["descriptors"]}

    # Which explicit reason a tree root carries, so admission can name it.
    root_reason = {}
    for r in explicit["tree_roots"]:
        root_reason[r["tree"]] = ("explicit_fibromyalgia"
                                  if "Fibromyalgia" in r["label"]
                                  else "explicit_neuropathic")

    out: dict[str, Descriptor] = {}
    mismatches = []

    with open(common.MESH_SCOPE_CSV, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            tns = tuple(t for t in row["tree_numbers"].split(";") if t)

            # ---- 1. recompute the saved core scope --------------------------
            under_core = under(tns, core_roots)
            excluded_trees = set()
            boundary_hits = []
            for b in exclusions:
                hit = under(tns, b["trees"])
                if hit:
                    boundary_hits.append(b["id"])
                    excluded_trees |= set(under(under_core, b["trees"]))
            core_trees = sorted(set(under_core) - excluded_trees)
            in_core = bool(core_trees)

            if in_core != (row["in_core_scope"] == "1"):
                mismatches.append((row["mesh_id"], row["mesh_label"],
                                   row["in_core_scope"], in_core))

            # ---- 2 and 3. the adopted additions -----------------------------
            reasons = []
            if in_core:
                reasons.append("core")
            if under(tns, pain_trees):
                reasons.append("general_pain")
            for root in explicit_roots:
                if under(tns, [root]):
                    reason = root_reason[root]
                    if reason not in reasons:
                        reasons.append(reason)
            if row["mesh_id"] in explicit_ids:
                reason = explicit_ids[row["mesh_id"]]
                if reason not in reasons:
                    reasons.append(reason)

            out[row["mesh_id"]] = Descriptor(
                mesh_id=row["mesh_id"],
                label=row["mesh_label"],
                tree_numbers=tns,
                in_core=in_core,
                core_trees=tuple(core_trees),
                boundary_classes=tuple(boundary_hits),
                in_scope=bool(reasons),
                scope_reasons=tuple(reasons),
            )

    if mismatches:
        detail = "; ".join(f"{m[0]} {m[1]!r} saved={m[2]} recomputed={m[3]}"
                           for m in mismatches[:10])
        raise common.PolicyError(
            f"recomputed core scope disagrees with the pinned classification on "
            f"{len(mismatches)} descriptors: {detail}. The base scope must not "
            f"drift while the adopted additions are layered onto it."
        )
    return out


def assert_covers(descriptors: dict[str, Descriptor], used: set[str]) -> None:
    """Fail if ChEMBL names a descriptor the pinned classification does not.

    An unclassified descriptor must never be silently treated as out of scope:
    that would turn a gap in the ontology snapshot into a membership decision.
    """
    missing = sorted(used - set(descriptors))
    if missing:
        raise common.PolicyError(
            f"{len(missing)} mesh_id values in drug_indication are absent from "
            f"{common.MESH_SCOPE_CSV.name}: {missing[:10]}. Classify them or "
            f"raise the scope policy version; do not treat them as out of scope."
        )


def fixtures_check(descriptors: dict[str, Descriptor], policy: dict) -> list[str]:
    """Verify the descriptors D02 names by hand actually landed in scope.

    These are the starting fixtures the decision log lists, not the whole
    neuropathic set. They are asserted here because the report prose claimed
    one of them (Neuralgia) was already in core when the saved data says it is
    not, and a rule that quietly stops delivering them is the failure this
    check exists to catch.
    """
    required = {
        "D005356": "Fibromyalgia",
        "D009437": "Neuralgia",
        "D051474": "Postherpetic Neuralgia",
        "D014277": "Trigeminal Neuralgia",
        "D005156": "Facial Neuralgia",
        "D060545": "Pudendal Neuralgia",
        # D16: CNS conditions MeSH files outside C10 and F03.
        "D001007": "Anxiety",
        "D003863": "Depression",
        "D016540": "Smoking Cessation",
        "D000758": "Anesthesia",
    }
    problems = []
    for mesh_id, name in required.items():
        d = descriptors.get(mesh_id)
        if d is None:
            problems.append(f"{mesh_id} ({name}) is not in the pinned classification")
        elif not d.in_scope:
            problems.append(f"{mesh_id} ({name}) is not in the adopted scope")
    return problems


def summarise(descriptors: dict[str, Descriptor]) -> dict:
    reasons = collections.Counter()
    for d in descriptors.values():
        if not d.in_scope:
            continue
        for r in d.scope_reasons:
            reasons[r] += 1
    recovered = [d for d in descriptors.values()
                 if d.in_scope and not d.in_core]
    return {
        "descriptors_classified": len(descriptors),
        "descriptors_in_scope": sum(1 for d in descriptors.values() if d.in_scope),
        "descriptors_in_core": sum(1 for d in descriptors.values() if d.in_core),
        "in_scope_by_reason": dict(reasons),
        "recovered_outside_core": len(recovered),
    }
