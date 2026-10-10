#!/usr/bin/env python3
"""Backfill target_orthologues into db/cohort1.db: the human protein each
non-human record is, found by sequence (D20).

ChEMBL files one protein once per species it was assayed in, and the
similarity score used to count each species' record as a separate shared
target. Naloxone and naltrexone's "12 shared targets" were the mu, kappa and
delta opioid receptors in up to four species, and CYP2D6; the rat and
guinea-pig records even weighed more than the human ones, because fewer
molecules are measured on them and the rarity term read that as rarity. The
viewer now counts a protein once, and this is what tells it which records are
one protein.

No identifier says so. ChEMBL records no orthology (its EQUIVALENT TO
relations join a species record to a broader taxon), NCBI's orthologue list
reaches a UniProt accession only through a GeneID the guinea-pig mu receptor
does not carry, OrthoDB puts mu and kappa in one group, and a gene symbol is
never a matching key (invariant 6). So the answer is read off the sequences,
by the textbook definition of an orthologue - reciprocal best match - with
the refusals invariant 6 asks for:

  1. Forward. The record's sequence (from the pinned ChEMBL release) is
     scored against every protein in UniProt's reviewed human proteome
     (pinned, sha256 in build_manifest), and the SHORTLIST best by alignment
     score are aligned again for their identity: matched residues over the
     record's own length, so a 98-residue fragment - the guinea-pig mu
     receptor, P97266, is one - is judged on the part that exists and a short
     human peptide cannot look identical to a whole receptor.
  2. The best must reach MIN_IDENTITY (MIN_IDENTITY_FRAGMENT where the record
     covers less than FULL_LENGTH of it, because a fragment from a conserved
     stretch has less room to differ) and lead the runner-up (`leads`): by
     MIN_LEAD, or with the runner-up differing at least MIN_DIFF_RATIO times
     as much. Rat Oprk1 is 94% identical to human OPRK1 and 57-59% to OPRM1
     and OPRD1, a lead of 35 points. The ratio is for the conserved families,
     where a true orthologue and its nearest paralogue are both close: rat
     Scn3a is 97.2% SCN3A and 87.8% SCN2A, 9.4 points but four times the
     differences. Human DHFR and its retrogene DHFR2 (87% and 84% to rat
     Dhfr) pass neither, and are refused rather than guessed.
  3. Reverse. The human protein is scored against every protein ChEMBL holds
     for the record's species, by identity over the shorter of each pair.
     A species protein near-identical to the record (SAME_PROTEIN) is the same
     protein filed twice - guinea pig has the mu receptor as the P97266
     fragment and as full-length Q8CGM4, and rat has the noradrenaline
     transporter three times over, 91% to 99.7% identical to each other - and
     is set aside. The bar sits at 90% because that is what the rat
     transporter needs, and it is still well clear of a real rodent gene
     cluster: Cyp2d3 and Cyp2d26 are 78% identical. Any other is a
     rival only if its *own* best human match is this human protein too, and
     the record must lead every rival by the same test. That refuses a rodent
     gene cluster with one human counterpart (the Cyp2d genes against
     CYP2D6), where each rodent gene reaches the human one and none of them is
     the one; and it does not let a fragment of a different protein block a
     match on the strength of a conserved stretch (the mu fragment is 82%
     identical to human kappa over its 98 residues, and 98% to mu, which is
     where it belongs).
  4. One to one. Two accessions of one species matched to one human protein
     are both refused, unless they are the same protein by SAME_PROTEIN.

Only mammals are matched (ChEMBL's organism_class, l2 = 'Mammalia'): below
them an orthologue can sit under the identity bar, and a bar low enough for
fish would admit mammalian paralogues. Every other record keeps its own
identity, as does every record refused here, with its reason; the viewer
counts such a record as its own protein, which is what it did before this
existed. A family or a complex is never matched - it is not one sequence.

A separate backfill, not part of a build: it reads ChEMBL read-only, touches
the network once to fetch the proteome (cached under db/cache/uniprot/, with
UniProt's release name beside it), and changes only target_orthologues and
one build_manifest key. The alignments take a few minutes across all cores
the first time and are cached against the proteome's sha256 and the scoring
parameters. Needs parasail (requirements.txt).
"""

