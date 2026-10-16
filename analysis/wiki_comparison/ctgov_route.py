#!/usr/bin/env python3
"""What ClinicalTrials.gov would admit read directly, rather than through
ChEMBL's drug_indication: for every wiki compound outside the catalogue, the
registered trials naming it as an intervention, and whether any is for an
in-scope condition at Phase 1 or later.

Read-only and adopts nothing. The question is whether the registry knows
trials ChEMBL has not curated into an indication: ChEMBL's indications come
from the registry, but only for molecules ChEMBL maps an intervention to.

**This queries the registry by name**, which invariant 15 forbids for anything
entering the database; it is allowed here only because nothing here does. The
registry's intervention search also matches synonyms, so a study is counted
only when one of its intervention names or other names contains the wiki's
name as whole words, and names of four characters or fewer are reported apart
(ALA, MCPP, LSD match too much).

Scope is the adopted one (config/cohort1_selection.json), applied to the
registry's condition MeSH ids with the same rules as scripts/cohort/scope.py,
but over every descriptor in the pinned MeSH 2026 file: the saved scope list
holds only the headings ChEMBL's indications use, and a registry condition
need not be one. On the headings both know, the two agree (checked at start).

Phase "NA" is the registry's "not applicable", the usual phase of a dietary
supplement or behavioural trial; it is counted apart, since no phase floor
reads it as Phase 1.

    python3 analysis/wiki_comparison/ctgov_route.py [--csv FILE] [--mesh DESC_GZ]

Writes ctgov_cache.json after every name, so a run can be stopped and resumed.
"""
import argparse
import collections
import concurrent.futures
import csv
import gzip
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from placing import HERE, REFERENCE, ROOT, norm

sys.path.insert(0, str(ROOT / "scripts"))
from cohort import scope as scope_mod  # noqa: E402

CACHE = HERE / "ctgov_cache.json"
API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = "NCTId,Phase,InterventionName,InterventionOtherName,ConditionMeshId"
UA = "SubNetwork/1.0 (drug-target interaction map; analysis/wiki_comparison)"
PHASE_RANK = {"EARLY_PHASE1": 0.5, "PHASE1": 1, "PHASE2": 2, "PHASE3": 3, "PHASE4": 4}
MAX_PAGES = 5  # 5,000 studies; only very common substances reach it


def mesh_scope(policy, desc_gz):
    """Every MeSH 2026 descriptor id -> in scope, by scope.load's rules."""
    sc = policy["indication_scope"]
    core = [r["tree"] for r in sc["core_roots"]]
    pain = [t for c in sc["additive_classes"] if c["adopted"] for t in c["trees"]]
    roots = [r["tree"] for r in sc["explicit_inclusions"]["tree_roots"]]
    ids = {d["mesh_id"] for d in sc["explicit_inclusions"]["descriptors"]}
    out = {}
    with gzip.open(desc_gz) as fh:
        for _, el in ET.iterparse(fh):
            if el.tag != "DescriptorRecord":
                continue
            ui = el.findtext("DescriptorUI")
            tns = [t.text for t in el.iter("TreeNumber")]
            in_core = scope_mod.under(tns, core)
            excl = set()
            for b in sc["core_boundary_exclusions"]:
                excl |= set(scope_mod.under(in_core, b["trees"]))
            out[ui] = bool(set(in_core) - excl or scope_mod.under(tns, pain)
                           or scope_mod.under(tns, roots) or ui in ids)
            el.clear()
    return out


