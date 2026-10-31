"""Place a compound name (or an InChIKey) at its ChEMBL 37 parent.

Shared by compare.py (the wiki against the catalogue) and compare_lists.py
(other public lists against the wiki and the catalogue). The tiers, in the
order tried, and their confidence:

  inchikey         an InChIKey the list itself supplies                high
  chembl_name      exact ChEMBL pref_name                              high
  chembl_synonym   exact ChEMBL synonym                                medium;
                   low at four characters or fewer (AMT, MDA)
  chembl_squashed  name with punctuation and spaces dropped            low
  unii_inchikey    FDA UNII preferred name -> InChIKey -> ChEMBL       high
  pubchem_*        PubChem's name service, from pubchem_cache.json     low

"_connectivity" means only the InChIKey's first block matched: the same
skeleton in another stereo or isotope form. Read-only throughout.
"""
import collections
import csv
import io
import json
import os
import pathlib
import re
import sqlite3
import unicodedata
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CHEMBL = os.environ.get("CHEMBL_SQLITE_PATH", "/mnt/data/chembl/chembl_37/chembl_37_sqlite/chembl_37.db")

# The wiki's own list, with the section and class it files each compound
# under, is kept on disk and out of the repository: its terms refuse copying
# the reference in bulk (docs/COMPOUND-LIST-TERMS.md). db/cache/ is gitignored.
# Everything that reads a section or class reads it from here; the repository
# keeps public_copy()'s version of each comparison file.
REFERENCE = ROOT / "db" / "cache" / "sciwiki"
WIKI_ONLY = ("section", "wiki_class")


def public_copy(path: pathlib.Path) -> pathlib.Path:
    """Write HERE/<name> from a reference comparison file, without WIKI_ONLY."""
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    out = HERE / path.name
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[k for k in rows[0] if k not in WIKI_ONLY])
        w.writeheader()
        w.writerows({k: v for k, v in r.items() if k not in WIKI_ONLY} for r in rows)
    return out