from __future__ import annotations

import argparse
import collections
import datetime
import gzip
import hashlib
import heapq
import json
import multiprocessing
import os
import pathlib
import re
import sqlite3
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cohort import common

TABLE = "target_orthologues"

CACHE = common.DB / "cache" / "uniprot"
REFERENCE_URL = ("https://rest.uniprot.org/uniprotkb/stream?compressed=true&format=fasta"
                 "&query=%28reviewed%3Atrue%29+AND+%28organism_id%3A9606%29")
REFERENCE_FILE = CACHE / "human_reviewed.fasta.gz"
# UniProt names its release in a response header and nowhere in the file.
RELEASE_FILE = CACHE / "human_reviewed.release"
HITS_FILE = CACHE / "orthologue_hits.json"
# Bumped whenever what a cached alignment result means changes.
HITS_VERSION = 3
HUMAN_TAX_ID = 9606

# BLAST's defaults for BLOSUM62.
GAP_OPEN, GAP_EXTEND = 11, 1
# How many of the best-scoring proteins are aligned again for their identity.
# Identity and score rank alike for full-length proteins; the shortlist is what
# lets a fragment, whose raw score is small against everything, be judged on
# identity among the proteins it resembles most.
SHORTLIST = 10
MIN_IDENTITY = 0.70
MIN_IDENTITY_FRAGMENT = 0.90
FULL_LENGTH = 0.80
MIN_LEAD = 0.10
MIN_DIFF_RATIO = 3.0
SAME_PROTEIN = 0.90

PARAMS = {"matrix": "blosum62", "gap_open": GAP_OPEN, "gap_extend": GAP_EXTEND,
          "shortlist": SHORTLIST, "min_identity": MIN_IDENTITY,
          "min_identity_fragment": MIN_IDENTITY_FRAGMENT, "full_length": FULL_LENGTH,
          "min_lead": MIN_LEAD, "min_diff_ratio": MIN_DIFF_RATIO,
          "same_protein": SAME_PROTEIN}

# The letters BLOSUM62 scores; anything else (U, O, J) is scored as X.
_ALPHABET = set("ARNDCQEGHILKMFPSTWYVBZX")


def clean(seq):
    return "".join(c if c in _ALPHABET else "X" for c in seq.upper())


# ------------------------------------------------------------------ files

def ensure_reference(path=REFERENCE_FILE, url=REFERENCE_URL, refresh=False):
    """The proteome, downloaded once. UniProt's "stream" answers the current
    release, so the copy is kept and is what every run reads until --refresh
    replaces it; its sha256 and release name go into build_manifest."""
    if path.exists() and not refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {url} ...")
    tmp = path.with_suffix(path.suffix + ".part")
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in resp.raw.stream(1 << 20, decode_content=False):
                fh.write(chunk)
        release = resp.headers.get("X-UniProt-Release", "")
    tmp.rename(path)
    RELEASE_FILE.write_text(release + "\n")
    return path


def load_fasta(path):
    """{accession: (sequence, gene symbol or None)} from a UniProt FASTA.

    The gene symbol is the header's GN= field, read for the audit in
    main() and nothing else: it is never used to match.
    """
    out, acc, gene, parts = {}, None, None, []
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as fh:
        for line in fh:
            if line.startswith(">"):
                if acc:
                    out[acc] = ("".join(parts), gene)
                acc = line.split("|")[1]
                m = re.search(r" GN=(\S+)", line)
                gene, parts = (m.group(1) if m else None), []
            else:
                parts.append(line.strip())
    if acc:
        out[acc] = ("".join(parts), gene)
    return out


# ------------------------------------------------------------- alignment

