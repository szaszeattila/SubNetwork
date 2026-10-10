#!/usr/bin/env python3
"""
Build the SubNetwork SQLite database from public data sources.

Seeds the molecules listed in SEED_MOLECULES (currently twenty-eight, in three
cohorts: seven methylxanthines and their PDE/ACHE partners, seven picked to
densify the targets the first produced, then fourteen picked to corroborate
the single-edge targets the second cohort left behind - see the comments on
SEED_MOLECULES itself), pulling from PubChem, ChEMBL, DGIdb, UniProt,
BindingDB and the PDSP Ki database. To add another molecule, add its ChEMBL ID
to SEED_MOLECULES and rerun.

Reruns are idempotent: each molecule's existing edges are dropped and
rebuilt from what the sources report *now*, so a correction that removes a
measurement actually removes it (see reset_molecule). Pass --rebuild to
discard the whole database and start from an empty file instead.
"""

import argparse
import csv
import datetime
import math
import pathlib
import sqlite3
import time

import requests

import chembl_local

DB_PATH = pathlib.Path(__file__).parent.parent / "db" / "subnetwork.db"
SCHEMA_PATH = pathlib.Path(__file__).parent.parent / "db" / "schema.sql"

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
DGIDB_BASE = "https://dgidb.org/api/graphql"
UNIPROT_BASE = "https://rest.uniprot.org"
BINDINGDB_BASE = "https://bindingdb.org/rest"
# PDSP has no query API (the web search form filters client-side, not
# server-side) - the only reliable path is their bulk CSV export, cached
# locally since it's ~20MB and doesn't change within a dev session.
PDSP_CSV_URL = "https://pdspdb.unc.edu/databases/kiDownload/download.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
PDSP_CACHE_PATH = pathlib.Path(__file__).parent.parent / "db" / "pdsp_ki_database.csv"

TODAY = datetime.date.today().isoformat()

# Seed set: molecules to load, identified by name + known ChEMBL ID.
SEED_MOLECULES = [
    {"name": "caffeine", "chembl_id": "CHEMBL113"},
    # Methylxanthine like caffeine; ChEMBL confirms a curated "adenosine
    # receptor antagonist" mechanism spanning all four ADORA subtypes plus
    # real Ki data at each individual subtype - same target set as caffeine.
    {"name": "theophylline", "chembl_id": "CHEMBL1355736"},
    # Fourth methylxanthine (cacao/chocolate); expected to share the ADORA1/
    # 2A/2B/3 family with caffeine/theophylline, generally weaker affinity.
    {"name": "theobromine", "chembl_id": "CHEMBL1114"},
    # Selective ADORA2A antagonist, FDA-approved Parkinson's adjunct
    # (Nourianz) - a highly-selective single-target counterpoint to the
    # promiscuous methylxanthines above, all converging on ADORA2A.
    {"name": "istradefylline", "chembl_id": "CHEMBL431770"},
    # Prototypical selective PDE4 inhibitor (research tool compound); same
    # PDE4A/B/C/D target family as theophylline's curated mechanism.
    {"name": "rolipram", "chembl_id": "CHEMBL63"},
    # PDE3 inhibitor, FDA-approved antiplatelet/vasodilator (Pletal); same
    # PDE3A/PDE3B target family as theophylline's curated mechanism.
    {"name": "cilostazol", "chembl_id": "CHEMBL799"},
    # Acetylcholinesterase inhibitor, FDA-approved Alzheimer's drug
    # (Aricept); ACHE was previously only a single-measurement off-target
    # lead from caffeine's BindingDB data - this adds a real curated
    # mechanism at that same target.
    {"name": "donepezil", "chembl_id": "CHEMBL502"},
    # --- Second cohort: chosen to densify the existing target set, not to
    # open new territory. Each one was picked from a ChEMBL 37 sweep of every
    # molecule with a curated mechanism or a qualifying binding measurement
    # against the 51 targets the first seven produced (see
    # docs/DATA-QUALITY-LOG.md, "Choosing the second seven"). Salt forms that
    # ChEMBL lists as separate molecules but that reduce to a molecule already
    # seeded - caffeine citrate, aminophylline, oxtriphylline, theophylline
    # sodium glycinate - were excluded: they would have drawn the same edges
    # twice under different names.
    #
    # Highest-reach candidate in the whole sweep: a curated mechanism at 13 of
    # the 51 - ADORA2A/2B antagonist plus inhibitor at PDE1A/1B/1C, PDE2A,
    # PDE3A/3B, PDE4A/B/C/D and PDE5A - and binding data at ACHE besides. It
    # is also a fourth methylxanthine, so it welds the xanthine cluster to the
    # PDE cluster through a single node rather than leaving them adjacent.
    {"name": "pentoxifylline", "chembl_id": "CHEMBL628"},
    # Binding data at 10 of the 51 (81 qualifying rows): PDE5A, PDE1A, PDE2A,
    # PDE3A, PDE4A/B/D, plus ADORA1/ADORA2A and KCNH2. The PDE5-selective
    # counterpoint to pentoxifylline's pan-PDE profile, and the only candidate
    # that reaches the adenosine receptors and hERG from the PDE side.
    {"name": "sildenafil", "chembl_id": "CHEMBL192"},
    # Three families in one node: CACNA1C (L-type calcium channel), KCNH2
    # (hERG) and ABCB1 (efflux transporter) each currently hang off a single
    # edge. 91 qualifying binding rows.
    {"name": "verapamil", "chembl_id": "CHEMBL6966"},
    # Curated dual ACHE + BCHE inhibitor, FDA-approved Alzheimer's drug
    # (Exelon), plus binding at FAAH. Donepezil is ACHE-selective; this is the
    # dual-cholinesterase contrast at the same targets, and BCHE and FAAH are
    # both single-edge targets today.
    {"name": "rivastigmine", "chembl_id": "CHEMBL636"},
    # First cholinesterase inhibitor approved for Alzheimer's (withdrawn for
    # hepatotoxicity), and the most heavily measured candidate in the sweep -
    # 340 qualifying binding rows across ACHE, BCHE, APP and KCNH2. APP is a
    # headline Alzheimer's protein sitting at one edge.
    {"name": "tacrine", "chembl_id": "CHEMBL95"},
    # Curated MAOB inhibitor (133 binding rows), FDA-approved for Parkinson's.
    # A selective single-target counterpoint at MAOB in the same way
    # istradefylline is one at ADORA2A, and it pairs with istradefylline on
    # indication as well as on target.
    {"name": "selegiline", "chembl_id": "CHEMBL972"},
    # Curated CNR1 modulator with binding at HRH3 and ADRA2C - three
    # brain-expressed targets that each sit at a single edge today, reached by
    # one widely-recognised molecule.
    {"name": "cannabidiol", "chembl_id": "CHEMBL190461"},
    # --- Third cohort: chosen to pay down the periphery the second cohort
    # created, not to add more of it. After the doubling to 14, 93 of the 141
    # targets sat at a single edge - mostly the new molecules' own off-targets
    # (see docs/DATA-QUALITY-LOG.md, "choosing the third fourteen"). So the
    # brief here was corroboration: reach targets that already exist and have
    # only one opinion on them, while adding as few new nodes as possible.
    #
    # Two changes to how candidates were ranked, both because the previous
    # ranking would have picked badly:
    #
    #   - Rank on distinct *single-protein* ChEMBL targets, not on accessions.
    #     Ranking on accessions put GABAPENTIN and SULOCTIDIL at the top with
    #     26 hits each - one mechanism record against the voltage-gated
    #     calcium channel complex, fanned out over 26 subunits. That is one
    #     assertion, and the viewer already collapses it into one row.
    #   - Score each pick by what it adds to the picks already made, on both
    #     sides: orphan targets newly covered, minus new off-target nodes
    #     newly dragged in. Three antipsychotics each covering DRD1/2/3 look
    #     like three wins and are one, and the second one's off-targets are
    #     largely the first one's.
    #
    # Predicted from the ChEMBL sweep: 34 of the 93 single-edge targets get a
    # second opinion, for 38 new targets. The rebuild did better on both
    # counts and worse on neither's sign - 50 covered, 66 added - because the
    # sweep sees only ChEMBL while five of the six sources are queried live,
    # and PDSP contributes whole receptor panels for these molecules. Treat a
    # sweep score as a ranking, not a forecast. Against 90 targets added by
    # the second cohort, and the single-edge count fell 93 -> 81 while the
    # target set grew 141 -> 207.
    #
    # The largest block of orphans by far is the aminergic panel that
    # cannabidiol, tacrine and verapamil were screened against. Haloperidol
    # is its anchor: 343 qualifying binding rows, a curated D2/5-HT2A
    # mechanism, and 11 orphans in one molecule - DRD1/2/3, SIGMAR1, TMEM97,
    # OPRM1, HRH2, SLC6A2/4, ADRA1D, GRIN2B.
    {"name": "haloperidol", "chembl_id": "CHEMBL54"},
    # The atypical against haloperidol's typical, at the same two curated
    # targets: weak at D2, strong at 5-HT2A, where haloperidol is the
    # reverse. Two molecules with the same target list and a different
    # balance across it is the case the graph exists to show, and shared-
    # target overlap alone cannot tell them apart. 286 binding rows.
    {"name": "clozapine", "chembl_id": "CHEMBL42"},
    # Curated serotonin + norepinephrine transporter inhibitor, and the one
    # molecule that bridges the aminergic block to the sodium-channel block:
    # SLC6A2/SLC6A4 and DRD1/2/3 and HRH2 on one side, SCN2A/5A/9A and
    # CACNA1B on the other. Those two regions are currently unconnected.
    {"name": "amitriptyline", "chembl_id": "CHEMBL629"},
    # Curated mu-opioid agonist - the only route to OPRD1/OPRK1/OPRM1, which
    # arrived as cannabidiol off-targets and have had one opinion each since.
    # Also SIGMAR1, TMEM97, CYP2D6 and KCNH2: the hERG liability that made it
    # notorious is a target this database already holds.
    {"name": "loperamide", "chembl_id": "CHEMBL841"},
    # Curated NMDA (GRIN2A) antagonist and sigma-1 agonist, reaching
    # GRIN1/2A/2B, SIGMAR1 and SLC6A2/4 while adding no new targets at all -
    # the best coverage-to-sprawl ratio in the whole sweep. Tacrine was the
    # only opinion on the NMDA receptor until now.
    {"name": "dextromethorphan", "chembl_id": "CHEMBL52440"},
    # The second NMDA opinion, and the fifth approved Alzheimer's drug here:
    # donepezil, rivastigmine, tacrine and galantamine inhibit cholinesterase,
    # memantine does not. A cluster of five drugs for one indication that
    # splits cleanly in two by mechanism is the clearest test of whether the
    # picture reads correctly. Drags in two new targets.
    {"name": "memantine", "chembl_id": "CHEMBL807"},
    # Sodium-channel blocker: SCN2A/3A/5A/9A, which arrived as verapamil and
    # cannabidiol off-targets. Two new nodes.
    {"name": "lamotrigine", "chembl_id": "CHEMBL741"},
    # Reversal of a documented exclusion. Dipyridamole ranked second in the
    # second-cohort sweep and was left out because all 11 of its hits were a
    # subset of pentoxifylline's 13 PDE targets. That is no longer true: the
    # target set it would join has grown to include PDE6A-H, PDE7A, PDE8A,
    # PDE10A and PDE11A - sildenafil's own off-targets, one opinion each -
    # and its curated equilibrative nucleoside transporter (SLC29A1)
    # mechanism reaches the one target that connects the PDE cluster back to
    # adenosine by a route no xanthine takes: it raises adenosine by blocking
    # reuptake, where caffeine blocks the receptor. One new node.
    #
    # Stated plainly: its PDE corroboration comes from a single curated
    # mechanism record filed against the phosphodiesterase *family*, which
    # fans out to 22 accessions. It is one curator's assertion, not 22
    # findings - the same shape as pentoxifylline's, and the same caveat.
    {"name": "dipyridamole", "chembl_id": "CHEMBL932"},
    # Curated PDE5A inhibitor, the direct comparison to sildenafil at the
    # target both are prescribed for, with its own measurements at PDE6A,
    # PDE10A and PDE11A. Adds no new targets.
    {"name": "vardenafil", "chembl_id": "CHEMBL1520"},
    # Curated CB1 *agonist*, against cannabidiol's curated negative allosteric
    # modulator at that same receptor - opposite actions on one target, which
    # is precisely the distinction shared-target overlap cannot make and the
    # edge colouring can. Also GPR55, TRPM8 and LDHA, all cannabidiol
    # singletons. Two new nodes.
    {"name": "dronabinol", "chembl_id": "CHEMBL465"},
    # Curated MAO-A *and* MAO-B inhibitor. Selegiline is MAO-B-selective and
    # was the only opinion on either, leaving MAOA at one edge; this is the
    # non-selective contrast, the same pairing rivastigmine makes against
    # donepezil at the cholinesterases. Also CYP2C9/2C19/2D6.
    {"name": "phenelzine", "chembl_id": "CHEMBL1089"},
    # CYP2D6, SCN5A and KCNH2 - the cardiac-liability trio - with three new
    # nodes. The classic hERG blocker, at a target verapamil, tacrine,
    # sildenafil and loperamide all reach.
    {"name": "quinidine", "chembl_id": "CHEMBL1294"},
    # 90 qualifying rows at ACHE and 55 at BCHE, and nothing else in this
    # database at all: no new nodes, no off-targets, pure corroboration. It
    # completes the four approved cholinesterase inhibitors - donepezil,
    # rivastigmine, tacrine, galantamine - which is the densest evidenced
    # cluster the graph has. ChEMBL 37 records no curated mechanism for it,
    # so these edges enter as measured binding.
    {"name": "galantamine", "chembl_id": "CHEMBL659"},
    # The one molecule found that measures the calcium-channel subunits
    # *individually*: 20 rows at CACNA1G, 4 at CACNA1H, 3 at CACNA1I. Those
    # three are currently members of tacrine's 26-way fan-out from a single
    # "Inhibition of VGCC (unknown origin)" assay, and this is the only
    # candidate in the sweep that gives any of them a subunit-specific
    # measurement of their own rather than a second fan-out. One new node.
    {"name": "mibefradil", "chembl_id": "CHEMBL45816"},
]

