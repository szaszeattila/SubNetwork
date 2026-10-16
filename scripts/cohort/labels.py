"""What stands behind ChEMBL's "Approved" for a disease (decision D23).

ChEMBL sets `drug_indication.max_phase_for_ind` to 4 on four kinds of
reference, and cites which in `indication_refs`:

  FDA / EMA        a regulator's own approval document;
  DailyMed         a US product label naming the disease;
  ATC              a WHO ATC class the disease is read off;
  ClinicalTrials   a Phase 4 trial - post-marketing, so of an approved drug,
                   and usually in the use it is approved for.

A DailyMed label is not an approval. FDA publishes the label of a product it
never approved, under the marketing category UNAPPROVED DRUG OTHER, and
isometheptene was Approved for migraine here on five such labels and nothing
else. scripts/check_dailymed_labels.py reads the category of every label
behind every label-backed record in the release and writes the verdicts to
config/cohort1_label_status.json; this module reads that file (never the
network), checks it still describes this release, and assesses each record.

`assess` returns the phase this catalogue states for a record, its label, and
its basis - the reason it is or is not an approval:

  regulator    an FDA or EMA document is cited                       Approved
  label        a cited label holds an application (NDA, ANDA, BLA)   Approved
  monograph    a cited label is sold under an FDA OTC monograph      Approved
  unresolved   a cited label could not be read, and FDA records an
               approval year for the molecule                        Approved
  atc          a WHO ATC class, and no regulator or approved label   Approved
  trial        only trials are cited, one of them Phase 4 in the
               registry                                              Approved
  unsourced    nothing ChEMBL cites says either way; ChEMBL's stands Approved
  unapproved   every cited label is marketed without approval,
               and no regulator or ATC class is cited     the trials' phase,
                                                     or Marketed unapproved
  trial_phase  only trials are cited, none of them Phase 4 in the
               registry                                  the trials' phase,
                                                     or Approval unconfirmed
  unconfirmed  a cited label could not be read, and FDA records no
               approval year for the molecule            the trials' phase,
                                                     or Approval unconfirmed

A Phase 4 trial alone was first read as no approval and labelled so; that put
desipramine's major depression and lidocaine's neuralgia (the Lidoderm patch)
below Approved, both of them approved uses. A post-marketing trial usually
studies the use a drug is approved for, so it stands, and its basis says
what it is. But ChEMBL's 4 on a trial-only record is often not the trial's:
108 of the 115 in-scope ones cite no trial the registry calls Phase 4 (D24,
docs/D23-GAPS.md). Nothing cited there says the drug is approved for that
disease, so the record takes the furthest registry phase of its trials, the
rule an unapproved label already follows. The registry's phases come through
the committed file, as an unapproved record's do.

A label that cannot be read - one older than FDA's structured marketing
category, which states it nowhere, or one neither DailyMed nor RxNav serves -
keeps ChEMBL's Approved only where FDA records an approval year for the
molecule (molecule_dictionary.first_approval, across its forms). Otherwise
nothing stands behind it, and it falls like any other record without support.
No record falls under that guard in ChEMBL 37; it keeps a future one from
standing on nothing.

An fda.gov page filed in ChEMBL's DailyMed slot is an FDA document, and is
read as one (Aucatzyl, a BLA, in ChEMBL 37).

An unapproved record's phase is the furthest the registry records for the
trials ChEMBL cites beside its labels, never ChEMBL's 4: the 4 came from the
labels, which say there is no approval behind them. A cited Phase 4 trial
there is a trial, "Phase 4 trial", not an approval. Where it cites none, it
has no clinical phase, and an indication needs one to admit a molecule (D21),
so a molecule admitted only by such a record leaves the cohort.

A WHO ATC code normally means approval in at least one country, but can be
given once an application is ready to file, and ChEMBL reads the disease off
the class; it is not contradicted here, and the basis says what it is.
"""

from __future__ import annotations

import collections
import json

from . import common

STATUS_FILE = common.CONFIG / "cohort1_label_status.json"

APPROVAL_BASES = ("regulator", "label", "monograph", "unresolved", "atc", "trial",
                  "unsourced")

PHASE4_TRIAL = "Phase 4 trial"
MARKETED_UNAPPROVED = "Marketed unapproved"
UNCONFIRMED = "Approval unconfirmed"