class Aligner:
    """Two operations on parasail, semi-global with free end gaps (a fragment
    is not penalised for the part of the protein it lacks): the best-scoring
    library entries for a query, and one pair's matched residues."""

    def __init__(self):
        import parasail
        self.p = parasail
        self.matrix = parasail.blosum62

    def shortlist(self, query, library, n=SHORTLIST):
        """The n library accessions scoring highest against query.
        library: [(accession, sequence)]."""
        prof = self.p.profile_create_sat(query, self.matrix)
        scored = ((self.p.sg_striped_profile_sat(prof, seq, GAP_OPEN, GAP_EXTEND).score, acc)
                  for acc, seq in library)
        return [acc for _, acc in heapq.nlargest(n, scored)]

    def matches(self, a, b):
        return self.p.sg_stats_striped_sat(a, b, GAP_OPEN, GAP_EXTEND, self.matrix).matches


def forward_hits(aligner, query, library, by_acc):
    """[(accession, identity, coverage)] for the shortlist, best identity
    first. Identity is over the query's own length; coverage is the shorter
    length over the longer."""
    out = []
    for acc in aligner.shortlist(query, library):
        seq = by_acc[acc]
        out.append((acc, aligner.matches(query, seq) / len(query),
                    min(len(query), len(seq)) / max(len(query), len(seq))))
    out.sort(key=lambda h: (-h[1], h[0]))
    return out


def reverse_hits(aligner, human_seq, record_acc, library, by_acc):
    """[(accession, identity, same)] for the human protein's shortlist in the
    record's species, the record always included, best identity first.

    Identity is over the *shorter* sequence of each pair: over the human
    protein's length a fragment record scores its length ratio (the guinea-pig
    mu fragment read 24% against human OPRM1), and over each species protein's
    own length a short peptide could look identical to a receptor. `same`
    says the species protein is the record filed again (SAME_PROTEIN)."""
    record = by_acc[record_acc]
    out = []
    for acc in dict.fromkeys(aligner.shortlist(human_seq, library) + [record_acc]):
        seq = by_acc[acc]
        ident = aligner.matches(human_seq, seq) / min(len(human_seq), len(seq))
        same = acc != record_acc and (
            aligner.matches(record, seq) / min(len(record), len(seq)) >= SAME_PROTEIN)
        out.append((acc, ident, same))
    out.sort(key=lambda h: (-h[1], h[0]))
    return out


# ---------------------------------------------------------------- decide

def leads(best, other):
    """Whether an identity of `best` is clearly ahead of `other`: by MIN_LEAD,
    or with `other` carrying MIN_DIFF_RATIO times the differences."""
    if best - other >= MIN_LEAD:
        return True
    return (1 - other) >= MIN_DIFF_RATIO * (1 - best) and best > other


def decide(accession, forward, reverse, best_human_of):
    """Whether one record is matched, and to what. Pure, so the rules can be
    tested without an aligner.

    forward: [(human accession, identity, coverage)], best identity first.
    reverse: [(species accession, identity, same)] for the best human protein
    against the record's species, or None where there is no best.
    best_human_of: {species accession: its own best human accession}, for the
    species proteins that could be rivals.
    Returns a dict of the target_orthologues columns this decides.
    """
    row = {"human_accession": None, "best_accession": None, "identity": None,
           "runner_up": None, "runner_up_identity": None, "coverage": None}
    if not forward:
        return dict(row, status="no_human_hit")
    best, ident, cov = forward[0]
    row.update(best_accession=best, identity=round(ident, 4), coverage=round(cov, 4))
    if len(forward) > 1:
        row.update(runner_up=forward[1][0], runner_up_identity=round(forward[1][1], 4))
    fragment = cov < FULL_LENGTH
    if ident < (MIN_IDENTITY_FRAGMENT if fragment else MIN_IDENTITY):
        return dict(row, status="fragment_below_identity" if fragment else "below_identity")
    if len(forward) > 1 and not leads(ident, forward[1][1]):
        return dict(row, status="no_lead_over_runner_up")
    mine = next((i for a, i, _ in reverse or () if a == accession), None)
    if mine is None:
        return dict(row, status="not_reciprocal")
    rivals = [i for a, i, same in reverse
              if a != accession and not same and best_human_of.get(a) == best]
    if any(i > mine for i in rivals):
        return dict(row, status="not_reciprocal")
    if any(not leads(mine, i) for i in rivals):
        return dict(row, status="no_lead_in_species")
    return dict(row, human_accession=best, status="matched")