# A target only gets auto-discovered (from raw ChEMBL/BindingDB/PDSP binding
# data, as opposed to a ChEMBL curated "mechanism" record, which always gets
# in regardless of affinity) if some measurement clears this bar. This is a
# noise filter, not a validated "real vs. not real" threshold - weak
# affinity doesn't mean an interaction isn't real (caffeine's own curated
# ADORA3 mechanism is Ki=100 uM), it just means auto-discovery can't tell a
# weak-but-real hit apart from the long tail of HTS screening-panel
# artifacts (100s of uM to mM hits against unrelated proteins) without a
# citation to lean on. Set generously for that reason; `n_measurements` on
# the resulting interaction is the better trust signal - a single-source
# hit is a lead to corroborate, not a settled finding, regardless of where
# it falls relative to this cutoff.
#
# Raised from 30,000 to 300,000 nM after theobromine (a third methylxanthine,
# seeded specifically to sit alongside caffeine/theophylline) came back with
# zero edges: ChEMBL has no curated *mechanism* record for it (it was never
# developed as a drug, so it never got a curator's write-up), but it does
# have real measured IC50s at all four ADORA subtypes + PDE4 (100,000-
# 250,000 nM) from a real, focused literature review (Faudone/Arifi/Merk,
# "The Medicinal Chemistry of Caffeine", J Med Chem 2021, PMID 34019396) -
# exactly the "weak but real, just uncurated" case this comment already
# called out, not an HTS artifact. 300,000 sits just above that paper's
# weakest value and matches an order of magnitude already trusted elsewhere
# in this DB (theophylline's own curated PDE3A/3B IC50s are 300,000 nM).
# Three of the five theobromine values carry ChEMBL's own
# data_validity_comment="Outside typical range" flag - not excluded for
# that (the source paper itself is legitimate), but surfaced via
# measurements.data_validity_note rather than silently trusted.
MAX_SUPPLEMENTARY_AFFINITY_NM = 300_000

# BindingDB's target field is free-text, not a gene symbol. Map the ones we
# already carry as curated ADORA targets so BindingDB corroborates the same
# target row instead of creating a duplicate. Anything not in this map is
# resolved dynamically via UniProt protein-name search (see
# resolve_uniprot_accession).
BINDINGDB_TARGET_NAME_ALIASES = {
    "adenosine receptor a1": "ADORA1",
    "adenosine receptor a2a": "ADORA2A",
    "adenosine receptor a2b": "ADORA2B",
    "adenosine receptor a3": "ADORA3",
}

# Manually-caught ChEMBL assay-target mislinkings, excluded rather than
# trusted blindly. Keyed by (assay_chembl_id, target_chembl_id).
CHEMBL_ASSAY_LINK_EXCLUSIONS = {
    ("CHEMBL1074487", "CHEMBL6114"): (
        "assay text says 'Inhibition of PLAP' (placental alkaline "
        "phosphatase, gene ALPP) but is linked to CHEMBL6114, which ChEMBL "
        "itself names 'Phospholipase A-2-activating protein' (gene PLAA) - "
        "an unrelated protein. Verified 2026-08-11 against its two sibling "
        "assays in the same series (CHEMBL1074488 'Inhibition of TNAP' -> "
        "ALPL, CHEMBL1074489 'Inhibition of IAP' -> ALPI), both correctly "
        "linked, so this looks like an isolated ChEMBL curation error for "
        "this one assay rather than a systematic problem."
    ),
    ("CHEMBL5133661", "CHEMBL2484"): (
        "assay text reads 'Inhibition of human AChE by Ellman's method' - "
        "the classic acetylcholinesterase (ACHE, P22303) assay - but is "
        "linked to CHEMBL2484, which ChEMBL itself resolves to "
        "'Acetylcholine receptor subunit epsilon' (CHRNE, Q04844), an "
        "unrelated protein. This is the same underlying upstream record "
        "already excluded on the BindingDB side via "
        "BINDINGDB_TARGET_LINK_EXCLUSIONS (monomerid 8960), which confirms "
        "the error originates above BindingDB rather than in its "
        "republication. Verified 2026-08-25 directly against ChEMBL: all "
        "four of donepezil's activities against CHEMBL2484 are AChE assays "
        "by description; the other three report unitless % Inhibition and "
        "are dropped by the nM units filter regardless, so this "
        "IC50=32.36nM record is the only one that could reach the "
        "database. Caught only because paginating the ChEMBL fetch "
        "surfaced it - it sat past the old limit=100 cutoff."
    ),
}

# Same idea as CHEMBL_ASSAY_LINK_EXCLUSIONS but for BindingDB, whose own
# compound pages sometimes file a hit under the wrong target header -
# distinct from the UniProt resolve_uniprot_accession bug (this is a
# mistake in BindingDB's own data, not in how we look up a gene from a
# name it gave us). Keyed by (monomerid, target_name) exactly as BindingDB
# reports them via getTargetByCompound.
BINDINGDB_TARGET_LINK_EXCLUSIONS = {
    ("8960", "Acetylcholine receptor subunit epsilon"): (
        "target header says 'Acetylcholine receptor subunit epsilon' "
        "(CHRNE) but the assay's own description reads 'Inhibition of "
        "human AChE by Ellman's method' - Ellman's method is the classic "
        "acetylcholinesterase (ACHE, an unrelated enzyme) assay. "
        "Verified 2026-08-18 directly against BindingDB's own page for "
        "this monomerid/target pair."
    ),
}

# Substrings that mark a UniProt tissue-specificity comment as describing
# expression in the brain/CNS. Deliberately narrow: "cortex" alone is not here
# because it matches "adrenal cortex", and "nerve" is not here because
# peripheral nerve isn't what this field means. A hit sets expressed_in_brain=1
# and stores UniProt's own sentence verbatim as the note, so a reader can judge
# the nuance ("to a much lesser extent, in brain") for themselves rather than
# trusting a bare flag.
BRAIN_TISSUE_KEYWORDS = (
    "brain", "cerebral", "cerebellum", "cerebellar", "hippocamp", "striatum",
    "striatal", "central nervous system", "neuron", "astrocyt", "microglia",
    "hypothalam", "cerebrospinal",
)

# Curated brain-expression notes, hand-written from established pharmacology
# literature. These take precedence over the UniProt-derived flag below: they
# say something the tissue-specificity comment doesn't (which subtype carries
# which effect), and UniProt has no tissue comment at all for the ADORA family.
BRAIN_EXPRESSION_NOTES = {
    "ADORA1": (1, "Widely and highly expressed in CNS (cortex, hippocampus, "
                   "cerebellum); mediates caffeine's main wake-promoting effect."),
    "ADORA2A": (1, "Densely expressed in striatum (striatopallidal neurons); "
                    "primary target for caffeine's psychostimulant effects."),
    "ADORA2B": (1, "Present in brain at lower levels than A1/A2A; low affinity "
                    "for caffeine, more prominent peripherally (e.g. lung, gut)."),
    "ADORA3": (1, "Present in brain at lower levels; low affinity for caffeine, "
                   "more prominent in lung/immune tissue."),
}


# Minimum gap between outbound requests. None of these APIs publish a hard
# rate limit, but all of them are free public infrastructure and paginating
# ChEMBL multiplied this pipeline's request count several-fold - throttling
# is the cheap way to stay a good citizen rather than finding the limit
# empirically.
MIN_REQUEST_INTERVAL = 0.15
_last_request_at = 0.0


def _throttle():
    global _last_request_at
    wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


# A full run makes thousands of requests across five APIs, so a single slow
# response shouldn't cost the whole load. Timeouts are generous and backoff is
# exponential: ChEMBL in particular has been observed both timing out
# transiently and going down entirely for hours (see docs/DATA-QUALITY-LOG.md),
# and the difference between those is how long you wait before giving up.
REQUEST_TIMEOUT = 60
REQUEST_RETRIES = 6
# Cap the exponential backoff: 3, 6, 12, 24, 30, 30 seconds. ChEMBL has been
# observed serving 500s and timeouts on roughly two-thirds of requests during a
# degraded spell (2026-08-25) while still recovering on its own within the
# hour, so patience here is the difference between a run that finishes and a
# run that aborts halfway and leaves the database under-reporting.
MAX_RETRY_DELAY = 30

# Wikidata asks for a descriptive User-Agent on its SPARQL endpoint and
# throttles requests that arrive without one.
WIKIDATA_USER_AGENT = (
    "SubNetwork/0.1 (educational drug-target interaction map; "
    "https://github.com/; contact via repository)"
)