# What a fallen record's phase is read off, beside its basis, for the build's
# molecule-level verdict: every phase-4 record of the family fallen, and none
# of them a Phase 4 trial.
FALLEN_BASES = ("unapproved", "trial_phase", "unconfirmed")

# FDA's marketing categories, as DailyMed prints them, grouped by what they
# say about approval. A category in none of these is not guessed at: its
# record stays `unresolved`, and the generator lists it.
APPLICATION = {"NDA", "ANDA", "BLA", "NDA AUTHORIZED GENERIC"}
UNAPPROVED = {
    "UNAPPROVED DRUG OTHER",
    "UNAPPROVED DRUG FOR USE IN DRUG SHORTAGE",
    "UNAPPROVED HOMEOPATHIC",
    "UNAPPROVED MEDICAL GAS",
    "UNAPPROVED DRUG MARKETED UNDER THE CODIFIED FDA DRUG SHORTAGE",
    "DIETARY SUPPLEMENT",
    "MEDICAL FOOD",
    "EXPORT ONLY",
    "BULK INGREDIENT",
    "BULK INGREDIENT FOR HUMAN PRESCRIPTION COMPOUNDING",
    "BULK INGREDIENT FOR ANIMAL DRUG COMPOUNDING",
    "COSMETIC",
}


def category_kind(category: str) -> str | None:
    c = (category or "").strip().upper()
    if c in APPLICATION:
        return "application"
    if c.startswith("OTC MONOGRAPH"):
        return "monograph"
    if c in UNAPPROVED or c.startswith("UNAPPROVED "):
        return "unapproved"
    return None


def phase4_refs(conn) -> dict[int, dict]:
    """Every phase-4 drug_indication record in the release, with what it cites.

    {drugind_id: {molregno, mesh_id, types: set, dailymed: [set ids in
    ChEMBL's order], trials: [NCT ids]}}. An fda.gov address in the DailyMed
    slot is an FDA document, so it is typed FDA and is not a label.
    """
    out: dict[int, dict] = {}
    for r in conn.execute("SELECT drugind_id, molregno, mesh_id FROM drug_indication"
                          " WHERE max_phase_for_ind = 4"):
        out[r["drugind_id"]] = {"molregno": r["molregno"], "mesh_id": r["mesh_id"],
                                "types": set(), "dailymed": [], "trials": [], "atc": []}
    for r in conn.execute("SELECT drugind_id, ref_type, ref_id FROM indication_refs"
                          " ORDER BY indref_id"):
        rec = out.get(r["drugind_id"])
        if rec is None:
            continue
        if r["ref_type"] == "DailyMed" and is_fda_document(r["ref_id"]):
            rec["types"].add("FDA")
            continue
        rec["types"].add(r["ref_type"])
        if r["ref_type"] == "DailyMed" and r["ref_id"] and r["ref_id"] not in rec["dailymed"]:
            rec["dailymed"].append(r["ref_id"])
        elif r["ref_type"] == "ATC" and r["ref_id"] and r["ref_id"] not in rec["atc"]:
            rec["atc"].append(r["ref_id"].strip())
        elif r["ref_type"] == "ClinicalTrials":
            for t in (r["ref_id"] or "").split(","):
                if t.strip() and t.strip() not in rec["trials"]:
                    rec["trials"].append(t.strip())
    for rec in out.values():
        rec["trials"].sort()
    return out


def is_fda_document(ref_id) -> bool:
    s = (ref_id or "").strip().lower()
    return s.startswith(("https://www.fda.gov/", "http://www.fda.gov/",
                         "https://fda.gov/", "http://fda.gov/"))


def is_label_backed(rec: dict) -> bool:
    return bool(rec["dailymed"]) and not rec["types"] & {"FDA", "EMA"}


def is_trial_only(rec: dict) -> bool:
    """A record citing trials and nothing else that could stand for an approval."""
    return ("ClinicalTrials" in rec["types"] and bool(rec["trials"])
            and not rec["types"] & {"FDA", "EMA", "DailyMed", "ATC"})


def label_backed_records(conn) -> dict[int, dict]:
    """The phase-4 records whose approval rests on a label: DailyMed, no FDA or EMA."""
    return {k: v for k, v in phase4_refs(conn).items() if is_label_backed(v)}


def trial_only_records(conn) -> dict[int, dict]:
    """The phase-4 records whose approval rests on cited trials alone."""
    return {k: v for k, v in phase4_refs(conn).items() if is_trial_only(v)}