def one_to_one(rows, same_protein):
    """Refuse every match where two accessions of one species that are not the
    same protein reach one human protein. rows: {target: row dict with
    accession, tax_id}; same_protein(tax_id, a, b) -> bool. In place."""
    reach = collections.defaultdict(set)
    for r in rows.values():
        if r["human_accession"]:
            reach[(r["tax_id"], r["human_accession"])].add(r["accession"])
    for r in rows.values():
        if not r["human_accession"]:
            continue
        others = reach[(r["tax_id"], r["human_accession"])] - {r["accession"]}
        if any(not same_protein(r["tax_id"], r["accession"], o) for o in others):
            r["human_accession"] = None
            r["status"] = "several_records_one_protein"
    return rows


# --------------------------------------------------------------- workers

_W = {}


def _init(human, species):
    _W["aligner"] = Aligner()
    _W["human"] = human
    _W["human_lib"] = list(human.items())
    _W["species"] = species
    _W["species_lib"] = {t: list(s.items()) for t, s in species.items()}


def _forward(query):
    return forward_hits(_W["aligner"], query, _W["human_lib"], _W["human"])


def _reverse(job):
    human_acc, tax_id, record_acc = job
    return reverse_hits(_W["aligner"], _W["human"][human_acc], record_acc,
                        _W["species_lib"][tax_id], _W["species"][tax_id])


def _seq_key(seq):
    return hashlib.md5(seq.encode()).hexdigest()


def _rev_key(job):
    return "|".join(map(str, job))


def load_cache(path, header):
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {"header": header, "forward": {}, "reverse": {}}
    if data.get("header") != header:
        return {"header": header, "forward": {}, "reverse": {}}
    return data


def run(records, human, species, cache, workers):
    """Align what the cache lacks, in three passes: every record forward, each
    record's best human protein back against its species, then forward again
    for the species proteins that came close enough to be rivals.
    records: {target: (accession, tax_id, seq)}."""
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(workers, initializer=_init, initargs=(human, species)) as pool:
        def forward(seqs, what):
            todo = sorted({_seq_key(s): s for s in seqs
                           if _seq_key(s) not in cache["forward"]}.items())
            if todo:
                print(f"  aligning {len(todo)} {what} against {len(human)} human proteins ...")
                for (key, _), got in zip(todo, pool.map(_forward, [s for _, s in todo],
                                                         chunksize=4)):
                    cache["forward"][key] = got

        forward([s for _, _, s in records.values()], "records")
        jobs = sorted(job for job in {(cache["forward"][_seq_key(s)][0][0], tax_id, acc)
                                      for acc, tax_id, s in records.values()
                                      if cache["forward"][_seq_key(s)]}
                      if _rev_key(job) not in cache["reverse"])
        if jobs:
            print(f"  aligning {len(jobs)} human proteins back against their species ...")
            for job, got in zip(jobs, pool.map(_reverse, jobs, chunksize=4)):
                cache["reverse"][_rev_key(job)] = got
        forward([species[tax_id][acc] for tax_id, acc in rivals(records, cache)],
                "possible rivals")
    return cache


def rivals(records, cache):
    """(tax_id, accession) of every species protein close enough to a
    record's human match to be a rival, whose own best match decides it."""
    out = set()
    for acc, tax_id, seq in records.values():
        fwd = cache["forward"][_seq_key(seq)]
        if not fwd:
            continue
        rev = cache["reverse"][_rev_key((fwd[0][0], tax_id, acc))]
        mine = next((i for a, i, _ in rev if a == acc), 0)
        for a, i, same in rev:
            if a != acc and not same and not (mine - i >= MIN_LEAD):
                out.add((tax_id, a))
    return sorted(out)


# --------------------------------------------------------------- backfill

def ensure_table(conn):
    have = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (TABLE,)).fetchone()
    if have:
        return False
    schema = (common.DB / "schema_cohort.sql").read_text()
    m = re.search(r"CREATE TABLE IF NOT EXISTS " + TABLE + r" \(.*?\n\);", schema, re.S)
    if not m:
        raise common.PolicyError(f"{TABLE} is missing from schema_cohort.sql")
    conn.execute(m.group(0))
    return True