# Matches found wrong on review: a name lookup that reached another substance.
REJECTED = {
    "Irisin": "PubChem name reached iridin, an isoflavone; irisin is a myokine protein",
    "Cardiogen": "PubChem name reached levocarnitine; Cardiogen is a Khavinson tetrapeptide",
    "Thymalin": "PubChem name reached nonathymulin; thymalin is a thymus extract",
    "HCG": "PubChem name reached a small molecule; hCG is a glycoprotein hormone",
    "MKP": "PubChem name reached potassium phosphate",
    "AMT": "ChEMBL synonym of 3-amino-3-deoxythymidine; the wiki means alpha-methyltryptamine",
    "NPAP": "ChEMBL synonym of prajmalium, an unrelated substance",
    "HU-210": "squashed name reached dexanabinol (HU-211), its enantiomer",
    "MET": "PubChem name reached methionine; the wiki means methylethyltryptamine",
    "DGL": "PubChem name reached D-glutamate; the wiki means deglycyrrhizinated licorice",
    "Beta-Glucans": "PubChem name reached maltotriose; beta-glucans are a polysaccharide family",
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("–", "-").replace("—", "-").replace("’", "'")
    return re.sub(r"\s+", " ", s).strip()


def squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", norm(s))


class Placer:
    def __init__(self, data_root: pathlib.Path = ROOT):
        data = pathlib.Path(data_root).resolve()
        self.ch = ch = sqlite3.connect(f"file:{CHEMBL}?mode=ro", uri=True)
        self.coh = sqlite3.connect(f"file:{data / 'db' / 'cohort1.db'}?mode=ro", uri=True)
        parent = dict(ch.execute("SELECT molregno, parent_molregno FROM molecule_hierarchy"))
        self.chembl_id = dict(ch.execute("SELECT molregno, chembl_id FROM molecule_dictionary"))
        self.pref_name = dict(ch.execute("SELECT molregno, pref_name FROM molecule_dictionary"))
        P = lambda m: parent.get(m, m)

        self.by_pref, self.by_syn, self.by_squash = (collections.defaultdict(set) for _ in range(3))
        for m, n in ch.execute("SELECT molregno, pref_name FROM molecule_dictionary WHERE pref_name IS NOT NULL"):
            self.by_pref[norm(n)].add(P(m))
            self.by_squash[squash(n)].add(P(m))
        for m, n in ch.execute("SELECT molregno, synonyms FROM molecule_synonyms WHERE synonyms IS NOT NULL"):
            self.by_syn[norm(n)].add(P(m))
            self.by_squash[squash(n)].add(P(m))
        self.by_key, self.by_block = collections.defaultdict(set), collections.defaultdict(set)
        for m, k in ch.execute("SELECT molregno, standard_inchi_key FROM compound_structures "
                               "WHERE standard_inchi_key IS NOT NULL"):
            self.by_key[k].add(P(m))
            self.by_block[k[:14]].add(P(m))

        # The FDA UNII file the MeSH structure backfill already pins.
        self.unii = collections.defaultdict(set)
        with zipfile.ZipFile(data / "db" / "cache" / "fda" / "UNII_Data.zip") as z:
            member = next(n for n in z.namelist() if n.startswith("UNII_Records"))
            with z.open(member) as fh:
                reader = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
                head = reader.readline().rstrip("\n").split("\t")
                i_name, i_key = head.index("DISPLAY_NAME"), head.index("INCHIKEY")
                for line in reader:
                    c = line.rstrip("\n").split("\t")
                    if len(c) > i_key:
                        self.unii[norm(c[i_name])].add((c[0], c[i_key]))

        cache_f = HERE / "pubchem_cache.json"
        self.pubchem = json.loads(cache_f.read_text()) if cache_f.exists() else {}
        self.gtopdb = set()
        for row in csv.reader(open(data / "db" / "cache" / "gtopdb" / "2026.3" / "ligands.csv", encoding="utf-8")):
            self.gtopdb.update(c for c in row if c.startswith("CHEMBL"))
        self.catalogue = {r[0]: r[1:] for r in self.coh.execute(
            "SELECT chembl_id, admission_reason, evidence_status FROM molecules")}

    def from_key(self, k):
        if k in self.by_key:
            return self.by_key[k], "inchikey"
        if k[:14] in self.by_block:
            return self.by_block[k[:14]], "connectivity"
        return set(), None

    def place(self, name: str, inchikeys=(), use_pubchem: bool = True):
        """Return (parent molregnos, tier, note, confidence)."""
        got, tier, note = set(), None, ""
        for k in inchikeys:
            s, how = self.from_key(k)
            if s:
                got |= s
                tier = tier or ("inchikey" if how == "inchikey" else "inchikey_connectivity")
        if got:
            pass
        elif norm(name) in self.by_pref:
            got, tier = self.by_pref[norm(name)], "chembl_name"
        elif norm(name) in self.by_syn:
            got, tier = self.by_syn[norm(name)], "chembl_synonym"
        elif squash(name) and squash(name) in self.by_squash:
            got, tier = self.by_squash[squash(name)], "chembl_squashed"
        elif norm(name) in self.unii and any(k for _, k in self.unii[norm(name)]):
            for _, k in self.unii[norm(name)]:
                s, how = self.from_key(k) if k else (set(), None)
                if s:
                    got |= s
                    tier = f"unii_{how}"
            if not got:
                tier = "unii_not_in_chembl"
                note = "UNII " + ";".join(sorted(u for u, k in self.unii[norm(name)] if k))
        elif norm(name) in self.unii:
            tier, note = "unii_no_structure", "UNII " + ";".join(sorted(u for u, _ in self.unii[norm(name)]))
        elif inchikeys:
            tier = "inchikey_not_in_chembl"
        if tier is None:
            if not use_pubchem:
                tier = "no_match"
            elif name not in self.pubchem:
                tier = "not_looked_up"
            elif self.pubchem[name]:
                for k in self.pubchem[name]:
                    s, how = self.from_key(k)
                    if s:
                        got |= s
                        tier = f"pubchem_{how}"
                tier = tier or "pubchem_not_in_chembl"
            else:
                tier = "no_match"
        if name in REJECTED and got:
            got, tier, note = set(), "rejected_on_review", REJECTED[name]

        if tier in ("inchikey", "chembl_name", "unii_inchikey"):
            confidence = "high"
        elif tier == "chembl_synonym" and len(squash(name)) > 4:
            confidence = "medium"
        else:
            confidence = "low" if got else ""
        return got, tier, note, confidence

    def ids(self, got):
        return sorted(self.chembl_id[p] for p in got)