def get_json(url, retries=REQUEST_RETRIES, timeout=REQUEST_TIMEOUT, **kwargs):
    last_err = None
    for attempt in range(retries):
        try:
            _throttle()
            resp = requests.get(url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException,) as err:
            last_err = err
            # A 4xx is an answer, not a hiccup: PubChem returns 404 for a
            # compound with no CAS numbers, and callers handle that. Retrying
            # it four times with backoff just burns ~20s per lookup. 429 is
            # the exception - that one genuinely wants waiting out.
            status = getattr(getattr(err, "response", None), "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                raise
            if attempt < retries - 1:
                delay = min(3 * (2 ** attempt), MAX_RETRY_DELAY)
                print(f"    request failed ({type(err).__name__}), retrying in {delay}s...")
                time.sleep(delay)
    raise last_err


# ChEMBL caps a single response at 1000 records and reports the true size in
# page_meta.total_count, with page_meta.next holding the path to the next
# page. Anything that doesn't follow that link is reading an arbitrary prefix
# of the result set, NOT the strongest or most relevant records - ChEMBL's
# default ordering is by internal activity id, unrelated to affinity. This
# was a real, measured bug here: with the previous hardcoded limit=100,
# caffeine's Ki fetch pooled 18 of its 61 usable measurements and donepezil's
# IC50 fetch pooled 96 of 280, silently deflating n_measurements (this
# project's core corroborated-vs-lead trust signal - caffeine/ADORA3 showed
# as an uncorroborated n=1 lead when ChEMBL alone had 8 measurements) and
# dropping 6 of donepezil's 15 ChEMBL IC50 targets out of the database
# entirely.
# 250, not ChEMBL's 1000 maximum: a full-size page takes ~4s to serve against
# ~1s for 250 or 500, and the first attempt at this ran into three consecutive
# 30s read timeouts on theophylline's Ki fetch and aborted the run. More,
# smaller requests are both faster in aggregate here and far less exposed to a
# slow response - the throttle below already keeps the request rate polite.
CHEMBL_PAGE_SIZE = 250
# Guard against an unbounded loop if ChEMBL ever returns a malformed
# page_meta; 250 x 40 is 10k records, far more than any molecule here has.
CHEMBL_MAX_PAGES = 40


def get_json_paginated(url, params, collection_key):
    """Fetch every page of a ChEMBL list endpoint, following page_meta.next
    until exhausted, and return the concatenated collection."""
    params = {**params, "limit": CHEMBL_PAGE_SIZE, "offset": 0}
    out = []
    for _ in range(CHEMBL_MAX_PAGES):
        data = get_json(url, params=params)
        out.extend(data[collection_key])
        meta = data.get("page_meta") or {}
        total = meta.get("total_count")
        if not meta.get("next") or (total is not None and len(out) >= total):
            break
        params = {**params, "offset": len(out)}
    else:
        print(f"    WARNING: hit CHEMBL_MAX_PAGES on {url} - results may be truncated")
    return out


# ChEMBL backend. None means "go over the network" (the original behaviour);
# a LocalChEMBL means "read the downloaded bulk release". Set once in main()
# and never per-molecule: a run that silently switched backends halfway would
# produce a database whose provenance couldn't be stated.
_local_chembl = None


def set_chembl_backend(local):
    """Install a chembl_local.LocalChEMBL (or None for the REST API)."""
    global _local_chembl
    _local_chembl = local


def chembl_backend_label():
    """How this run sourced its ChEMBL data, for the run log and for the
    sources.base_url recorded alongside every ChEMBL-backed edge."""
    if _local_chembl is None:
        return "ChEMBL REST API"
    return f"local {_local_chembl.release} release ({_local_chembl.path})"


def fetch_pubchem_properties(name):
    props = "MolecularFormula,MolecularWeight,IUPACName,CanonicalSMILES,InChIKey"
    url = f"{PUBCHEM_BASE}/compound/name/{name}/property/{props}/JSON"
    data = get_json(url)
    return data["PropertyTable"]["Properties"][0]


def fetch_chembl_mechanisms(chembl_id):
    """Curated top-line mechanism-of-action records for a molecule."""
    if _local_chembl is not None:
        return _local_chembl.mechanisms(chembl_id)
    return get_json_paginated(f"{CHEMBL_BASE}/mechanism", {
        "molecule_chembl_id": chembl_id, "format": "json",
    }, "mechanisms")


def fetch_chembl_target(target_chembl_id):
    if _local_chembl is not None:
        return _local_chembl.target(target_chembl_id)
    url = f"{CHEMBL_BASE}/target/{target_chembl_id}"
    return get_json(url, params={"format": "json"})


# Cached across the whole run (not per-molecule) since the same paper often
# backs measurements for more than one seed molecule (e.g. the caffeine
# medicinal-chemistry review also covers theobromine/theophylline).
_document_cache = {}

# Same reasoning for target lookups, which are far more numerous: the seed set
# is deliberately built around shared targets (four molecules hit the ADORA
# family, three hit PDE4), so a per-molecule cache re-fetched the same target
# records once per molecule.
_target_cache = {}


def cached_chembl_target(target_chembl_id):
    if target_chembl_id not in _target_cache:
        _target_cache[target_chembl_id] = fetch_chembl_target(target_chembl_id)
    return _target_cache[target_chembl_id]


def fetch_chembl_document(document_chembl_id):
    if document_chembl_id not in _document_cache:
        if _local_chembl is not None:
            _document_cache[document_chembl_id] = _local_chembl.document(
                document_chembl_id
            )
        else:
            try:
                _document_cache[document_chembl_id] = get_json(
                    f"{CHEMBL_BASE}/document/{document_chembl_id}.json"
                )
            except requests.exceptions.RequestException:
                _document_cache[document_chembl_id] = {}
    return _document_cache[document_chembl_id]


def chembl_activity_citation(act):
    """(citation_url, citation_text) for a raw ChEMBL activity record,
    preferring a direct PubMed/DOI link on the underlying document over
    ChEMBL's own document page. document_journal/document_year are already
    present on the activity record itself (no extra call needed for those);
    only DOI/PubMed ID require fetching the /document endpoint."""
    doc_id = act.get("document_chembl_id")
    if not doc_id:
        return None, None
    doc = fetch_chembl_document(doc_id)
    pubmed_id = doc.get("pubmed_id")
    doi = doc.get("doi")
    if pubmed_id:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/"
    elif doi:
        url = f"https://doi.org/{doi}"
    else:
        url = f"https://www.ebi.ac.uk/chembl/document_report_card/{doc_id}/"
    journal = act.get("document_journal") or doc.get("journal")
    year = act.get("document_year") or doc.get("year")
    text = doc.get("title") or " ".join(
        part for part in (journal, f"({year})" if year else None) if part
    ) or doc_id
    return url, text


# Prefer a PubMed reference over an FDA label over whatever else ChEMBL's
# curators attached, for citing a curated mechanism-of-action record.
_MECHANISM_REF_PRIORITY = {"PubMed": 0, "FDA": 1}


def chembl_mechanism_citation(mech):
    """(citation_url, citation_text) for a curated ChEMBL mechanism record,
    from its own mechanism_refs (already-complete URLs - FDA label, PubMed
    via Europe PMC, sometimes Wikipedia - no extra API call needed)."""
    refs = mech.get("mechanism_refs") or []
    if not refs:
        return None, None
    ref = min(refs, key=lambda r: _MECHANISM_REF_PRIORITY.get(r.get("ref_type"), 99))
    ref_type = ref.get("ref_type") or "Reference"
    text = f"{ref_type} {ref['ref_id']}" if ref.get("ref_id") else ref_type
    return ref.get("ref_url"), text


def fetch_chembl_binding_activities(chembl_id, standard_type):
    """Direct target-engagement assay results (Ki/Kd/IC50, in nM) against
    human protein targets. Restricted to assay_type=B ("binding" in ChEMBL's
    classification - includes biochemical/enzyme-inhibition assays against
    purified protein, not just receptor radioligand-displacement assays) so
    every value pulled in, including IC50 (which is otherwise assay-condition-
    dependent and not directly comparable across studies the way Ki is), at
    least represents a direct target-engagement measurement rather than a
    downstream functional/phenotypic readout (assay_type=F, e.g. cAMP
    accumulation, calcium flux) where potency can shift for reasons unrelated
    to affinity at this target (receptor reserve, signal amplification,
    etc). Verified against theophylline's own data: 96/100 of its existing
    Ki activities are already assay_type=B, and its two real PDE3 IC50
    records are both direct enzyme-inhibition assays on purified/tissue PDE3
    (bao_label "protein format"), so this filter doesn't meaningfully cut
    real data - it excludes the assay types that would produce numbers not
    meaningfully comparable to Ki in the first place."""
    if _local_chembl is not None:
        return _local_chembl.binding_activities(chembl_id, standard_type)
    return get_json_paginated(f"{CHEMBL_BASE}/activity", {
        "molecule_chembl_id": chembl_id,
        "target_organism": "Homo sapiens",
        "standard_type": standard_type,
        "assay_type": "B",
        "format": "json",
    }, "activities")


# Functional-assay standard_types worth tracking: well-defined potency
# quantities from a specific pharmacological readout. Deliberately excludes
# ambiguous/inconsistent ones like ChEMBL's generic "Potency" (used for
# qHTS/Tox21-style promiscuity panels) and "Activity"/"FC" (fold-change,
# not a concentration).
FUNCTIONAL_STANDARD_TYPES = ("Ki", "Kd", "IC50", "EC50", "AC50", "Kb")


def fetch_chembl_functional_activities(chembl_id):
    """Cell-based (or tissue/membrane-based) functional-assay results against
    human protein targets - corroborating evidence that a target engagement
    has a downstream functional consequence, tracked separately from
    binding_value since functional potency isn't the same physical quantity
    as binding affinity (see interactions.functional_value in schema.sql).
    Excludes assay_type=B (that's fetch_chembl_binding_activities' job) and,
    within assay_type=F, excludes bao_label="organism-based format": whole-
    animal assays report a phenotypic outcome (e.g. urine output in a dosed
    rat) without attributing it to a specific molecular target - ChEMBL's
    own target_pref_name for those is literally the species name, not a
    gene - so they can't be mapped onto a specific target_id at all,
    regardless of how well-verified the compound/target pair otherwise is.
    """
    if _local_chembl is not None:
        activities = _local_chembl.functional_activities(
            chembl_id, FUNCTIONAL_STANDARD_TYPES
        )
        return [a for a in activities if a.get("bao_label") != "organism-based format"]
    activities = get_json_paginated(f"{CHEMBL_BASE}/activity", {
        "molecule_chembl_id": chembl_id,
        "target_organism": "Homo sapiens",
        "assay_type": "F",
        "standard_type__in": ",".join(FUNCTIONAL_STANDARD_TYPES),
        "format": "json",
    }, "activities")
    return [a for a in activities if a.get("bao_label") != "organism-based format"]


def fetch_dgidb_interactions(drug_name):
    query = """
    query($names: [String!]) {
      drugs(names: $names) {
        nodes {
          name
          interactions {
            gene { name }
            interactionTypes { type }
            interactionClaims {
              source { sourceDbName }
              publications { pmid citation }
            }
          }
        }
      }
    }
    """
    _throttle()
    resp = requests.post(
        DGIDB_BASE,
        json={"query": query, "variables": {"names": [drug_name.upper()]}},
        timeout=20,
    )
    resp.raise_for_status()
    nodes = resp.json()["data"]["drugs"]["nodes"]
    for node in nodes:
        if node["name"].upper() == drug_name.upper():
            return node["interactions"]
    return []


def dgidb_citation(interaction):
    """(citation_url, citation_text) for a DGIdb gene interaction, from the
    first attached publication across its claims. DGIdb aggregates several
    curated databases (PharmGKB, TTD, etc.) per gene-drug pair, and not
    every claim carries a publication - falls back to naming the curating
    database(s) when none do."""
    for claim in interaction.get("interactionClaims", []):
        for pub in claim.get("publications", []):
            if pub.get("pmid"):
                return (
                    f"https://pubmed.ncbi.nlm.nih.gov/{pub['pmid']}/",
                    pub.get("citation") or f"PubMed {pub['pmid']}",
                )
    dbs = sorted({
        c["source"]["sourceDbName"] for c in interaction.get("interactionClaims", [])
        if c.get("source")
    })
    return None, (", ".join(dbs) if dbs else None)


def fetch_uniprot_entry(accession):
    url = f"{UNIPROT_BASE}/uniprotkb/{accession}.json"
    return get_json(url)


def uniprot_function_summary(entry):
    for c in entry.get("comments", []):
        if c.get("commentType") == "FUNCTION":
            return c["texts"][0]["value"]
    return None


def uniprot_tissue_specificity(entry):
    for c in entry.get("comments", []):
        if c.get("commentType") == "TISSUE SPECIFICITY":
            texts = c.get("texts") or []
            if texts:
                return texts[0]["value"]
    return None


def brain_expression(gene_symbol, entry):
    """(expressed_in_brain, expression_note) for a target.

    Hand-curated notes win where they exist. Otherwise this reads UniProt's
    own TISSUE SPECIFICITY comment - the closest thing any wired-up source has
    to structured tissue data - and flags a brain/CNS mention, quoting the
    sentence verbatim with its accession so the claim is traceable like every
    other value in this database.

    Only ever returns 1 or None, never 0: UniProt's tissue comments are
    incomplete (ADORA1 has none at all, despite being one of the best-
    characterised CNS receptors in pharmacology), so silence means "unknown",
    not "absent". A comment that mentions the brain only to deny expression
    there would be misread by this keyword scan - the verbatim note is stored
    precisely so that stays visible rather than hidden behind a bare flag.
    """
    curated = BRAIN_EXPRESSION_NOTES.get(gene_symbol)
    if curated:
        return curated
    if entry is None:
        return (None, None)
    tissue = uniprot_tissue_specificity(entry)
    if not tissue:
        return (None, None)
    if not any(kw in tissue.lower() for kw in BRAIN_TISSUE_KEYWORDS):
        return (None, None)
    accession = entry.get("primaryAccession")
    return (1, f"UniProt {accession} tissue specificity: {tissue}")


def uniprot_gene_symbol(entry):
    genes = entry.get("genes") or []
    if not genes:
        return None
    return genes[0].get("geneName", {}).get("value")


def resolve_uniprot_accession(gene_symbol=None, protein_name=None):
    """Find the reviewed human UniProt accession for a gene symbol or a
    free-text protein name (used to resolve targets discovered via
    BindingDB/PDSP that don't come with a gene symbol attached).

    For protein_name, UniProt's `protein_name:"..."` query is a
    relevance-ranked full-text search, not an exact-match lookup - blindly
    taking result[0] silently returned the wrong gene entirely in real
    cases found in this DB: searching "Tumor necrosis factor" ranked LTBR
    ("Tumor necrosis factor receptor superfamily member 3") above the
    literal exact match, gene TNF itself; searching "Amyloid-beta
    precursor protein" never returned APP at all in the top 3, instead
    surfacing three unrelated "amyloid ... binding protein" genes
    (APPBP2/APBB1/APBB2). Fetches several candidates and only accepts one
    whose own recommended full name matches the query exactly
    (case/whitespace-insensitive) - refuses to guess (returns None) rather
    than accepting a merely-related top "relevance" hit, since a wrong
    gene is worse than a missing one. This does mean a genuinely generic/
    ambiguous source name (e.g. BindingDB's own "cGMP-specific 3',5'-
    cyclic phosphodiesterase", with no isoform specified) now correctly
    resolves to nothing instead of guessing a specific isoform - confirmed
    against this DB's own data that the specific isoform it used to guess
    (PDE9A) wasn't even the assay's real target (PDE5A1).

    For gene_symbol, `gene_exact:` matches UniProt's gene *synonyms* as well
    as its primary gene name, and the results are relevance-ranked rather
    than exact-first - so this branch needs the same guard for the same
    reason. `gene_exact:ADRA1A` returns two reviewed human entries and ranks
    P25100 *first*, whose primary gene is ADRA1D: the receptor originally
    cloned as "alpha-1a" was reclassified as alpha-1D, and the superseded
    name survives as a synonym on that entry. Taking result[0] therefore
    attributed every PDSP alpha-1A measurement to the alpha-1D receptor.
    Only an entry whose own *primary* gene name is the one asked for is
    accepted, and an ambiguous answer (two primaries matching, which should
    not happen for a reviewed human gene) is refused like any other guess."""
    if gene_symbol:
        query = f"gene_exact:{gene_symbol} AND organism_id:9606 AND reviewed:true"
        data = get_json(
            f"{UNIPROT_BASE}/uniprotkb/search",
            params={"query": query, "format": "json", "size": 10,
                    "fields": "accession,gene_primary"},
        )
        wanted = gene_symbol.strip().lower()
        matches = [
            r["primaryAccession"]
            for r in data.get("results") or []
            if any((g.get("geneName") or {}).get("value", "").strip().lower() == wanted
                   for g in r.get("genes") or [])
        ]
        return matches[0] if len(matches) == 1 else None

    if protein_name:
        query = f'protein_name:"{protein_name}" AND organism_id:9606 AND reviewed:true'
        data = get_json(
            f"{UNIPROT_BASE}/uniprotkb/search",
            params={"query": query, "format": "json", "size": 10,
                    "fields": "accession,protein_name"},
        )
        target_norm = " ".join(protein_name.split()).lower()
        for r in data.get("results") or []:
            name = r["proteinDescription"]["recommendedName"]["fullName"]["value"]
            if " ".join(name.split()).lower() == target_norm:
                return r["primaryAccession"]
        return None

    return None


def fetch_bindingdb_activities(smiles):
    """Human binding/functional measurements for the compound matching
    `smiles` exactly. BindingDB's compound search matches on the literal
    input structure encoding, not a canonicalized form - so it's queried
    with PubChem's ConnectivitySMILES for reproducibility, but may not
    surface every synonym/duplicate ligand record BindingDB holds for the
    same real-world compound. That's acceptable here since BindingDB is a
    supplementary/cross-validation source (like DGIdb), not the primary Ki
    source (ChEMBL is)."""
    data = get_json(
        f"{BINDINGDB_BASE}/getTargetByCompound",
        params={"smiles": smiles, "cutoff": "0", "response": "application/json"},
    )
    affinities = (data.get("getLindsByUniprotResponse") or {}).get("bdb.affinities") or []
    out = []
    for a in affinities:
        if a.get("bdb.species") != "Human":
            continue
        affinity_type = a.get("bdb.affinity_type")
        if affinity_type not in ("Ki", "Kd", "IC50"):
            continue
        raw = (a.get("bdb.affinity") or "").strip()
        if raw.startswith(">"):
            continue  # no binding detected up to this concentration - not a hit
        out.append({
            "target_name": a.get("bdb.target"),
            "affinity_type": affinity_type,
            "value": float(raw.lstrip("<")),
            "external_ref": str(a.get("bdb.monomerid")),
        })
    return out


def bindingdb_citation(monomerid):
    """(citation_url, citation_text) for a BindingDB ligand record. The
    getTargetByCompound response itself carries no reference/DOI/PMID field
    (checked directly - it's just monomerid/smiles/target/species/affinity),
    so this can't cite the specific paper behind a measurement. It can
    still link to BindingDB's own compound page for that monomerid, which
    is a real, stable, unauthenticated page (confirmed against 10849 ->
    caffeine, matching this project's own data) - distinct from the
    getTargetByCompound REST endpoint that's been unreliable elsewhere in
    this project; this is a static page, not that API."""
    if not monomerid or monomerid == "None":
        return None, None
    url = f"https://www.bindingdb.org/rwd/bind/chemsearch/marvin/MolStructure.jsp?monomerid={monomerid}"
    return url, f"BindingDB BDBM{monomerid}"


def fetch_pubchem_cas_numbers(name):
    """CAS registry numbers for a compound, used to match it against PDSP's
    bulk CSV (which has no stable compound ID we already hold)."""
    try:
        data = get_json(f"{PUBCHEM_BASE}/compound/name/{name}/xrefs/RN/JSON")
    except requests.exceptions.HTTPError:
        return set()
    info = data["InformationList"]["Information"][0]
    return set(info.get("RN", []))


# The PDSP bulk CSV is the only way to read that database (no query API), so
# it gets cached locally - but an existence check alone means the cache never
# expires and the pipeline can quietly keep reading a year-old snapshot while
# reporting today's accessed_date. Re-fetched once it goes stale; --refresh-pdsp
# forces it.
PDSP_CACHE_MAX_AGE_DAYS = 30


def pdsp_cache_age_days():
    if not PDSP_CACHE_PATH.exists():
        return None
    age = time.time() - PDSP_CACHE_PATH.stat().st_mtime
    return age / 86400


def download_pdsp_database(force=False):
    age = pdsp_cache_age_days()
    if force or age is None or age > PDSP_CACHE_MAX_AGE_DAYS:
        why = ("forced" if force else "not cached" if age is None
               else f"cache is {age:.0f} days old")
        print(f"  downloading PDSP Ki database (~20MB, {why})...")
        resp = requests.get(PDSP_CSV_URL, timeout=120)
        resp.raise_for_status()
        PDSP_CACHE_PATH.write_bytes(resp.content)
    return PDSP_CACHE_PATH


def fetch_pdsp_activities(cas_numbers):
    """Human Ki measurements from the PDSP bulk CSV, matched by CAS number
    (PDSP has no query API - see PDSP_CSV_URL comment above)."""
    if not cas_numbers:
        return []
    path = download_pdsp_database()
    out = []
    with open(path, newline="", encoding="latin-1") as f:
        for row in csv.DictReader(f):
            row = {(k or "").strip(): (v.strip() if v else v) for k, v in row.items()}
            if row.get("CAS") not in cas_numbers:
                continue
            if (row.get("species") or "").upper() != "HUMAN":
                continue
            gene_symbol = row.get("Unigene")
            if not gene_symbol:
                continue
            if (row.get("ki Note") or "").strip() == ">":
                continue  # no binding detected up to this concentration - not a hit
            val = row.get("ki Val")
            if not val:
                continue
            try:
                value = float(val)
            except ValueError:
                continue
            out.append({
                "gene_symbol": gene_symbol,
                "affinity_type": "Ki",
                "value": value,
                "external_ref": row.get("Number"),
                # Free-text citation shorthand (e.g. "HOYER, 1988") - PDSP's
                # bulk CSV has no DOI/PMID/URL field to link to directly.
                "reference": row.get("Reference") or None,
            })
    return out


def get_or_create_source(conn, name, base_url, release=None):
    """Source row, refreshed on every run.

    accessed_date and source_release are updated rather than left at their
    first-insert values: a rerun really did re-read the source, and a build
    that switched from the live API to a local dump (or to a newer release)
    would otherwise keep claiming the older provenance forever. base_url is
    left alone -- it is the canonical public URL a reader should follow, and
    stays that even when the data was read from a local copy."""
    cur = conn.execute("SELECT id FROM sources WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        conn.execute(
            "UPDATE sources SET accessed_date = ?, source_release = ? WHERE id = ?",
            (TODAY, release, row[0]),
        )
        return row[0]
    cur = conn.execute(
        "INSERT INTO sources (name, base_url, accessed_date, source_release)"
        " VALUES (?, ?, ?, ?)",
        (name, base_url, TODAY, release),
    )
    return cur.lastrowid


def upsert_molecule(conn, name, chembl_id):
    print(f"  fetching PubChem properties for {name}...")
    props = fetch_pubchem_properties(name)
    conn.execute(
        """
        INSERT INTO molecules (name, chembl_id, pubchem_cid, iupac_name,
                                molecular_formula, molecular_weight, smiles, inchikey)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chembl_id) DO UPDATE SET
            pubchem_cid=excluded.pubchem_cid, iupac_name=excluded.iupac_name,
            molecular_formula=excluded.molecular_formula,
            molecular_weight=excluded.molecular_weight,
            smiles=excluded.smiles, inchikey=excluded.inchikey
        """,
        (
            name.capitalize(), chembl_id, props["CID"], props.get("IUPACName"),
            props.get("MolecularFormula"), float(props.get("MolecularWeight", 0)) or None,
            props.get("ConnectivitySMILES") or props.get("CanonicalSMILES"),
            props.get("InChIKey"),
        ),
    )
    return conn.execute(
        "SELECT id FROM molecules WHERE chembl_id = ?", (chembl_id,)
    ).fetchone()[0]


def upsert_target(conn, gene_symbol, protein_name, uniprot_accession,
                   chembl_target_id, function_summary, uniprot_entry=None):
    # targets.uniprot_accession is UNIQUE, so two gene symbols claiming one
    # accession is a hard error - but raised by sqlite it names neither gene,
    # and the first time it happened (ADRA1A resolving to ADRA1D's accession,
    # see resolve_uniprot_accession) the traceback said only "UNIQUE
    # constraint failed". Say which two genes disagree and about what: this
    # means a resolver returned the wrong protein, and the constraint is the
    # only thing standing between that and a silently mislabelled target.
    clash = conn.execute(
        "SELECT gene_symbol FROM targets WHERE uniprot_accession = ? AND gene_symbol != ?",
        (uniprot_accession, gene_symbol),
    ).fetchone()
    if clash:
        raise ValueError(
            f"{gene_symbol} resolved to UniProt {uniprot_accession}, which is "
            f"already held by {clash[0]}. One of the two is misresolved - a "
            f"gene symbol must not be attached to another protein's accession "
            f"(invariant 6)."
        )
    brain_flag, brain_note = brain_expression(gene_symbol, uniprot_entry)
    conn.execute(
        """
        INSERT INTO targets (gene_symbol, protein_name, uniprot_accession,
                              chembl_target_id, function_summary,
                              expressed_in_brain, expression_note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(gene_symbol) DO UPDATE SET
            protein_name=excluded.protein_name,
            uniprot_accession=excluded.uniprot_accession,
            chembl_target_id=excluded.chembl_target_id,
            function_summary=excluded.function_summary,
            expressed_in_brain=excluded.expressed_in_brain,
            expression_note=excluded.expression_note
        """,
        (gene_symbol, protein_name, uniprot_accession, chembl_target_id,
         function_summary, brain_flag, brain_note),
    )
    return conn.execute(
        "SELECT id FROM targets WHERE gene_symbol = ?", (gene_symbol,)
    ).fetchone()[0]


def upsert_interaction(conn, molecule_id, target_id, action_type,
                        mechanism_of_action, is_primary, binding_value,
                        binding_type, binding_units, n_measurements,
                        functional_value=None, functional_type=None,
                        functional_units=None, functional_n_measurements=None):
    conn.execute(
        """
        INSERT INTO interactions (molecule_id, target_id, action_type,
                                   mechanism_of_action, is_primary_mechanism,
                                   binding_value, binding_type, binding_units,
                                   n_measurements, functional_value,
                                   functional_type, functional_units,
                                   functional_n_measurements)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        -- Plain assignment, not COALESCE(excluded.x, x): a NULL coming out of
        -- this run means "the sources no longer support a value here", and
        -- coalescing would pin the old number in place forever. That mattered
        -- concretely - the standard_relation="=" fix removed ~16 bogus
        -- binding values, and on an existing database COALESCE would have
        -- kept every one of them. reset_molecule already clears the
        -- molecule's rows before a reload, so this branch only fires within a
        -- single run; it is written this way so it stays correct if that
        -- changes.
        ON CONFLICT(molecule_id, target_id, action_type) DO UPDATE SET
            mechanism_of_action=excluded.mechanism_of_action,
            is_primary_mechanism=excluded.is_primary_mechanism,
            binding_value=excluded.binding_value,
            binding_type=excluded.binding_type,
            binding_units=excluded.binding_units,
            n_measurements=excluded.n_measurements,
            functional_value=excluded.functional_value,
            functional_type=excluded.functional_type,
            functional_units=excluded.functional_units,
            functional_n_measurements=excluded.functional_n_measurements
        """,
        (molecule_id, target_id, action_type, mechanism_of_action, is_primary,
         binding_value, binding_type, binding_units, n_measurements,
         functional_value, functional_type, functional_units,
         functional_n_measurements),
    )
    return conn.execute(
        "SELECT id FROM interactions WHERE molecule_id = ? AND target_id = ? AND action_type = ?",
        (molecule_id, target_id, action_type),
    ).fetchone()[0]


def link_source(conn, interaction_id, source_id, external_ref,
                 citation_url=None, citation_text=None,
                 role="binding", citation_kind=None):
    # Upsert (not INSERT OR IGNORE) so rerunning the pipeline after adding a
    # new field like citation_url actually backfills it onto rows that
    # already existed from a previous run, instead of leaving them NULL.
    # `role` is part of the key: see interaction_sources.role in schema.sql
    # for why one source needs more than one row per edge.
    #
    # A citation here must be one that is NOT a measurement of this edge -
    # see interaction_sources.citation_url in schema.sql. Passing one without
    # a citation_kind is a caller bug: it would land in the viewer's
    # database list unlabelled, which is exactly the ambiguity this column
    # was added to remove.
    if (citation_url or citation_text) and citation_kind is None:
        raise ValueError(
            f"link_source: citation given for source {source_id} on "
            f"interaction {interaction_id} with no citation_kind. Every "
            "citation stored here must declare what kind of claim it "
            "supports ('mechanism' or 'annotation'); per-measurement "
            "citations belong in `measurements`, not here."
        )
    conn.execute(
        """
        INSERT INTO interaction_sources
            (interaction_id, source_id, external_ref, citation_url,
             citation_text, citation_kind, role)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(interaction_id, source_id, role) DO UPDATE SET
            external_ref=excluded.external_ref,
            citation_url=excluded.citation_url,
            citation_text=excluded.citation_text,
            citation_kind=excluded.citation_kind
        """,
        (interaction_id, source_id, external_ref, citation_url, citation_text,
         citation_kind, role),
    )


def record_measurements(conn, interaction_id, source_ids, role, affinity_type, rows):
    """Store every individual measurement behind one pooled value.

    Plain INSERTs with no conflict clause, which is safe only because
    reset_molecule clears this table for the molecule first: there is no
    natural key here to upsert on, since duplicate rows are legitimate data
    (see the schema comment on why this table is not deduplicated)."""
    for row in rows:
        conn.execute(
            """
            INSERT INTO measurements (
                interaction_id, source_id, role, affinity_type, value, units,
                counted, external_ref, citation_url, citation_text,
                data_validity_note, assay_description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (interaction_id, source_ids[row["source"]], role, affinity_type,
             row["value"], "nM", 1 if row["counted"] else 0, row["external_ref"],
             row["citation_url"], row["citation_text"], row["data_validity_note"],
             row["assay_description"]),
        )


def pooled_affinity(values):
    """Median of a set of affinity values, computed in log space.

    Binding affinities are log-normally distributed - the meaningful
    quantity is pKi/pKd (i.e. -log10 M), which is why the field quotes
    "Ki = 50 nM" and "Ki = 5 uM" as two log units apart rather than as a
    difference of 4950. For an odd-sized sample the median is an order
    statistic and both conventions pick the same number; for an even-sized
    sample the two middle values get combined, and doing that arithmetically
    biases the result high (arithmetic mean of 10 and 1000 is 505; the
    geometric mean, i.e. the midpoint in log space, is ~100). Falls back to
    the arithmetic mean if a value is non-positive, which shouldn't happen
    for a real affinity but shouldn't crash the load either.
    """
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    lo, hi = ordered[mid - 1], ordered[mid]
    if lo <= 0 or hi <= 0:
        return (lo + hi) / 2
    return math.sqrt(lo * hi)


def reduce_measurements(entries, preference=("Ki", "Kd", "IC50")):
    """entries: {"Ki": [(value, source, ref, citation_url, citation_text,
    validity_note, assay_description), ...], "Kd": [...], "IC50": [...]}.
    Prefer types earlier
    in `preference` - by default Ki, then Kd, then IC50, in that order of
    assay-independence - and never mix types together in one median.
    Returns (type, median_value, n_measurements,
    {source_name: (ref, citation_url, citation_text, validity_note)},
    [per-measurement dicts]) for the first type that has data, or None.

    The dict holds one entry per source (matching interaction_sources'
    one-row-per-source schema) and carries only the external ref - see the
    comment on its construction for why the citation and validity note are
    dropped rather than sampled. The fifth element is every row of the
    winning type, unreduced, each tagged with whether it was counted - that
    is what the `measurements` table stores, and it exists because the
    collapsed dict discarded ~230 of this database's ~290 citations, leaving
    n_measurements an assertion the viewer could not show the evidence for.

    BindingDB rows are excluded from the median/n_measurements count
    whenever at least one non-BindingDB row exists for that type. Checked
    directly against BindingDB's own compound pages (not exposed by the
    getTargetByCompound API we call) for every hit pooled into this DB:
    307/338 (91%) were tagged "Curated by ChEMBL" and 20/338 (6%) "Curated
    by PDSP Ki Database" - i.e. 97% of what BindingDB returns here is
    itself republished from a source this pipeline already queries
    directly, not independent corroboration (e.g. caffeine/SIRT3: ChEMBL
    and BindingDB both report Kd=690nM because BindingDB's own SIRT3 entry
    is literally sourced from the same ChEMBL record, same PubMed ID).
    Counting both inflated n_measurements, the project's core
    corroborated-vs-lead trust signal. BindingDB is still included in
    `sources` (for its citation link) and still counted when it's the
    *only* data for that type - real numbers, just not verifiably
    independent of a source already counted."""
    for measurement_type in preference:
        rows = entries.get(measurement_type)
        if not rows:
            continue
        non_bindingdb = [row for row in rows if row[1] != "BindingDB"]
        counted_rows = non_bindingdb or rows
        values = [row[0] for row in counted_rows]
        # Only the external ref survives per source. The citation and the
        # validity note are facts about one measurement, and this dict holds
        # one entry per source, so carrying them here meant sampling: dict
        # assignment is last-write-wins, making the "source's citation"
        # whichever row ChEMBL happened to deposit last. It then rendered
        # beside the measurement list as if it were a separate reference
        # corroborating the edge, when it was a copy of a row already in that
        # list. Both fields are per-measurement in `measurements` now; a
        # citation reaches interaction_sources only from a path that has a
        # non-measurement reference to record (the curated-mechanism override
        # below, and DGIdb's annotation).
        sources = {row[1]: (row[2], None, None, None) for row in rows}
        # Recomputed from the same condition rather than by identity-matching
        # against counted_rows: two measurements can be an identical tuple
        # (same value, same source, same assay reported twice), and `in`
        # would then mark both or neither.
        counted_all = not non_bindingdb
        detail = [
            {
                "value": row[0],
                "source": row[1],
                "external_ref": row[2],
                "citation_url": row[3],
                "citation_text": row[4],
                "data_validity_note": row[5],
                "assay_description": row[6],
                "counted": counted_all or row[1] != "BindingDB",
            }
            for row in rows
        ]
        return measurement_type, pooled_affinity(values), len(values), sources, detail
    return None


def reset_molecule(conn, molecule_id):
    """Drop a molecule's existing edges so a reload reflects what the sources
    report now, rather than the union of every run ever made.

    Two concrete failures this prevents. (1) A correction that *removes* data
    (e.g. the standard_relation="=" filter, which invalidated ~16 stored
    binding values) otherwise leaves the old value sitting in the row, since
    an upsert can only overwrite what the new run still produces. (2)
    action_type is part of interactions' UNIQUE key, so an edge that changes
    type between runs - a gene stored as BINDER that later gains a curated
    ChEMBL mechanism, becoming ANTAGONIST - would be INSERTed as a second row
    while the stale one lived on, showing up as duplicate parallel edges in
    the graph. Deleting first makes both cases impossible.

    Targets are left alone here (they are shared across molecules); main()
    prunes any left unreferenced at the end of the run.
    """
    for table in ("interaction_sources", "measurements"):
        conn.execute(
            f"""
            DELETE FROM {table}
             WHERE interaction_id IN (SELECT id FROM interactions WHERE molecule_id = ?)
            """,
            (molecule_id,),
        )
    conn.execute("DELETE FROM interactions WHERE molecule_id = ?", (molecule_id,))


def load_molecule(conn, name, chembl_id, source_ids):
    print(f"Loading {name} ({chembl_id})...")
    molecule_id = upsert_molecule(conn, name, chembl_id)
    reset_molecule(conn, molecule_id)
    molecule_smiles = conn.execute(
        "SELECT smiles FROM molecules WHERE id = ?", (molecule_id,)
    ).fetchone()[0]

    # 1. Curated top-line mechanism(s) from ChEMBL's "mechanism" endpoint.
    print("  fetching ChEMBL mechanism-of-action records...")
    mechanisms = fetch_chembl_mechanisms(chembl_id)
    mechanism_by_gene = {}
    for mech in mechanisms:
        target = cached_chembl_target(mech["target_chembl_id"])
        for component in target.get("target_components", []):
            gene_symbol = next(
                (s["component_synonym"] for s in component["target_component_synonyms"]
                 if s["syn_type"] == "GENE_SYMBOL"),
                None,
            )
            if not gene_symbol:
                continue
            mechanism_by_gene[gene_symbol] = mech
            print(f"    primary mechanism -> {gene_symbol}: {mech['action_type']} "
                  f"({mech['mechanism_of_action']})")

    # 2. Raw binding measurements, pooled across ChEMBL, BindingDB, and PDSP,
    #    keyed by gene symbol then affinity type. target_info tracks how to
    #    resolve/display each gene once we know it has a real measurement.
    measurements = {}
    target_info = {}
    # Cell-based functional-assay corroboration, pooled separately per gene -
    # see interactions.functional_value in schema.sql for why this never
    # gets merged into `measurements`.
    functional_measurements = {}

    def add_measurement(gene_symbol, affinity_type, value, source_name, external_ref,
                         citation_url=None, citation_text=None, data_validity_note=None,
                         assay_description=None):
        measurements.setdefault(gene_symbol, {}).setdefault(affinity_type, []).append(
            (value, source_name, external_ref, citation_url, citation_text,
             data_validity_note, assay_description)
        )

    def add_functional_measurement(gene_symbol, affinity_type, value, source_name, external_ref,
                                    citation_url=None, citation_text=None, data_validity_note=None,
                                    assay_description=None):
        functional_measurements.setdefault(gene_symbol, {}).setdefault(affinity_type, []).append(
            (value, source_name, external_ref, citation_url, citation_text,
             data_validity_note, assay_description)
        )

    print("  fetching ChEMBL binding activities (Ki/Kd/IC50)...")
    activities = []
    for standard_type in ("Ki", "Kd", "IC50"):
        activities.extend(fetch_chembl_binding_activities(chembl_id, standard_type))
    seen_genes = set()
    for act in activities:
        if act.get("standard_value") is None or act.get("standard_units") != "nM":
            continue
        # ChEMBL's standard_relation distinguishes a real measured value
        # ("=") from a censored bound: "> 30000" means no activity was
        # detected up to the highest concentration tested, not that
        # potency is 30000nM. Confirmed directly against this DB's own
        # stored data - e.g. caffeine's ADRA1A record is
        # relation=">" value=30000, and ChEMBL's own activity_comment on
        # that record spells it out: "largest value for measurements with
        # relation sign '>'". Silently accepting these turned negative/
        # no-signal screening results into apparent weak-affinity leads;
        # 16/65 (25%) of this DB's ChEMBL-sourced binding measurements had
        # this problem before this filter was added.
        if act.get("standard_relation") != "=":
            continue
        value = float(act["standard_value"])
        target_chembl_id = act["target_chembl_id"]
        exclusion = CHEMBL_ASSAY_LINK_EXCLUSIONS.get((act["assay_chembl_id"], target_chembl_id))
        if exclusion:
            print(f"    skipping assay {act['assay_chembl_id']} x {target_chembl_id}: {exclusion}")
            continue
        target = cached_chembl_target(target_chembl_id)
        for component in target.get("target_components", []):
            gene_symbol = next(
                (s["component_synonym"] for s in component["target_component_synonyms"]
                 if s["syn_type"] == "GENE_SYMBOL"),
                None,
            )
            if not gene_symbol:
                continue
            # The affinity cutoff only gates auto-discovery of a *new*
            # target - a gene with a curated ChEMBL mechanism is already
            # established as real, so every measurement for it should be
            # pooled regardless of magnitude (this is what was silently
            # dropping real weak-affinity ChEMBL data for caffeine's own
            # curated ADORA targets before this check was added).
            if gene_symbol not in mechanism_by_gene and value > MAX_SUPPLEMENTARY_AFFINITY_NM:
                continue
            if gene_symbol not in seen_genes:
                seen_genes.add(gene_symbol)
                print(f"    {gene_symbol}: {act['standard_type']}={value:g} nM "
                      f"via assay {act['assay_chembl_id']} - "
                      f"{act.get('assay_description') or '(no description)'}")
            target_info.setdefault(gene_symbol, {
                "accession": component["accession"],
                "chembl_target_id": target_chembl_id,
            })
            # external_ref is the assay itself, not just the target - lets
            # anyone trace a value back to exactly what was measured and how
            # (see fetch_chembl_binding_activities docstring on assay_type).
            citation_url, citation_text = chembl_activity_citation(act)
            add_measurement(gene_symbol, act["standard_type"], value,
                             "ChEMBL", act["assay_chembl_id"],
                             citation_url, citation_text, act.get("data_validity_comment"),
                             act.get("assay_description"))

    print("  fetching BindingDB binding activities...")
    try:
        bindingdb_activities = fetch_bindingdb_activities(molecule_smiles)
    except requests.exceptions.RequestException as err:
        # BindingDB is a supplementary/cross-validation source (see module
        # docstring notes on ChEMBL being primary), so an outage there
        # shouldn't abort the whole load - just skip it for this molecule.
        print(f"    BindingDB fetch failed ({err}), skipping for this molecule")
        bindingdb_activities = []
    for act in bindingdb_activities:
        exclusion = BINDINGDB_TARGET_LINK_EXCLUSIONS.get((act["external_ref"], act["target_name"]))
        if exclusion:
            print(f"    skipping BindingDB monomerid={act['external_ref']} x "
                  f"'{act['target_name']}': {exclusion}")
            continue
        # Cheap alias lookup (no API call) so a curated gene's weak-affinity
        # measurements aren't dropped by the auto-discovery cutoff below -
        # same reasoning as the ChEMBL loop above. Targets only resolvable
        # via UniProt (not in the alias map) always go through the cutoff,
        # since we can't know if they're curated without an API call, and
        # spending one per noise hit would be wasteful.
        aliased_gene = BINDINGDB_TARGET_NAME_ALIASES.get(act["target_name"].lower())
        is_curated = bool(aliased_gene) and aliased_gene in mechanism_by_gene
        if not is_curated and act["value"] > MAX_SUPPLEMENTARY_AFFINITY_NM:
            continue
        gene_symbol = aliased_gene
        if not gene_symbol:
            accession = resolve_uniprot_accession(protein_name=act["target_name"])
            if not accession:
                print(f"    could not resolve UniProt entry for BindingDB target "
                      f"'{act['target_name']}', skipping")
                continue
            entry = fetch_uniprot_entry(accession)
            gene_symbol = uniprot_gene_symbol(entry) or accession
            target_info.setdefault(gene_symbol, {"accession": accession, "chembl_target_id": None})
            print(f"    BindingDB surfaced new target: {gene_symbol} "
                  f"({act['target_name']})")
        else:
            target_info.setdefault(gene_symbol, {
                "accession": None, "chembl_target_id": None,
            })
        bdb_url, bdb_text = bindingdb_citation(act["external_ref"])
        add_measurement(gene_symbol, act["affinity_type"], act["value"],
                         "BindingDB", act["external_ref"], bdb_url, bdb_text)

    print("  fetching PDSP Ki database activities...")
    cas_numbers = fetch_pubchem_cas_numbers(name)
    for act in fetch_pdsp_activities(cas_numbers):
        gene_symbol = act["gene_symbol"]
        if gene_symbol not in mechanism_by_gene and act["value"] > MAX_SUPPLEMENTARY_AFFINITY_NM:
            continue
        if gene_symbol not in target_info:
            accession = resolve_uniprot_accession(gene_symbol=gene_symbol)
            if not accession:
                print(f"    could not resolve UniProt accession for PDSP gene "
                      f"'{gene_symbol}', skipping")
                continue
            target_info[gene_symbol] = {"accession": accession, "chembl_target_id": None}
            print(f"    PDSP surfaced new target: {gene_symbol}")
        add_measurement(gene_symbol, act["affinity_type"], act["value"],
                         "PDSP", act["external_ref"],
                         citation_text=act.get("reference"))

    # 3. Cell-based/functional ChEMBL assays (assay_type=F). Two roles now:
    #    (a) corroborate a gene that already has a real binding measurement
    #    (original behavior - stored in functional_value, never blended
    #    into binding_value, see schema.sql); (b) when a gene has NO
    #    binding-type data at all (from ChEMBL/BindingDB/PDSP), still
    #    surface it as a functional-only lead rather than silently
    #    dropping it. (b) used to only happen indirectly and incorrectly
    #    via BindingDB, which doesn't expose ChEMBL's own binding-vs-
    #    functional distinction at all - it surfaced real ChEMBL functional
    #    assays (e.g. a TNF-alpha production assay, an amyloid-beta self-
    #    aggregation assay) mislabeled as if they were direct binding_value
    #    measurements. Sourcing them here instead keeps them correctly
    #    typed as functional-only *and* resolves the gene via ChEMBL's own
    #    structured target_chembl_id (reliable) rather than BindingDB's
    #    free-text target name run through a fuzzy UniProt search
    #    (confirmed to guess the wrong gene in real cases - see
    #    resolve_uniprot_accession).
    print("  fetching ChEMBL functional activities (cell-based)...")
    seen_functional_genes = set()
    for act in fetch_chembl_functional_activities(chembl_id):
        if act.get("standard_value") is None or act.get("standard_units") != "nM":
            continue
        # See the identical check in the binding-activity loop above: a
        # non-"=" relation is a censored bound (no signal detected up to
        # this concentration), not a real measured value. This mattered
        # far more here than for binding: 118/140 (84%) of the functional-
        # only leads this discovery path first produced turned out to be
        # exactly this pattern - almost all "AC50 > 30000nM"/"AC50 >
        # 10000nM" ceiling values from one secondary-pharmacology safety
        # panel paper tested against nearly every molecule in this DB.
        if act.get("standard_relation") != "=":
            continue
        value = float(act["standard_value"])
        target_chembl_id = act["target_chembl_id"]
        target = cached_chembl_target(target_chembl_id)
        for component in target.get("target_components", []):
            gene_symbol = next(
                (s["component_synonym"] for s in component["target_component_synonyms"]
                 if s["syn_type"] == "GENE_SYMBOL"),
                None,
            )
            if not gene_symbol:
                continue
            has_binding_data = gene_symbol in measurements
            if (not has_binding_data and gene_symbol not in mechanism_by_gene
                    and value > MAX_SUPPLEMENTARY_AFFINITY_NM):
                continue
            if gene_symbol not in seen_functional_genes:
                seen_functional_genes.add(gene_symbol)
                print(f"    {gene_symbol}: {act['standard_type']}={value:g} nM "
                      f"via assay {act['assay_chembl_id']} - "
                      f"{act.get('assay_description') or '(no description)'}")
            target_info.setdefault(gene_symbol, {
                "accession": component["accession"],
                "chembl_target_id": target_chembl_id,
            })
            citation_url, citation_text = chembl_activity_citation(act)
            add_functional_measurement(gene_symbol, act["standard_type"], value,
                                        "ChEMBL", act["assay_chembl_id"],
                                        citation_url, citation_text, act.get("data_validity_comment"),
                                        act.get("assay_description"))

    # 4. DGIdb interactions, used to cross-validate the pooled edges.
    print("  fetching DGIdb interactions...")
    dgidb_interactions = fetch_dgidb_interactions(name)
    dgidb_by_gene = {i["gene"]["name"]: i for i in dgidb_interactions}

    # Build one interaction edge per gene with a real measurement - binding
    # (Ki > Kd > IC50, pooled across every source that reported that type)
    # and/or, now, functional-only when no binding-type data exists at all.
    for gene_symbol in measurements.keys() | functional_measurements.keys():
        reduced = reduce_measurements(measurements.get(gene_symbol, {}))
        if reduced:
            (binding_type, binding_value, n_measurements,
             contributing_sources, binding_rows) = reduced
        else:
            binding_type = binding_value = n_measurements = None
            contributing_sources = {}
            binding_rows = []

        functional_reduced = reduce_measurements(
            functional_measurements.get(gene_symbol, {}),
            preference=FUNCTIONAL_STANDARD_TYPES,
        )
        if functional_reduced:
            (functional_type, functional_value, functional_n_measurements,
             functional_sources, functional_rows) = functional_reduced
        else:
            functional_type = functional_value = functional_n_measurements = None
            functional_sources = {}
            functional_rows = []

        if not reduced and not functional_reduced:
            continue

        info = target_info[gene_symbol]
        accession = info["accession"] or resolve_uniprot_accession(gene_symbol=gene_symbol)
        if not accession:
            print(f"    could not resolve UniProt accession for {gene_symbol}, skipping")
            continue

        print(f"  resolving target {gene_symbol} via UniProt...")
        entry = fetch_uniprot_entry(accession)
        protein_name = entry["proteinDescription"]["recommendedName"]["fullName"]["value"]
        function_summary = uniprot_function_summary(entry)

        target_id = upsert_target(
            conn, gene_symbol, protein_name, accession,
            info["chembl_target_id"], function_summary, entry,
        )

        mech = mechanism_by_gene.get(gene_symbol)
        is_primary = 1 if mech else 0
        if mech:
            action_type, moa = mech["action_type"], mech["mechanism_of_action"]
            # For a curated primary mechanism, the authoritative citation is
            # the drug-level reference behind that claim (FDA label, PubMed
            # review) - not just whichever raw assay happened to be pooled
            # last into the binding-affinity median. Keep the assay id as
            # external_ref (still traceable to a specific measurement);
            # only the citation shown alongside it changes.
            mech_url, mech_text = chembl_mechanism_citation(mech)
            # Prefer the binding row for the drug-level citation, but fall
            # back to the functional row: a curated gene whose only ChEMBL
            # data is functional used to lose this citation entirely.
            citation_target = (contributing_sources if "ChEMBL" in contributing_sources
                               else functional_sources)
            if (mech_url or mech_text) and "ChEMBL" in citation_target:
                ref, _, _, validity = citation_target["ChEMBL"]
                citation_target["ChEMBL"] = (ref, mech_url, mech_text, validity)
        elif not reduced:
            # No binding-type measurement at all for this gene - only
            # possible now that functional-only ChEMBL discovery exists
            # (see the functional-activity loop above). Kept as its own
            # sentinel rather than reusing BINDER, since "binding activity
            # reported" would misdescribe what was actually measured (e.g.
            # a cellular TNF-alpha release assay isn't a binding assay to
            # any single protein).
            action_type = "FUNCTIONAL"
            moa = (f"Functional activity reported via {'/'.join(functional_sources)}; "
                   "no direct binding measurement; mechanism not curated.")
        elif gene_symbol.startswith("ADORA"):
            action_type = "ANTAGONIST"
            moa = f"Adenosine receptor antagonist ({gene_symbol})"
        else:
            # NOTE: action_type is part of interactions' UNIQUE key and SQLite
            # never treats NULL as equal to itself there, so a real NULL would
            # break upsert idempotency (every re-run would insert a duplicate
            # row instead of updating). Use an explicit sentinel instead.
            action_type = "BINDER"
            moa = (f"Binding activity reported via {'/'.join(contributing_sources)}; "
                   "mechanism not curated.")

        interaction_id = upsert_interaction(
            conn, molecule_id, target_id, action_type, moa, is_primary,
            binding_value, binding_type, "nM" if binding_value else None, n_measurements,
            functional_value, functional_type, "nM" if functional_value else None,
            functional_n_measurements,
        )
        # Binding and functional provenance are recorded separately rather
        # than merged into one row per source - see interaction_sources.role
        # in schema.sql. Merging them meant ChEMBL's functional assay ID was
        # silently dropped on every edge that also had ChEMBL binding data.
        for role, source_map in (("binding", contributing_sources),
                                  ("functional", functional_sources)):
            for source_name, source_info in source_map.items():
                external_ref, citation_url, citation_text, _ = source_info
                # reduce_measurements returns these entries with no citation,
                # so the only way one is present is the curated-mechanism
                # override above, which is the sole 'mechanism' writer.
                kind = "mechanism" if (citation_url or citation_text) else None
                link_source(conn, interaction_id, source_ids[source_name], external_ref,
                            citation_url, citation_text, role=role,
                            citation_kind=kind)
        # Every measurement behind those two pooled values, individually.
        # Recorded from the unreduced rows, so each keeps its own paper -
        # deliberately *not* the mechanism citation the loop above may have
        # just written over contributing_sources["ChEMBL"], which is a
        # drug-level review and not evidence for any single number.
        for role, affinity_type, rows in (
            ("binding", binding_type, binding_rows),
            ("functional", functional_type, functional_rows),
        ):
            if rows:
                record_measurements(conn, interaction_id, source_ids, role,
                                    affinity_type, rows)
        if gene_symbol in dgidb_by_gene:
            dgidb_url, dgidb_text = dgidb_citation(dgidb_by_gene[gene_symbol])
            link_source(conn, interaction_id, source_ids["DGIdb"], gene_symbol,
                        dgidb_url, dgidb_text, role="annotation",
                        citation_kind="annotation" if (dgidb_url or dgidb_text) else None)

    conn.commit()


# Columns added after the first schema was written. schema.sql uses
# CREATE TABLE IF NOT EXISTS, so it will not alter a table that already
# exists - a database built before one of these landed would fail at insert
# time with a confusing "no such column". Checked up front instead, with an
# actionable message.
REQUIRED_COLUMNS = {
    "sources": ("source_release",),
    "interaction_sources": ("citation_url", "citation_text", "citation_kind", "role"),
    "molecules": ("wikipedia_url",),
    "targets": ("wikipedia_url",),
    "interactions": ("functional_value", "functional_type", "functional_units",
                      "functional_n_measurements"),
    "measurements": ("assay_description",),
}


def check_schema(conn):
    for table, columns in REQUIRED_COLUMNS.items():
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not existing:
            continue  # table not created yet - executescript is about to
        missing = [c for c in columns if c not in existing]
        if missing:
            raise SystemExit(
                f"{DB_PATH} predates the current schema: {table} is missing "
                f"{', '.join(missing)}.\nRerun with --rebuild to discard it and "
                "build from scratch."
            )


def add_column_if_missing(conn, table, column, decl):
    """ALTER TABLE ADD COLUMN, but only if `column` isn't already there.

    schema.sql's CREATE TABLE IF NOT EXISTS will not alter a table that
    already exists, so a column added to an existing table after the first
    build needs an explicit migration - and this is deliberately narrow
    rather than a general auto-migration facility. check_schema's job is to
    demand --rebuild for anything that *could* change which rows exist, and
    that job has to stay intact; this helper is only for the one column
    where that's provably not a risk. target_complexes.wikipedia_url adds no
    rows, changes no molecule/edge/measurement, and is filled from Wikidata
    exactly as molecules.wikipedia_url and targets.wikipedia_url already
    are - the same derivable-from-a-snapshot exemption from --rebuild that
    assay_description and target_complexes itself used (see CLAUDE.md
    "Running it"). Do not reach for this for a column whose absence could
    mean a different set of rows exists - that case must still fail
    check_schema and demand --rebuild.
    """
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


# Wikipedia links, resolved through Wikidata.
#
# Never by title search. "ATM" and "APP" are English words, "TNF" and "NOTUM"
# are ambiguous, and a search API will cheerfully return an article about
# something else - which is invariant 6 (refuse to guess a gene) applied to
# links instead of genes. Every lookup here is an exact match on an identifier
# this database already holds, and an item that resolves to more than one
# English article is skipped rather than guessed at.
#
# Molecules match on InChIKey (P235), PubChem CID (P662) or ChEMBL ID (P592).
# All three are tried because they disagree about coverage, not about answers:
# Wikidata's theophylline item carries a different ChEMBL ID from this DB's
# (parent vs. salt), and would be missed by P592 alone. Where more than one
# matches, they agree - checked for the original seven seed molecules.
#
# Targets match on UniProt accession (P352), then follow "encoded by" (P702)
# to the gene item. Both hops are needed: English Wikipedia's article is on
# the protein item for ACHE and on the gene item for ADORA1, and there is no
# rule saying which.
WIKIDATA_MOLECULE_QUERY = """
SELECT ?key ?article WHERE {
  VALUES (?key ?prop ?value) { %s }
  ?item ?prop ?value .
  ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> .
}"""

WIKIDATA_TARGET_QUERY = """
SELECT ?key ?article WHERE {
  VALUES (?key ?accession) { %s }
  ?protein wdt:P352 ?accession .
  { ?article schema:about ?protein }
  UNION
  { ?protein wdt:P702 ?gene . ?article schema:about ?gene }
  ?article schema:isPartOf <https://en.wikipedia.org/> .
}"""

# Protein assemblies (target_complexes) cannot be linked the same way -
# there is no rule that walks an identifier this database already holds
# (a member's UniProt accession) to the right Wikidata concept, only to
# confidently wrong or overly broad ones. Two rules were tried against the
# live endpoint (2026-09-05):
#
#   - Following P527 ("has part") / P361 ("part of") outward from the
#     members' accessions returns, per assembly, a pile of Reactome-imported
#     complex items plus a few broad concept items - and the ones that carry
#     an English article are confidently wrong: 5-HT3 resolves to "Cys-loop
#     receptor", KCNQ1/KCNE1 to "KCNQ channels".
#   - Tightening that to unanimity (an item reachable from *every* member's
#     accession, not just one) still fails: the 7-member NMDA receptor group
#     resolves 7/7 to "Ionotropic glutamate receptor" (too broad) while the
#     correct "NMDA receptor" article is reachable from only 4/7 members.
#     GABA-A alpha-1/alpha-2/beta-2/gamma-2 resolves 4/4 to the correct
#     "GABAA receptor" - so across the six assemblies with any hit at all,
#     unanimity is right once, wrong-but-confident once, and the other five
#     assemblies resolve to nothing.
#
# A rule that is sometimes wrong with full confidence is worse than one that
# is sometimes silent, so there is no derivation here. What is hand-written
# below is only the identity assertion - "this ChEMBL complex id is that
# Wikidata item" - never the article itself: the article is still resolved
# from the item at build time through the same apply_articles ambiguity
# check as molecules and targets, so a page move or rename is picked up
# automatically. That keeps this inside invariant 15 (resolve by identifier,
# never by name): what is curated is which identifier, not which title.
COMPLEX_WIKIDATA_ITEMS = {
    # The glutamate NMDA receptor is reached three ways in target_complexes -
    # the 7-subunit PROTEIN COMPLEX GROUP plus the two precise GRIN1/GRIN2A
    # and GRIN1/GRIN2B PROTEIN COMPLEX dimers that resolve_groups carries on
    # `absorbed` (see export_graph.py) - and all three name the same
    # receptor, so all three take the same item.
    "CHEMBL2094124": "Q414896",    # Glutamate [NMDA] receptor (7 subunits)
    "CHEMBL1907603": "Q414896",    # Glutamate NMDA receptor; GRIN1/GRIN2B
    "CHEMBL1907604": "Q414896",    # Glutamate NMDA receptor; GRIN1/GRIN2A
    "CHEMBL2094132": "Q3454515",   # Serotonin 3 (5-HT3) receptor
    "CHEMBL5303741": "Q60147",     # GABA-A alpha-1/alpha-2/beta-2/gamma-2
    "CHEMBL2363032": "Q14905735",  # Voltage-gated calcium channel
    # Mapped to None deliberately: English Wikipedia has no article for the
    # IKs channel itself. Wikidata's own complex item (Q107517499, a Complex
    # Portal import) carries no article, and KCNQ1 (Q14865150)/KCNE1
    # (Q14905770) do have articles - but those are the *subunits*, already
    # linked from the subunit target nodes themselves. This entry is the
    # record that the assembly was looked at and found to have no article of
    # its own, not that it was missed - the same spirit as
    # CHEMBL_ASSAY_LINK_EXCLUSIONS being an explicit exclusion rather than a
    # silent drop.
    "CHEMBL2221347": None,         # Voltage-gated potassium channel, IKs
}

WIKIDATA_ITEM_QUERY = """
SELECT ?key ?article WHERE {
  VALUES (?key ?item) { %s }
  ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> .
}"""

# The endpoint times out on large VALUES blocks (a 51-accession target query
# 504s reliably); it answers 15 at a time in about a second.
WIKIDATA_CHUNK = 15


def sparql_articles(query_template, values):
    """Run one Wikidata SPARQL query per chunk of `values` and return
    {key: {article, ...}}. `values` is a list of pre-rendered SPARQL VALUES
    tuples. Returns partial results rather than raising: a Wikipedia link is
    a convenience, and losing the endpoint should not fail a build that has
    already fetched every measurement in the database."""
    found = {}
    for start in range(0, len(values), WIKIDATA_CHUNK):
        chunk = values[start:start + WIKIDATA_CHUNK]
        try:
            data = get_json(
                WIKIDATA_SPARQL,
                params={"query": query_template % " ".join(chunk), "format": "json"},
                headers={"User-Agent": WIKIDATA_USER_AGENT},
            )
        except requests.exceptions.RequestException as err:
            print(f"    Wikidata lookup failed ({type(err).__name__}); "
                  "leaving these links unresolved")
            continue
        for binding in data["results"]["bindings"]:
            found.setdefault(binding["key"]["value"], set()).add(
                binding["article"]["value"])
    return found


def sparql_literal(value):
    """A SPARQL string literal. Every value passed here is an identifier this
    pipeline already validated (InChIKey, CID, accession, gene symbol), but
    quoting is not the place to rely on that."""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def apply_articles(conn, table, key_column, found, keys):
    """Write the resolved URLs, skipping anything ambiguous. Only writes rows
    that resolved: a chunk the endpoint refused leaves the previous run's URL
    in place rather than blanking it."""
    resolved = ambiguous = 0
    for key in keys:
        articles = found.get(key)
        if not articles:
            continue
        if len(articles) > 1:
            ambiguous += 1
            print(f"    {key}: {len(articles)} English articles on Wikidata, "
                  "skipping rather than picking one")
            continue
        conn.execute(
            f"UPDATE {table} SET wikipedia_url = ? WHERE {key_column} = ?",
            (articles.pop(), key),
        )
        resolved += 1
    print(f"  {table}: {resolved}/{len(keys)} linked to Wikipedia"
          + (f", {ambiguous} skipped as ambiguous" if ambiguous else "")
          + f", {len(keys) - resolved - ambiguous} with no article")


def resolve_wikipedia_urls(conn):
    """Fill molecules.wikipedia_url and targets.wikipedia_url. Runs once at
    the end of a build over everything in the database, rather than per
    molecule: it is two dozen HTTP requests either way, and doing it in one
    pass keeps it out of the per-molecule path where a Wikidata outage would
    look like a data problem."""
    print("\nResolving Wikipedia links via Wikidata...")
    molecules = list(conn.execute(
        "SELECT name, chembl_id, pubchem_cid, inchikey FROM molecules ORDER BY name"))
    values = []
    for name, chembl_id, pubchem_cid, inchikey in molecules:
        key = sparql_literal(name)
        if inchikey:
            values.append(f"({key} wdt:P235 {sparql_literal(inchikey)})")
        if pubchem_cid:
            values.append(f"({key} wdt:P662 {sparql_literal(pubchem_cid)})")
        if chembl_id:
            values.append(f"({key} wdt:P592 {sparql_literal(chembl_id)})")
    apply_articles(conn, "molecules", "name",
                   sparql_articles(WIKIDATA_MOLECULE_QUERY, values),
                   [m[0] for m in molecules])

    targets = list(conn.execute(
        "SELECT gene_symbol, uniprot_accession FROM targets"
        " WHERE uniprot_accession IS NOT NULL ORDER BY gene_symbol"))
    values = [f"({sparql_literal(gene)} {sparql_literal(acc)})"
              for gene, acc in targets]
    apply_articles(conn, "targets", "gene_symbol",
                   sparql_articles(WIKIDATA_TARGET_QUERY, values),
                   [t[0] for t in targets])

    resolve_complex_wikipedia_urls(conn)


def resolve_complex_wikipedia_urls(conn):
    """Fill target_complexes.wikipedia_url from the hand-curated
    COMPLEX_WIKIDATA_ITEMS map (see the comment above it for why this one
    can't be derived from an identifier the way molecules and targets are).

    A separate function rather than inline in resolve_wikipedia_urls because
    it has a second caller: --complexes-only re-derives assembly membership
    without touching a molecule, edge or measurement row, and needs to
    re-resolve these links the same way without also re-querying Wikidata
    for every molecule and target in the database.

    Only queries complexes that are actually in target_complexes right now -
    load_target_complexes replaces that table wholesale on every run, so an
    assembly dropped from the seed set's reach is already gone from here
    too - and only those with a non-None entry in the map. An assembly
    present in the database but absent from the map entirely is a new one
    nobody has looked at yet, which is reported by name so it doesn't sit
    silently unlinked."""
    chembl_ids = [row[0] for row in conn.execute(
        "SELECT chembl_id FROM target_complexes ORDER BY chembl_id")]
    unmapped = [c for c in chembl_ids if c not in COMPLEX_WIKIDATA_ITEMS]
    if unmapped:
        print(f"    {len(unmapped)} assembly(ies) in target_complexes have no "
              f"entry in COMPLEX_WIKIDATA_ITEMS: {', '.join(unmapped)}")

    queryable = [c for c in chembl_ids if COMPLEX_WIKIDATA_ITEMS.get(c)]
    values = [f"({sparql_literal(c)} wd:{COMPLEX_WIKIDATA_ITEMS[c]})"
              for c in queryable]
    apply_articles(conn, "target_complexes", "chembl_id",
                   sparql_articles(WIKIDATA_ITEM_QUERY, values),
                   queryable)


def prune_orphan_targets(conn):
    """Targets are shared across molecules, so reset_molecule can't clean them
    up per-molecule; anything left with no edges at the end of a full run is a
    target that no longer has support in any source."""
    cur = conn.execute(
        """
        DELETE FROM targets
         WHERE NOT EXISTS (SELECT 1 FROM interactions WHERE interactions.target_id = targets.id)
        """
    )
    if cur.rowcount:
        print(f"Pruned {cur.rowcount} target(s) left without any interaction.")


# SQLite's default build caps a single statement at 999 bound parameters
# ("too many SQL variables" past that - see sqlite.org/limits.html). This
# database's own ChEMBL assay ids number ~1,388, so the IN (...) list built
# from them has to go in under that ceiling rather than as one query.
SQLITE_MAX_VARIABLES = 999


def load_target_complexes(conn, local_chembl):
    """Record which of this database's targets are subunits of one physical
    protein assembly, per the local ChEMBL bulk release, keyed on identifiers
    only - never a gene symbol or name (invariants 6 and 15).

    ChEMBL's protein_classification tree cannot answer this question - see
    the comment above target_complexes in schema.sql for why (CACNA1C and
    CACNA1D share a leaf while being different channels; CACNB2 sits under
    an unrelated branch despite physically co-assembling with CACNA1C).
    target_dictionary.target_type is what actually distinguishes an asserted
    multi-subunit assembly ('PROTEIN COMPLEX'), a poorly-defined one
    ('PROTEIN COMPLEX GROUP', ChEMBL's own wording), and an ordinary single
    protein or family/selectivity grouping, which this function ignores.

    Walks outward from every distinct ChEMBL assay id this database's own
    measurements already cite, rather than sweeping all of target_dictionary
    - a complex only gets recorded here if a seed molecule's own data
    actually reached it. Idempotent: both tables are replaced wholesale on
    every call, so a molecule dropped from the seed set (and the assay ids
    that went with it) doesn't leave a stale complex behind.

    Needs `local_chembl` (a chembl_local.LocalChEMBL): target_type,
    target_components and component_sequences are release-scoped ChEMBL
    tables the REST API path never fetches at all. If it's None, this
    leaves both tables exactly as they were rather than emptying them - a
    build with no local release available is not evidence there are no
    complexes, it's evidence nobody looked this time, and silently blanking
    a real answer would be worse than leaving a stale one in place.
    """
    if local_chembl is None:
        print(
            "\nSkipping target_complexes: complex membership needs the local "
            "ChEMBL release (chembl_local.find_database() found none, or "
            "--chembl-source api forced the REST path). Leaving any existing "
            "target_complexes/target_complex_members rows untouched."
        )
        return

    assay_ids = [row[0] for row in conn.execute(
        """
        SELECT DISTINCT m.external_ref
        FROM measurements m
        JOIN sources s ON s.id = m.source_id
        WHERE s.name = 'ChEMBL' AND m.external_ref LIKE 'CHEMBL%'
        """
    )]
    print(f"\nResolving target complexes from {len(assay_ids)} ChEMBL assay ids...")

    cchembl = local_chembl.conn
    complex_targets = {}  # chembl_id -> sqlite3.Row (tid, chembl_id, pref_name, target_type)
    for start in range(0, len(assay_ids), SQLITE_MAX_VARIABLES):
        chunk = assay_ids[start:start + SQLITE_MAX_VARIABLES]
        placeholders = ",".join("?" for _ in chunk)
        for row in cchembl.execute(
            f"""
            SELECT DISTINCT td.tid, td.chembl_id, td.pref_name, td.target_type
            FROM assays a
            JOIN target_dictionary td ON td.tid = a.tid
            WHERE a.chembl_id IN ({placeholders})
              AND td.target_type IN ('PROTEIN COMPLEX', 'PROTEIN COMPLEX GROUP')
            """,
            chunk,
        ):
            complex_targets[row["chembl_id"]] = row

    kept = []
    for chembl_id, row in complex_targets.items():
        # Every component ChEMBL lists for this assembly, including ones this
        # database doesn't hold at all - n_components is meant to answer "how
        # many subunits does ChEMBL say this assembly has", not "how many of
        # them happen to already be in this graph".
        accessions = [r[0] for r in cchembl.execute(
            """
            SELECT DISTINCT cs.accession
            FROM target_components tc
            JOIN component_sequences cs ON cs.component_id = tc.component_id
            WHERE tc.tid = ? AND cs.accession IS NOT NULL
            """,
            (row["tid"],),
        )]
        if not accessions:
            continue
        placeholders = ",".join("?" for _ in accessions)
        members = list(conn.execute(
            f"SELECT id, gene_symbol FROM targets WHERE uniprot_accession IN ({placeholders})",
            accessions,
        ))
        # A "complex" with fewer than two members present in this database is
        # not a grouping of anything here - it's a single target that
        # happens to carry a ChEMBL complex record, and recording it would
        # assert a merge the graph has no second node to merge with.
        if len(members) < 2:
            continue
        kept.append({
            "chembl_id": chembl_id,
            "name": row["pref_name"],
            "target_type": row["target_type"],
            "n_components": len(accessions),
            "members": members,
        })

    # Idempotent: dropped and rebuilt wholesale rather than upserted, same
    # reasoning as reset_molecule - a molecule that leaves the seed set can
    # take a complex's only two present members with it, and there is no
    # per-run diff cheap enough to compute that a full replace doesn't already
    # give for free.
    conn.execute("DELETE FROM target_complex_members")
    conn.execute("DELETE FROM target_complexes")
    for c in kept:
        conn.execute(
            """
            INSERT INTO target_complexes (chembl_id, name, target_type,
                                           n_components, source_release)
            VALUES (?, ?, ?, ?, ?)
            """,
            (c["chembl_id"], c["name"], c["target_type"], c["n_components"],
             local_chembl.release),
        )
        for target_id, _ in c["members"]:
            conn.execute(
                "INSERT INTO target_complex_members (complex_chembl_id, target_id)"
                " VALUES (?, ?)",
                (c["chembl_id"], target_id),
            )
        gene_symbols = ", ".join(sorted(g for _, g in c["members"]))
        print(f"  {c['chembl_id']} ({c['target_type']}) {c['name']}: "
              f"{len(c['members'])}/{c['n_components']} members present - {gene_symbols}")

    print(f"{len(kept)} complex(es) recorded, of {len(complex_targets)} "
          f"complex-typed targets reached.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild", action="store_true",
        help="delete the existing database and build from scratch (needed "
             "after a schema change, and the honest way to re-baseline the "
             "counts quoted in CLAUDE.md)",
    )
    parser.add_argument(
        "--refresh-pdsp", action="store_true",
        help=f"re-download the PDSP bulk CSV even if the local cache is "
             f"younger than {PDSP_CACHE_MAX_AGE_DAYS} days",
    )
    parser.add_argument(
        "--chembl-source", choices=("auto", "local", "api"), default="auto",
        help="where to read ChEMBL from. 'local' uses a downloaded bulk "
             "release (see scripts/chembl_local.py); 'api' forces the REST "
             "API; 'auto' (default) prefers a local release if one is "
             "present and falls back to the API. Only ChEMBL is affected - "
             "UniProt, PubChem, DGIdb, BindingDB and PDSP are unchanged.",
    )
    parser.add_argument(
        "--chembl-db", metavar="PATH",
        help="path to a ChEMBL bulk-release SQLite file, overriding the "
             "search in chembl_local.SEARCH_GLOBS",
    )
    parser.add_argument(
        "--complexes-only", action="store_true",
        help="backfill target_complexes/target_complex_members, and their "
             "Wikipedia links, on the existing database from the local "
             "ChEMBL release (see load_target_complexes) and exit, without "
             "touching any molecule, edge or measurement row. The same "
             "new-tables-plus-backfill exemption from --rebuild that "
             "assay_description used - see CLAUDE.md ('Running it').",
    )
    args = parser.parse_args()

    if args.refresh_pdsp:
        download_pdsp_database(force=True)

    # Resolve the ChEMBL backend before touching the database, so a bad
    # --chembl-db path fails immediately rather than 40 minutes into a run.
    local_chembl = None
    if args.chembl_source != "api":
        path = args.chembl_db or chembl_local.find_database()
        if path:
            local_chembl = chembl_local.LocalChEMBL(path)
        elif args.chembl_source == "local":
            parser.error(
                "--chembl-source local, but no ChEMBL release was found. "
                "Pass --chembl-db PATH, set CHEMBL_SQLITE_PATH, or see the "
                "download instructions in scripts/chembl_local.py."
            )
    set_chembl_backend(local_chembl)
    print(f"ChEMBL source: {chembl_backend_label()}")
    if local_chembl is not None:
        counts = local_chembl.counts()
        print("  " + ", ".join(f"{n:,} {t}" for t, n in counts.items()))

    DB_PATH.parent.mkdir(exist_ok=True)

    if args.complexes_only:
        # The backfill path: target_complexes/target_complex_members are
        # derivable from a snapshot already on disk (the same exemption
        # assay_description used - see CLAUDE.md "Running it"), so this
        # never touches a molecule, edge or measurement row and never needs
        # --rebuild. It now makes one live Wikidata call too, to resolve
        # target_complexes.wikipedia_url from COMPLEX_WIKIDATA_ITEMS - still
        # nothing that touches a molecule, edge or measurement row, and
        # resolve_complex_wikipedia_urls is called directly rather than via
        # the full resolve_wikipedia_urls so this path doesn't also re-query
        # Wikidata for every molecule and target in the database.
        if not DB_PATH.exists():
            parser.error(
                f"--complexes-only needs an existing database at {DB_PATH}; "
                "run build_db.py without it first."
            )
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(SCHEMA_PATH.read_text())
        # target_complexes predates its wikipedia_url column on any database
        # built before this change; schema.sql's CREATE TABLE IF NOT EXISTS
        # won't add it to a table that already exists (see
        # add_column_if_missing).
        add_column_if_missing(conn, "target_complexes", "wikipedia_url", "TEXT")
        load_target_complexes(conn, local_chembl)
        resolve_complex_wikipedia_urls(conn)
        conn.commit()
        conn.close()
        if local_chembl is not None:
            local_chembl.close()
        return

    if args.rebuild and DB_PATH.exists():
        print(f"--rebuild: removing {DB_PATH}")
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    check_schema(conn)
    conn.executescript(SCHEMA_PATH.read_text())
    # See add_column_if_missing: an existing database predates
    # target_complexes.wikipedia_url, and CREATE TABLE IF NOT EXISTS above
    # won't add it on its own.
    add_column_if_missing(conn, "target_complexes", "wikipedia_url", "TEXT")

    source_ids = {
        "PubChem": get_or_create_source(conn, "PubChem", PUBCHEM_BASE),
        # base_url stays the public API even on a local build: it is what a
        # reader should follow. Which snapshot produced the numbers is
        # recorded in source_release instead.
        "ChEMBL": get_or_create_source(
            conn, "ChEMBL", CHEMBL_BASE,
            release=local_chembl.release if local_chembl else None,
        ),
        "DGIdb": get_or_create_source(conn, "DGIdb", DGIDB_BASE),
        "UniProt": get_or_create_source(conn, "UniProt", UNIPROT_BASE),
        "BindingDB": get_or_create_source(conn, "BindingDB", BINDINGDB_BASE),
        "PDSP": get_or_create_source(conn, "PDSP", PDSP_CSV_URL),
    }
    conn.commit()

    for molecule in SEED_MOLECULES:
        load_molecule(conn, molecule["name"], molecule["chembl_id"], source_ids)

    prune_orphan_targets(conn)
    conn.commit()

    load_target_complexes(conn, local_chembl)
    conn.commit()

    resolve_wikipedia_urls(conn)
    conn.commit()

    counts = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("molecules", "targets", "interactions", "interaction_sources")
    }
    conn.close()
    if local_chembl is not None:
        local_chembl.close()
    print(f"\nDone. Database written to {DB_PATH}")
    print("  " + ", ".join(f"{n} {t}" for t, n in counts.items()))
    print(f"  ChEMBL data from: {chembl_backend_label()}")


if __name__ == "__main__":
    main()
