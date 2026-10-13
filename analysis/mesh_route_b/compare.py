"""Route B variants against route A, on a catalogue where route A is complete.

  B1  InChIKey -> FDA UNII -> the one MeSH record carrying that UNII (own_record)
  B2  B1, and where the UNIIs reach no record, the CAS numbers FDA lists for
      them, since older MeSH records carry a CAS number where newer ones carry
      the UNII
  B2R B2, then rule R, only for a molecule B2 leaves without a record and only
      where ChEMBL's InChIKey has no stereo layer: an FDA substance registered
      as a mixture of stereoisomers of that skeleton (its INCHIKEY field
      ';'-joins two or more keys sharing the first block), accepted only when
      exactly one record. ChEMBL's "stereo unspecified" and FDA's "a mixture of
      this skeleton's stereoisomers" describe one substance
  B3  B2, then, only for a molecule B2 leaves without a record: the first
      InChIKey block (the skeleton, stereo ignored) -> every FDA UNII with that
      block -> their UNII/CAS -> records, accepted only when exactly one record

Read-only and offline: the cohort database and ChEMBL are opened read-only,
and nothing is fetched. Run from the repository root, against a database whose PubChem
backfill (route A) completed:
    python3 analysis/mesh_route_b/compare.py db/cohort1.db [wikidata_mesh.json]

With the second argument, a JSON map of ChEMBL ID -> the MeSH IDs (P486) on
the Wikidata item(s) carrying that ChEMBL ID (P592), as written by
analysis/mesh_route_b/wikidata_mesh.py, it also measures Wikidata as a
fallback for the molecules B2R cannot place.

The measurement and what it found: docs/MESH-ACTIONS-ROUTE-B.md.
"""
import collections
import csv
import io
import sqlite3
import sys
import zipfile

sys.path.insert(0, "scripts")
import resolve_cohort_pharm_actions as pharm  # noqa: E402
import resolve_cohort_mesh_structure as structure  # noqa: E402
from cohort import common  # noqa: E402

mesh = pharm.load_mesh(pharm.ensure_mesh_file())
records = pharm.load_records(pharm.ensure_mesh_file(), structure.ensure_supp_file())
name = lambda ui: mesh["desc"].get(ui, (ui,))[0]  # noqa: E731

# FDA's records: InChIKey -> UNIIs, UNII -> CAS numbers.
csv.field_size_limit(1 << 30)
with zipfile.ZipFile(structure.ensure_unii_file()) as zf:
    member = [n for n in zf.namelist() if n.startswith("UNII_Records")][0]
    text = zf.read(member).decode("utf-8")
reader = csv.DictReader(io.StringIO(text), delimiter="\t")
print("FDA columns:", reader.fieldnames)
unii_by_key, cas_of, by_block = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
mixture_by_block = collections.defaultdict(set)   # skeleton -> UNIIs registered as a mixture of its stereoisomers
for r in reader:
    u, k, rn = r.get("UNII"), r.get("INCHIKEY"), (r.get("RN") or "").strip()
    if not u:
        continue
    if rn:
        cas_of[u].add(rn)
    if k:
        unii_by_key[k].add(u)
        by_block[k[:14]].add(u)
        parts = [x.strip() for x in k.split(";") if x.strip()]
        if len(parts) >= 2 and len({x[:14] for x in parts}) == 1:
            mixture_by_block[parts[0][:14]].add(u)

by_rn = collections.defaultdict(set)   # a MeSH registry number (UNII or CAS) -> records
for rec, rns in records["rn"].items():
    for x in rns:
        by_rn[x].add(rec)


def records_for(uniis, with_cas):
    found = set()
    for u in uniis:
        found |= by_rn.get(u, set())
        if with_cas:
            for c in cas_of.get(u, ()):
                found |= by_rn.get(c, set())
    return found


def own(keys, with_cas):
    """own_record's rule: the parent's key first, forms only if it reaches
    nothing. With with_cas, CAS numbers are tried only where the UNIIs reach
    no record at all: used alongside them, a CAS number some second record
    also carries refuses molecules the UNII had placed (eplerenone,
    lacosamide)."""
    def by(cas):
        found = set()
        for i, key in enumerate(keys):
            if i == 1 and found:
                break
            found |= records_for(unii_by_key.get(key, ()), cas)
        return found
    return by(False) or (by(True) if with_cas else set())


db = sys.argv[1]
conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
chembl = common.chembl()
forms = collections.defaultdict(list)
for p, m in conn.execute("SELECT parent_molregno, molregno FROM molecule_forms"
                         " ORDER BY parent_molregno, is_parent DESC, molregno"):
    forms[p].append(m)
key_of = {}
regnos = sorted({m for v in forms.values() for m in v})
for chunk in common.chunked(regnos):
    q = f"SELECT molregno, standard_inchi_key FROM compound_structures WHERE molregno IN ({','.join('?' * len(chunk))})"
    key_of.update(chembl.execute(q, chunk).fetchall())
mols = {p: (n, k) for p, n, k in conn.execute("SELECT parent_molregno, pref_name, inchikey FROM molecules")}

a = collections.defaultdict(set)
for p, ui in conn.execute("SELECT parent_molregno, code FROM molecule_classes WHERE source='mesh_pa'"):
    a[p].add(ui)

