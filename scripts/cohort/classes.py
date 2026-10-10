"""Drug classes for the catalogue: every ATC code and every USAN/INN name stem.

Both are read from the pinned ChEMBL release and both are ChEMBL's own words.
They are for search and display: "antidepressants" should find quinupramine,
and a class should open the other molecules filed with it. Neither is evidence
about a target, and neither enters the similarity score - its grade is marked
against ATC, so feeding ATC into the ranking would mark the ranking against
itself.

The two are kept apart because they answer different questions. ATC is WHO's
filing of a *product* by the organ it acts on and then by therapeutic,
pharmacological and chemical subgroup; USAN/INN stems are the naming councils'
filing of a *name* by the family it was assigned from ("-pramine:
antidepressants (imipramine type)"). A molecule can carry several of either,
and every one is kept.

molecule_atc keeps only the N codes, because it is the admission route's record
and selection reads it. This reads every anatomical group, so aspirin's B01AC
and lidocaine's C01BB are here while the admission route is untouched.
"""

from __future__ import annotations

import collections
import re

from . import common

# molecule_dictionary pairs a molecule's stems with its sub-stems positionally,
# "; "-joined, and writes a sub-stem as "-mab (-umab)" where usan_stems writes
# subgroup "-umab". The definition field is joined the same way, but a single
# annotation can itself contain "; " ("-triptan"), so it is never split: each
# stem is looked up in usan_stems instead.
_SEP = "; "


def stem_pairs(stem_field: str, substem_field: str | None):
    """Yield (stem, subgroup) for one molecule_dictionary row; '' for no subgroup."""
    stems = stem_field.split(_SEP)
    subs = (substem_field or stem_field).split(_SEP)
    if len(subs) != len(stems):
        # The two lists cannot be paired, so keep the stems and drop the
        # sub-stems rather than attach one to the wrong stem.
        subs = stems
    for stem, sub in zip(stems, subs):
        if not stem.strip("- "):
            # ChEMBL writes a bare "-" for "no stem" (dexmethylphenidate,
            # viloxazine), with "-" as its definition. It is not a class.
            continue
        m = re.fullmatch(re.escape(stem) + r" \((.+)\)", sub)
        yield stem, (m.group(1) if m else ("" if sub == stem else sub))


def _annotations(conn):
    """(stem, subgroup) -> annotation, or None where usan_stems disagrees with itself."""
    seen = collections.defaultdict(set)
    for r in conn.execute("SELECT stem, subgroup, annotation FROM usan_stems"):
        if r["annotation"]:
            seen[(r["stem"], r["subgroup"] or "")].add(r["annotation"])
    return {k: (next(iter(v)) if len(v) == 1 else None) for k, v in seen.items()}


def collect(conn, form_to_parent: dict[int, int]):
    """Every class carried by any form of each parent.

    Returns (molecule_classes rows, class_labels rows), sorted, as tuples in
    the tables' column order. ``conn`` is the ChEMBL release; ``form_to_parent``
    maps each form's molregno to the catalogue parent it folds onto.
    """
    forms = sorted(form_to_parent)
    found: dict[tuple, dict] = {}
    labels: dict[tuple, tuple] = {}

    def add(parent, source, code, subgroup, label, carrier):
        rec = found.setdefault((parent, source, code, subgroup),
                               {"label": label, "carriers": set()})
        if rec["label"] is None:
            rec["label"] = label
        if carrier:
            rec["carriers"].add(carrier)

    for chunk in common.chunked(forms):
        marks = ",".join("?" * len(chunk))
        for r in conn.execute(
                "SELECT mac.molregno, md.chembl_id, a.level5, a.who_name,"
                "       a.level1, a.level1_description, a.level2, a.level2_description,"
                "       a.level3, a.level3_description, a.level4, a.level4_description"
                "  FROM molecule_atc_classification mac"
                "  JOIN atc_classification a ON a.level5 = mac.level5"
                "  JOIN molecule_dictionary md ON md.molregno = mac.molregno"
                f" WHERE mac.molregno IN ({marks})", chunk):
            add(form_to_parent[r["molregno"]], "atc", r["level5"], "",
                r["who_name"], r["chembl_id"])
            for level in (1, 2, 3, 4):
                code = r[f"level{level}"]
                if code:
                    labels[("atc", code)] = (level, r[f"level{level}_description"])

    notes = _annotations(conn)
    for chunk in common.chunked(forms):
        marks = ",".join("?" * len(chunk))
        for r in conn.execute(
                "SELECT molregno, chembl_id, usan_stem, usan_substem, usan_stem_definition"
                "  FROM molecule_dictionary"
                f" WHERE usan_stem IS NOT NULL AND molregno IN ({marks})", chunk):
            pairs = list(stem_pairs(r["usan_stem"], r["usan_substem"]))
            for stem, sub in pairs:
                label = notes.get((stem, sub))
                if label is None and len(pairs) == 1:
                    # One stem on the row, so the row's own definition can only
                    # be that stem's; with several it could be any of them.
                    label = r["usan_stem_definition"]
                add(form_to_parent[r["molregno"]], "usan", stem, sub, label, r["chembl_id"])
                labels[("usan", stem)] = (None, notes.get((stem, "")))

    rows = sorted((p, s, c, g, v["label"], "|".join(sorted(v["carriers"])))
                  for (p, s, c, g), v in found.items())
    label_rows = sorted((s, c, lv, lb) for (s, c), (lv, lb) in labels.items())
    return rows, label_rows


# The sources this module derives from ChEMBL. Other writers own other sources
# in the same tables (mesh_pa, scripts/resolve_cohort_pharm_actions.py), and a
# rerun here must not wipe them.
SOURCES = ("atc", "usan")


def write(db, rows, label_rows, sources=SOURCES) -> None:
    """Replace this writer's sources in both tables, so a rerun leaves nothing
    stale behind and touches no other writer's rows. A label row may carry a
    fifth field, its parents."""
    marks = ",".join("?" * len(sources))
    db.execute(f"DELETE FROM molecule_classes WHERE source IN ({marks})", tuple(sources))
    db.execute(f"DELETE FROM class_labels WHERE source IN ({marks})", tuple(sources))
    db.executemany("INSERT INTO molecule_classes(parent_molregno, source, code,"
                   " subgroup, label, carriers) VALUES(?,?,?,?,?,?)", rows)
    db.executemany("INSERT INTO class_labels(source, code, level, label, parents)"
                   " VALUES(?,?,?,?,?)",
                   [tuple(r) + (None,) * (5 - len(r)) for r in label_rows])


def ensure_tables(db) -> list[str]:
    """Create the two tables in a database built before them. Returns those made.

    The statements are read out of db/schema_cohort.sql rather than repeated
    here, so a backfilled database and a fresh build cannot differ in shape.
    """
    have = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    made = []
    schema = (common.DB / "schema_cohort.sql").read_text()
    for name in ("molecule_classes", "class_labels"):
        if name in have:
            continue
        m = re.search(r"CREATE TABLE IF NOT EXISTS " + name + r" \(.*?\n\);", schema, re.S)
        if not m:
            raise common.PolicyError(f"{name} is missing from schema_cohort.sql")
        db.execute(m.group(0))
        made.append(name)
    # class_labels.parents arrived after the table did, for the MeSH hierarchy.
    cols = {c[1] for c in db.execute("PRAGMA table_info(class_labels)")}
    if "parents" not in cols:
        db.execute("ALTER TABLE class_labels ADD COLUMN parents TEXT")
        made.append("class_labels.parents")
    return made