class LabelStatus:
    """The committed verdicts, checked against the release they were made from."""

    def __init__(self, conn, path=STATUS_FILE, cfg: dict | None = None):
        """`cfg` stands in for the file in tests; the build always reads the file."""
        self.path = path
        if cfg is None:
            with open(path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        self.cfg = cfg
        if self.cfg.get("chembl_release") != common.CHEMBL_RELEASE:
            raise common.PolicyError(
                f"{path.name} was made from {self.cfg.get('chembl_release')}, the build "
                f"reads {common.CHEMBL_RELEASE}: rerun scripts/check_dailymed_labels.py")
        self.refs = phase4_refs(conn)
        self.by_molregno: dict[int, list[int]] = collections.defaultdict(list)
        for rid, r in self.refs.items():
            self.by_molregno[r["molregno"]].append(rid)
        self.verdicts: dict[int, str] = {}
        for v, ids in self.cfg["checked"].items():
            for rid in ids:
                self.verdicts[int(rid)] = v
        self.records = {int(k): d for k, d in self.cfg["records"].items()}
        for rid, d in self.records.items():
            self.verdicts[rid] = d["verdict"]
        self.trial_only = {int(k): d for k, d in self.cfg.get("trial_only", {}).items()}
        self._conn = conn
        self._fda_years: dict[int, int | None] = {}
        self._check()

    def _check(self) -> None:
        backed = {k: v for k, v in self.refs.items() if is_label_backed(v)}
        unchecked = sorted(set(backed) - set(self.verdicts))
        stale = sorted(set(self.verdicts) - set(backed))
        moved = sorted(rid for rid, d in self.records.items() if rid in backed and
                       sorted(lab["set_id"] for lab in d["labels"])
                       != sorted(backed[rid]["dailymed"]))
        trial = {k: v for k, v in self.refs.items() if is_trial_only(v)}
        unread = sorted(set(trial) - set(self.trial_only))
        stale += sorted(set(self.trial_only) - set(trial))
        moved += sorted(rid for rid, d in self.trial_only.items() if rid in trial and
                        sorted(t["nct"] for t in d["trials"]) != trial[rid]["trials"])
        if unchecked or unread or stale or moved:
            raise common.PolicyError(
                f"{self.path.name} no longer describes {common.CHEMBL_RELEASE}: "
                f"{len(unchecked)} label-backed records unchecked {unchecked[:5]}, "
                f"{len(unread)} trial-only records without registry phases {unread[:5]}, "
                f"{len(stale)} recorded records no longer label-backed or trial-only "
                f"{stale[:5]}, {len(moved)} cite different labels or trials {moved[:5]}. "
                f"Rerun scripts/check_dailymed_labels.py fetch and write.")

    def fda_year(self, molregno: int):
        """FDA's approval year for a molecule, across its parent and every form of it."""
        if molregno not in self._fda_years:
            row = self._conn.execute("SELECT parent_molregno FROM molecule_hierarchy"
                                     " WHERE molregno = ?", (molregno,)).fetchone()
            parent = row[0] if row and row[0] is not None else molregno
            row = self._conn.execute(
                "SELECT MIN(md.first_approval) FROM molecule_dictionary md"
                " LEFT JOIN molecule_hierarchy mh ON mh.molregno = md.molregno"
                " WHERE md.molregno = ? OR mh.parent_molregno = ?",
                (parent, parent)).fetchone()
            self._fda_years[molregno] = row[0] if row else None
        return self._fda_years[molregno]

    @staticmethod
    def _fallen(phase, basis: str) -> tuple:
        """A record nothing cited approves: the furthest phase of the trials it cites."""
        if phase is None:
            return None, (MARKETED_UNAPPROVED if basis == "unapproved" else UNCONFIRMED), basis
        if phase >= 4:
            return 4.0, PHASE4_TRIAL, basis
        return phase, common.phase_label(phase), basis

    def assess(self, drugind_id: int, chembl_phase) -> tuple:
        """(phase, phase_label, basis) for one record; basis None below phase 4."""
        if chembl_phase is None or float(chembl_phase) < 4:
            return chembl_phase, common.phase_label(chembl_phase), None
        rec = self.refs.get(drugind_id)
        types = rec["types"] if rec else set()
        if types & {"FDA", "EMA"}:
            return 4.0, "Approved", "regulator"
        if "DailyMed" in types:
            v = self.verdicts[drugind_id]
            if v not in ("unapproved", "unresolved"):
                return 4.0, "Approved", v
            if "ATC" in types:
                return 4.0, "Approved", "atc"
            if v == "unresolved":
                if self.fda_year(rec["molregno"]):
                    return 4.0, "Approved", "unresolved"
                return self._fallen(self.records[drugind_id].get("trial_phase"),
                                    "unconfirmed")
            return self._fallen(self.records[drugind_id].get("trial_phase"), "unapproved")
        if "ATC" in types:
            return 4.0, "Approved", "atc"
        if drugind_id in self.trial_only:
            p = self.trial_only[drugind_id].get("trial_phase")
            if p is not None and p >= 4:
                return 4.0, "Approved", "trial"
            return self._fallen(p, "trial_phase")
        return 4.0, "Approved", "unsourced"

    def unapproved_labels(self, drugind_id: int) -> list[dict]:
        d = self.records.get(drugind_id)
        return d["labels"] if d and d["verdict"] == "unapproved" else []

    def unread_reason(self, drugind_id: int) -> str | None:
        """Why an `unresolved` or `unconfirmed` record's labels could not be read.

        'no marketing table' where DailyMed serves a label stating no category
        (one older than FDA's structured category), 'not served' where neither
        DailyMed nor RxNav holds it; both, '|'-joined, where its labels differ.
        """
        d = self.records.get(drugind_id)
        if not d or d["verdict"] != "unresolved":
            return None
        reasons = sorted({lab["unread"] for lab in d["labels"] if lab.get("unread")})
        return "|".join(reasons) or None

    def atc_classes(self, drugind_id: int) -> list[str]:
        """The WHO ATC classes an `atc` record cites, as 'N05BA (anxiolytics:
        benzodiazepine derivatives)': the level-4 code and the words of levels
        3 and 4, which is the class ChEMBL read the disease off."""
        rec = self.refs.get(drugind_id)
        out = []
        for code in (rec or {}).get("atc", []):
            row = self._conn.execute(
                "SELECT level4, level3_description, level4_description"
                " FROM atc_classification WHERE level5 = ? OR level4 = ?"
                " ORDER BY level5 LIMIT 1", (code, code)).fetchone()
            if row is None:
                text = code
            else:
                words = [w.lower() for w in (row[1], row[2]) if w]
                text = row[0] + (f" ({': '.join(words)})" if words else "")
            if text not in out:
                out.append(text)
        return out

    def is_approval(self, drugind_id: int, chembl_phase) -> bool:
        return self.assess(drugind_id, chembl_phase)[2] in APPROVAL_BASES

    def molecule_status(self, family: list[int], chembl_max_phase, first_approval):
        """(approval_status, max_phase_checked) for a molecule family.

        ChEMBL's molecule-level 4 is taken back only where its family has
        phase-4 records, FDA records no approval year for any form, and every
        one of those records has fallen (FALLEN_BASES) with no Phase 4 trial
        beside it. A Phase 4 trial is post-marketing - the drug is approved
        somewhere - so it is never read as the absence of an approval.
        'unapproved_marketing' where every one is an unapproved label,
        'no_approval_cited' where some rest on trials or unread labels instead.
        Returns (None, chembl_max_phase) wherever ChEMBL's stands.
        """
        if chembl_max_phase is None or float(chembl_max_phase) < 4 or first_approval:
            return None, chembl_max_phase
        recs = [rid for m in family for rid in self.by_molregno.get(m, ())]
        if not recs:
            return None, chembl_max_phase
        phases, bases = [], set()
        for rid in recs:
            phase, label, basis = self.assess(rid, 4)
            if basis not in FALLEN_BASES or label == PHASE4_TRIAL:
                return None, chembl_max_phase
            bases.add(basis)
            if phase is not None:
                phases.append(phase)
        status = "unapproved_marketing" if bases == {"unapproved"} else "no_approval_cited"
        return status, (max(phases) if phases else None)

    def summary(self) -> dict:
        bases = collections.Counter(self.assess(rid, 4)[2] for rid in self.refs)
        return {"file": f"config/{self.path.name}", "version": self.cfg.get("version"),
                "sha256": common.sha256(self.path),
                "labels_read": self.cfg.get("labels_read", {}),
                "bases": dict(sorted(bases.items()))}