results, reached = {}, {}
for variant in ("B1", "B2", "B2R", "B3"):
    b, how = {}, {}
    reached[variant] = {}
    for p, (n, pkey) in mols.items():
        keys = [k for k in dict.fromkeys([pkey] + [key_of.get(m) for m in forms[p]]) if k]
        found = own(keys, with_cas=variant != "B1")
        route = "exact"
        if variant == "B2R" and not found:
            for key in keys:
                if key[15:25] != "UHFFFAOYSA":
                    continue
                mix = mixture_by_block.get(key[:14], ())
                found = records_for(mix, False) or records_for(mix, True)
                if found:
                    route = "mixture"
                    break
        if variant == "B3" and not found and keys:
            found = records_for(by_block.get(keys[0][:14], ()), with_cas=True)
            route = "skeleton"
        if len(found) == 1:
            rec = next(iter(found))
            reached[variant][p] = rec
            if records["pa"].get(rec):
                b[p] = frozenset(records["pa"][rec])
                how[p] = (route, rec)
    results[variant] = (b, how)
    covered = set(a) | set(b)
    same = sum(1 for p in covered if a.get(p, set()) == b.get(p, set()))
    print(f"\n{variant}: actions for {len(b)} (route A {len(a)});"
          f" identical {same}, A only {len(set(a) - set(b))}, B only {len(set(b) - set(a))},"
          f" both but differ {sum(1 for p in set(a) & set(b) if a[p] != b[p])}")

# What each refinement added, and whether it agrees with route A where A has an answer.
for lo, hi in (("B1", "B2"), ("B2", "B2R"), ("B2", "B3")):
    lost = set(results[lo][0]) - set(results[hi][0])
    if lost:
        print(f"\n{hi} loses {len(lost)} that {lo} had (a second record reached, so refused):")
        for p in sorted(lost, key=lambda p: mols[p][0] or ""):
            A = a.get(p, set())
            print(f"   {mols[p][0]} (was {results[lo][1][p][1]}):"
                  f" {'same as A' if A == results[lo][0][p] else 'differed from A'}")
    added = set(results[hi][0]) - set(results[lo][0])
    print(f"\n{hi} adds {len(added)} over {lo}:")
    for p in sorted(added, key=lambda p: mols[p][0] or ""):
        B = results[hi][0][p]
        A = a.get(p, set())
        verdict = "same as A" if A == B else ("A has none" if not A else "differs from A")
        rec = results[hi][1][p][1]
        print(f"   {mols[p][0]} -> {rec} {name(rec) if rec.startswith('D') else ''}: {verdict}"
              + ("" if verdict == "same as A" else f"  [A: {'; '.join(sorted(map(name, A))) or '-'} | B: {'; '.join(sorted(map(name, B)))}]"))

# What route A still reaches that B2R does not, and why.
b2r = results["B2R"][0]
print(f"\nroute A only, after B2R ({len(set(a) - set(b2r))}):")
for p in sorted(set(a) - set(b2r), key=lambda p: mols[p][0] or ""):
    n, pkey = mols[p]
    keys = [k for k in dict.fromkeys([pkey] + [key_of.get(m) for m in forms[p]]) if k]
    if not keys:
        why = "no InChIKey"
    else:
        hit = own(keys, with_cas=True)
        if len(hit) > 1:
            why = f"UNII/CAS reach {len(hit)} records"
        elif hit:
            why = "own record lists no action"
        elif any(unii_by_key.get(k) for k in keys):
            why = "FDA holds the key; no MeSH record carries its UNII or CAS"
        elif any(by_block.get(k[:14]) for k in keys):
            flat = keys[0][15:25] == "UHFFFAOYSA"
            why = ("same skeleton in FDA, " + ("ChEMBL flat, no single-record mixture" if flat
                                                else "different stereo"))
        else:
            why = "skeleton not in FDA"
    print(f"   {n}: {why}  [A: {'; '.join(sorted(map(name, a[p])))}]")

# Wikidata as a fallback: ChEMBL ID -> item -> MeSH ID, for what B2R cannot place.
if len(sys.argv) > 2:
    import json  # noqa: E402
    wd = json.load(open(sys.argv[2]))
    chembl_of = dict(conn.execute("SELECT parent_molregno, chembl_id FROM molecules"))
    known = set(records["pa"]) | set(records["rn"]) | set(records["mapped"]) | set(mesh["desc"])
    rb = reached["B2R"]
    both = [p for p in rb if wd.get(chembl_of[p])]
    agree = [p for p in both if rb[p] in wd[chembl_of[p]]]
    print(f"\nWikidata against B2R, where both name a record: {len(agree)} of {len(both)} agree")
    for p in sorted(set(both) - set(agree), key=lambda p: mols[p][0] or ""):
        print(f"   disagree: {mols[p][0]} B2R {rb[p]} {name(rb[p])} | Wikidata {wd[chembl_of[p]]}"
              f" {[name(x) for x in wd[chembl_of[p]]]}")
    extra = {}
    for p in mols:
        if p in rb:
            continue
        ids = [x for x in wd.get(chembl_of[p], []) if x in known]
        if len(ids) == 1 and records["pa"].get(ids[0]):
            extra[p] = (ids[0], frozenset(records["pa"][ids[0]]))
    no_key = [p for p in extra if not mols[p][1]]
    print(f"\nWikidata adds actions for {len(extra)} molecules B2R places nowhere"
          f" ({len(no_key)} of them with no InChIKey)")
    vs = collections.Counter()
    for p, (rec, acts) in sorted(extra.items(), key=lambda kv: mols[kv[0]][0] or ""):
        A = a.get(p, set())
        v = "same as A" if A == acts else ("A has none" if not A else "differs from A")
        vs[v] += 1
        print(f"   {mols[p][0]} -> {rec} {name(rec) if rec.startswith('D') else ''}: {v}"
              + ("" if v == "same as A" else f"  [A: {'; '.join(sorted(map(name, A))) or '-'} | WD: {'; '.join(sorted(map(name, acts)))}]"))
    print("  ", dict(vs))
