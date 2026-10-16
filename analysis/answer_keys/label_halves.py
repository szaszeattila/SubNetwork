"""The label key's profiles built twice, from two disjoint sets of labels.

    python3 analysis/answer_keys/label_halves.py > halves.json

Read-only: it reads the pinned OnSIDES zip the label backfill cached and the
`label_effect_molecules` / `label_effect_terms` tables, and writes JSON to
stdout for analysis/answer_keys/label_reliability.mjs. It writes nothing else.

Every label of an ingredient is either a US label (DailyMed) or not (the UK,
the EU and Japan). Each half gets a profile under the key's own rules
(analysis/similarity_harness/onsides_key.json): an effect counts when
`min_labels` of the half's labels list it, or every label of a half with
fewer; terms are counted as the effect `label_effect_terms` places them on;
the scope is a set of MedDRA SOCs or every effect. Two profiles of one
ingredient from different regulators' labels are two measurements of one
thing, so how far they agree is how far the key agrees with itself.
"""

import collections
import csv
import io
import json
import pathlib
import sqlite3
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import resolve_cohort_label_effects as rle  # noqa: E402

KEY = json.loads((ROOT / "analysis" / "similarity_harness" / "onsides_key.json").read_text())


def main():
    conn = sqlite3.connect(f"file:{ROOT / 'db' / 'cohort1.db'}?mode=ro", uri=True)
    rx_of = dict(conn.execute("SELECT parent_molregno, rxcui FROM label_effect_molecules"))
    placed = {t: (e, set((s or "").split("|")) - {""}) for t, e, s in
              conn.execute("SELECT term, effect, socs FROM label_effect_terms")}
    conn.close()

    ingredients = set(rx_of.values())
    label_counts, effects, _, _ = rle.read_onsides(rle.ONSIDES_FILE, ingredients)
    with zipfile.ZipFile(rle.ONSIDES_FILE) as z, z.open("csv/product_label.csv") as fh:
        source = {r["label_id"]: r["source"]
                  for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", newline=""))}

    half_of = lambda label: "us" if source[label] == "US" else "rest"
    out = {"min_labels": KEY["min_labels"], "molecules": rx_of, "profiles": {}}
    for scope_name, spec in KEY["scopes"].items():
        scope = set(spec["socs"]) if spec["socs"] else None
        by_half = {"us": {}, "rest": {}}
        for ing in sorted(ingredients):
            listed = collections.defaultdict(lambda: collections.defaultdict(set))
            for term, by_label in effects.get(ing, {}).items():
                effect, socs = placed.get(term, (term, set()))
                if scope is not None and not socs & scope:
                    continue
                for label in by_label:
                    listed[half_of(label)][effect].add(label)
            for half in ("us", "rest"):
                # Every single-ingredient label counts, one with no effect
                # read from it included, as in the key.
                n = sum(c for country, c in label_counts.get(ing, {}).items()
                        if (country == "US") == (half == "us"))
                if not n:
                    continue
                need = min(KEY["min_labels"], n)
                prof = sorted(e for e, ls in listed[half].items() if len(ls) >= need)
                if prof:
                    by_half[half][ing] = prof
        out["profiles"][scope_name] = by_half
    json.dump(out, sys.stdout)


if __name__ == "__main__":
    main()