def candidates(conn, chembl):
    """{target: (accession, tax_id)} for every non-human, mammalian,
    single-component SINGLE PROTEIN in the catalogue."""
    mammals = {t for (t,) in chembl.execute(
        "SELECT tax_id FROM organism_class WHERE l2 = 'Mammalia'")}
    out = {}
    for tid, tax_id, accs in conn.execute(
            "SELECT t.chembl_id, t.tax_id, group_concat(c.accession, '|')"
            " FROM targets t JOIN target_components c ON c.target_chembl_id = t.chembl_id"
            " WHERE t.target_type = 'SINGLE PROTEIN' AND t.tax_id != ?"
            " GROUP BY t.chembl_id ORDER BY t.chembl_id", (HUMAN_TAX_ID,)):
        if tax_id in mammals and "|" not in accs:
            out[tid] = (accs, tax_id)
    return out


def species_sequences(chembl, tax_ids):
    """{tax_id: {accession: sequence}}: every protein ChEMBL holds for each."""
    out = collections.defaultdict(dict)
    marks = ",".join("?" * len(tax_ids))
    for acc, tax_id, seq in chembl.execute(
            "SELECT accession, tax_id, sequence FROM component_sequences"
            f" WHERE component_type = 'PROTEIN' AND tax_id IN ({marks})"
            " AND accession IS NOT NULL AND sequence IS NOT NULL", sorted(tax_ids)):
        out[tax_id][acc] = clean(seq)
    return dict(out)


def resolve(cands, species, cache, same_protein):
    rows = {}
    for tid, (acc, tax_id) in cands.items():
        seq = species.get(tax_id, {}).get(acc)
        base = {"target_chembl_id": tid, "accession": acc, "tax_id": tax_id}
        if not seq:
            rows[tid] = dict(base, human_accession=None, best_accession=None, identity=None,
                             runner_up=None, runner_up_identity=None, coverage=None,
                             status="no_sequence")
            continue
        fwd = [tuple(h) for h in cache["forward"][_seq_key(seq)]]
        rev, best_of = None, {}
        if fwd:
            rev = [tuple(h) for h in cache["reverse"][_rev_key((fwd[0][0], tax_id, acc))]]
            for a, _, _ in rev:
                got = cache["forward"].get(_seq_key(species[tax_id][a]))
                if got:
                    best_of[a] = got[0][0]
        rows[tid] = dict(base, **decide(acc, fwd, rev, best_of))
    return one_to_one(rows, same_protein)


COLUMNS = ["target_chembl_id", "accession", "tax_id", "human_accession", "best_accession",
           "identity", "runner_up", "runner_up_identity", "coverage", "status"]


def write(conn, rows):
    ensure_table(conn)
    before = {tuple(r) for r in conn.execute(f"SELECT * FROM {TABLE}")}
    conn.execute(f"DELETE FROM {TABLE}")
    conn.executemany(f"INSERT INTO {TABLE}({','.join(COLUMNS)}) VALUES "
                     f"({','.join('?' * len(COLUMNS))})",
                     [tuple(r[c] for c in COLUMNS)
                      for r in sorted(rows.values(), key=lambda r: r["target_chembl_id"])])
    after = {tuple(r) for r in conn.execute(f"SELECT * FROM {TABLE}")}
    return len(before ^ after)