def fetch(name):
    studies, token = [], None
    for _ in range(MAX_PAGES):
        q = {"query.intr": name, "fields": FIELDS, "pageSize": 1000}
        if token:
            q["pageToken"] = token
        req = urllib.request.Request(f"{API}?{urllib.parse.urlencode(q)}", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            page = json.load(r)
        studies += page.get("studies", [])
        token = page.get("nextPageToken")
        if not token:
            break
    pat = re.compile(r"(?<![a-z0-9])" + re.escape(norm(name)) + r"(?![a-z0-9])")
    kept = []
    for s in studies:
        ps = s.get("protocolSection", {})
        names = [x for i in ps.get("armsInterventionsModule", {}).get("interventions", [])
                 for x in [i.get("name", "")] + i.get("otherNames", [])]
        if any(pat.search(norm(n)) for n in names):
            kept.append([ps["identificationModule"]["nctId"],
                         ps.get("designModule", {}).get("phases", []),
                         [m["id"] for m in s.get("derivedSection", {})
                          .get("conditionBrowseModule", {}).get("meshes", [])]])
    return {"returned": len(studies), "truncated": bool(token), "studies": kept}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=pathlib.Path, default=REFERENCE / "comparison.csv")
    ap.add_argument("--mesh", type=pathlib.Path, default=ROOT / "db" / "cache" / "mesh" / "desc2026.gz")
    args = ap.parse_args()

    policy = json.loads((ROOT / "config" / "cohort1_selection.json").read_text())
    in_scope = mesh_scope(policy, args.mesh)
    saved = scope_mod.load(policy)
    disagree = [k for k, d in saved.items() if k in in_scope and in_scope[k] != d.in_scope]
    print(f"scope: {sum(in_scope.values()):,} of {len(in_scope):,} MeSH 2026 descriptors in scope; "
          f"{len(disagree)} disagree with the saved scope on the {len(saved):,} it holds {disagree[:5]}")

    wiki = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    groups = {
        "in ChEMBL": [r for r in wiki if r["chembl_parents"] and not r["in_catalogue"]],
        "identified, not in ChEMBL": [r for r in wiki if r["match_tier"] in (
            "unii_not_in_chembl", "unii_no_structure", "pubchem_not_in_chembl")],
    }
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = sorted({r["name"] for g in groups.values() for r in g} - set(cache))
    print(f"{len(todo)} names to ask the registry")

    def ask(name):
        try:
            return name, fetch(name)
        except (urllib.error.URLError, OSError, ValueError) as e:
            return name, e
        finally:
            time.sleep(5)  # four workers stay under the registry's ~50 requests a minute

    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        for i, (name, got) in enumerate(pool.map(ask, todo)):
            if isinstance(got, Exception):
                print(f"error on {name!r}: {got}; left for a later run", flush=True)
                continue
            cache[name] = got
            CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
            if i % 50 == 0:
                print(f"{i}/{len(todo)}", flush=True)

    def verdict(name):
        best_scoped, na_scoped, any_trial = -9, False, False
        for _, phases, conds in cache.get(name, {}).get("studies", []):
            any_trial = True
            if any(in_scope.get(c) for c in conds):
                if "NA" in phases:
                    na_scoped = True
                best_scoped = max([best_scoped] + [PHASE_RANK.get(p, -9) for p in phases])
        if best_scoped >= 1:
            return "in-scope trial, Phase 1+"
        if best_scoped == 0.5:
            return "in-scope trial, Early Phase 1"
        if na_scoped:
            return "in-scope trial, phase NA only"
        return "trials, none in scope" if any_trial else "no trial naming it"

    order = ["in-scope trial, Phase 1+", "in-scope trial, Early Phase 1",
             "in-scope trial, phase NA only", "trials, none in scope", "no trial naming it"]
    for gname, rows in groups.items():
        long_ = [r for r in rows if len(re.sub(r"[^a-z0-9]", "", norm(r["name"]))) > 4]
        print(f"\n{gname}: {len(rows)} wiki compounds outside the catalogue "
              f"({len(rows) - len(long_)} names of four characters or fewer set apart)")
        c = collections.Counter(verdict(r["name"]) for r in long_)
        for v in order:
            names = sorted(r["name"] for r in long_ if verdict(r["name"]) == v)
            shown = ", ".join(names[:40]) if v != "no trial naming it" and v != "trials, none in scope" else ""
            print(f"  {v}: {c[v]}  {shown}")
        sec = collections.Counter(r["section"] for r in long_ if verdict(r["name"]) == order[0])
        print("  Phase 1+ in scope, by section:", dict(sec.most_common()))
        short = sorted(f'{r["name"]} ({verdict(r["name"])})' for r in rows if r not in long_)
        print("  short names:", "; ".join(short))
    trunc = sorted(n for n, v in cache.items() if v.get("truncated"))
    if trunc:
        print(f"\ntruncated at {MAX_PAGES * 1000:,} studies: {trunc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