def audit(conn, rows, human_genes):
    """Where the sequence match and the gene symbols disagree - read, never
    used. A match whose human gene is not the record's own symbol, case aside,
    and a refusal where they would have agreed, are both listed for a person."""
    own = {t: g for t, g in conn.execute(
        "SELECT target_chembl_id, gene_symbol FROM target_components")}
    agree, differ, refused_same = 0, [], []
    for tid, r in sorted(rows.items()):
        mine = (own.get(tid) or "").upper()
        if r["human_accession"]:
            theirs = (human_genes.get(r["human_accession"]) or "").upper()
            if mine and mine == theirs:
                agree += 1
            else:
                differ.append((tid, own.get(tid), r["human_accession"],
                               human_genes.get(r["human_accession"]), r["identity"]))
        elif r["best_accession"] and mine and mine == (human_genes.get(r["best_accession"]) or "").upper():
            refused_same.append((tid, own.get(tid), r["best_accession"], r["status"], r["identity"],
                                 r["runner_up"], r["runner_up_identity"]))
    return agree, differ, refused_same


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report, write nothing")
    parser.add_argument("--refresh", action="store_true",
                        help="re-download UniProt's human proteome instead of reading the cached copy")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--db", type=pathlib.Path, default=common.COHORT_DB)
    args = parser.parse_args(argv)
    if not args.db.exists():
        raise SystemExit(f"{args.db} does not exist.")

    ref = ensure_reference(refresh=args.refresh)
    release = RELEASE_FILE.read_text().strip() if RELEASE_FILE.exists() else ""
    proteome = load_fasta(ref)
    human = {acc: clean(seq) for acc, (seq, _) in proteome.items()}
    human_genes = {acc: g for acc, (_, g) in proteome.items()}

    conn = sqlite3.connect(args.db, isolation_level=None)
    chembl = common.chembl()
    try:
        cands = candidates(conn, chembl)
        species = species_sequences(chembl, {t for _, t in cands.values()})
        records = {tid: (acc, tax, species[tax][acc]) for tid, (acc, tax) in cands.items()
                   if acc in species.get(tax, {})}
        header = {"version": HITS_VERSION,
                  "reference_sha256": common.sha256(ref), "chembl_release": common.CHEMBL_RELEASE,
                  "params": {k: PARAMS[k] for k in ("matrix", "gap_open", "gap_extend",
                                                    "shortlist", "same_protein")}}
        cache = run(records, human, species, load_cache(HITS_FILE, header), args.workers)
        HITS_FILE.write_text(json.dumps(cache))
        aligner = Aligner()

        def same_protein(tax_id, a, b):
            x, y = species[tax_id][a], species[tax_id][b]
            return aligner.matches(x, y) / min(len(x), len(y)) >= SAME_PROTEIN

        rows = resolve(cands, species, cache, same_protein)
        counts = collections.Counter(r["status"] for r in rows.values())
        agree, differ, refused_same = audit(conn, rows, human_genes)
        summary = {
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "reference": "UniProtKB reviewed, Homo sapiens", "reference_release": release,
            "reference_sha256": header["reference_sha256"], "reference_proteins": len(human),
            "chembl_release": common.CHEMBL_RELEASE, "params": PARAMS,
            "records": len(rows), "counts": dict(counts),
            "audit": {"matched_same_symbol": agree, "matched_other_symbol": len(differ),
                      "refused_same_symbol": len(refused_same)},
        }
        conn.execute("BEGIN")
        summary["rows_changed"] = write(conn, rows)
        conn.execute("INSERT OR REPLACE INTO build_manifest(key, value) VALUES(?, ?)",
                     ("target_orthologues", json.dumps(summary, sort_keys=True)))
        conn.execute("ROLLBACK" if args.dry_run else "COMMIT")
    finally:
        conn.close()
        chembl.close()

    print(f"{counts.get('matched', 0)} of {len(rows)} non-human mammalian records matched to a "
          f"human protein; {summary['rows_changed']} rows changed"
          + (" - dry run, nothing written" if args.dry_run else ""))
    for k, n in sorted(counts.items()):
        print(f"  {n:5d}  {k}")
    print(f"  audit: {agree} matches carry the record's own gene symbol, {len(differ)} another;"
          f" {len(refused_same)} refusals would have agreed on symbol")
    for tid, g, h, hg, ident in differ:
        print(f"    matched, symbols differ: {tid} {g} -> {h} {hg} ({ident})")
    for tid, g, h, status, ident, runner, runner_ident in refused_same:
        print(f"    refused, symbols agree:  {tid} {g} ~ {h} {status} ({ident}; "
              f"runner-up {runner} {human_genes.get(runner)} {runner_ident})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
