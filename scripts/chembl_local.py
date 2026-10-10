#!/usr/bin/env python3
"""Local ChEMBL bulk-release backend.

Answers the same five ChEMBL questions build_db.py asks the REST API, but
against a downloaded SQLite release instead of over HTTP. Every function
here returns the *same dict shape* the corresponding REST endpoint does, so
load_molecule() consumes either backend without knowing which one it got --
that equivalence is the whole design, and it's what makes an API-vs-local
diff a meaningful regression check rather than a shape mismatch.

Why bother: a full rebuild against the API is ~45 minutes, nearly all of it
network wait, and it aborted twice in one week on EBI 500s and read timeouts
(see docs/DATA-QUALITY-LOG.md). The same queries against the local release
return in ~15ms, offline, pinned to a citable release.

What this does NOT replace: UniProt, PubChem, DGIdb and BindingDB still go
over the network. Those are a handful of requests per molecule and were
never the bottleneck or the failure point.

Getting the data (~5.4GB download, 29GB extracted):

    curl -O https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/chembl_37_sqlite.tar.gz
    tar xzf chembl_37_sqlite.tar.gz

Point CHEMBL_SQLITE_PATH at the resulting .db, or drop it anywhere matching
SEARCH_GLOBS below.
"""

import glob
import os
import pathlib
import re
import sqlite3

# Checked in order; first match wins. The globs are release-agnostic on
# purpose so a future chembl_38 is picked up without a code change.
SEARCH_GLOBS = (
    "/mnt/data/chembl/chembl_*/chembl_*_sqlite/chembl_*.db",
    "/mnt/data/chembl/chembl_*.db",
    str(pathlib.Path(__file__).parent.parent / "db" / "chembl_*.db"),
)

# ChEMBL's own placeholder document, attached to activities deposited without
# a publication (direct data deposits, DrugMatrix, etc). It has no pubmed_id,
# no doi and no title, so citing it produces a link to an empty record card.
# The REST API returns it too; recorded here only so the reason it shows up
# in citations is written down somewhere.
UNPUBLISHED_DOC_CHEMBL_ID = "CHEMBL1158643"


def find_database():
    """Absolute path to a local ChEMBL release, or None if none is present.

    CHEMBL_SQLITE_PATH wins if set; it's an error for it to point at nothing,
    since the only reason to set it is to override the search."""
    explicit = os.environ.get("CHEMBL_SQLITE_PATH")
    if explicit:
        path = pathlib.Path(explicit).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"CHEMBL_SQLITE_PATH points at {path}, which is not a file"
            )
        return str(path)
    for pattern in SEARCH_GLOBS:
        # Sorted descending so chembl_38 beats chembl_37 when both are present.
        matches = sorted(glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]
    return None


class LocalChEMBL:
    """Read-only handle on a ChEMBL bulk release.

    Opened via a file: URI with mode=ro so a bug here can never write to a
    29GB download that took an hour to fetch. check_same_thread is left at
    its default: this pipeline is single-threaded and silently allowing
    cross-thread use would hide a real bug if that ever changed."""

    def __init__(self, path):
        self.path = str(path)
        uri = f"file:{pathlib.Path(self.path).as_posix()}?mode=ro"
        self.conn = sqlite3.connect(uri, uri=True)
        self.conn.row_factory = sqlite3.Row
        self._target_cache = {}

    def close(self):
        self.conn.close()

    # -- provenance ------------------------------------------------------

    @property
    def release(self):
        """Release label, e.g. "chembl_37", for citing which snapshot a
        rebuild used. Taken from the filename rather than a table because
        ChEMBL's own version table has moved between releases."""
        match = re.search(r"chembl_(\d+)", pathlib.Path(self.path).name)
        return f"chembl_{match.group(1)}" if match else "chembl_local"

    def counts(self):
        """Row counts for the tables this backend reads, for a startup
        sanity line -- a truncated or half-extracted download shows up here
        immediately rather than as mysteriously missing edges later."""
        tables = ("activities", "assays", "target_dictionary", "docs",
                  "drug_mechanism", "molecule_dictionary")
        return {t: self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in tables}

    # -- activities ------------------------------------------------------

    # Mirrors exactly the activity fields load_molecule() and
    # chembl_activity_citation() read off a REST record. Anything not listed
    # here is unused downstream; adding a field means adding it here too.
    #
    # target_organism is target_dictionary.organism, NOT assays.assay_organism
    # -- the REST API's activity.target_organism is the organism of the
    # *target* the assay was run against, and the two differ often enough to
    # matter (a human receptor expressed in a rat tissue prep). Verified
    # against the API-built database: this join reproduces caffeine's
    # ADORA2A/2B/1/3 counts (18/17/13/8) exactly.
    _ACTIVITY_SELECT = """
        SELECT
            act.activity_id             AS activity_id,
            act.standard_type           AS standard_type,
            act.standard_relation       AS standard_relation,
            act.standard_value          AS standard_value,
            act.standard_units          AS standard_units,
            act.data_validity_comment   AS data_validity_comment,
            act.activity_comment        AS activity_comment,
            act.pchembl_value           AS pchembl_value,
            a.chembl_id                 AS assay_chembl_id,
            a.description               AS assay_description,
            a.assay_type                AS assay_type,
            td.chembl_id                AS target_chembl_id,
            td.pref_name                AS target_pref_name,
            td.organism                 AS target_organism,
            bao.label                   AS bao_label,
            d.chembl_id                 AS document_chembl_id,
            d.journal                   AS document_journal,
            d.year                      AS document_year
        FROM activities act
        JOIN assays a              ON a.assay_id = act.assay_id
        JOIN target_dictionary td  ON td.tid = a.tid
        JOIN molecule_dictionary m ON m.molregno = act.molregno
        LEFT JOIN bioassay_ontology bao ON bao.bao_id = a.bao_format
        LEFT JOIN docs d           ON d.doc_id = act.doc_id
        WHERE m.chembl_id = ?
          AND td.organism = ?
          AND a.assay_type = ?
    """

    def binding_activities(self, molecule_chembl_id, standard_type,
                           organism="Homo sapiens"):
        """assay_type=B activities of one standard_type.

        Equivalent to GET /activity?molecule_chembl_id=&target_organism=
        &standard_type=&assay_type=B -- see the docstring on
        build_db.fetch_chembl_binding_activities for why B specifically."""
        rows = self.conn.execute(
            self._ACTIVITY_SELECT + " AND act.standard_type = ?"
            " ORDER BY act.activity_id",
            (molecule_chembl_id, organism, "B", standard_type),
        ).fetchall()
        return [dict(r) for r in rows]

    def functional_activities(self, molecule_chembl_id, standard_types,
                              organism="Homo sapiens"):
        """assay_type=F activities restricted to the listed standard_types.

        Equivalent to the same endpoint with assay_type=F and
        standard_type__in=. The organism-based-format exclusion is left to
        the caller, exactly as it is on the API path, so both backends drop
        the same records for the same stated reason."""
        placeholders = ",".join("?" for _ in standard_types)
        rows = self.conn.execute(
            self._ACTIVITY_SELECT
            + f" AND act.standard_type IN ({placeholders})"
            " ORDER BY act.activity_id",
            (molecule_chembl_id, organism, "F", *standard_types),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- targets ---------------------------------------------------------

    def target(self, target_chembl_id):
        """A /target/{id} record, with target_components and their synonyms.

        Cached per handle for the same reason build_db caches the REST
        version: the seed set is built around shared targets, so the same
        ADORA/PDE records are asked for once per molecule. It's ~0.2ms
        uncached rather than ~400ms, but the cache also keeps the two
        backends behaving identically."""
        if target_chembl_id in self._target_cache:
            return self._target_cache[target_chembl_id]

        row = self.conn.execute(
            "SELECT tid, chembl_id, pref_name, organism, target_type, tax_id"
            " FROM target_dictionary WHERE chembl_id = ?",
            (target_chembl_id,),
        ).fetchone()
        if row is None:
            # The API 404s here; returning an empty component list lets the
            # caller's `for component in target.get("target_components", [])`
            # skip it the same way it would an unusable record.
            record = {"target_chembl_id": target_chembl_id, "target_components": []}
            self._target_cache[target_chembl_id] = record
            return record

        components = []
        # compsyn_id / component_id ordering reproduces the order the REST
        # API returns synonyms in, which matters because the caller takes the
        # *first* GENE_SYMBOL per component. Only 36 components in all of
        # ChEMBL 37 carry more than one, and none are in this seed set, but
        # the ordering is free and makes the two paths byte-identical.
        for comp in self.conn.execute(
            "SELECT tc.component_id, cs.accession, cs.description,"
            "       cs.component_type, cs.organism"
            " FROM target_components tc"
            " LEFT JOIN component_sequences cs ON cs.component_id = tc.component_id"
            " WHERE tc.tid = ? ORDER BY tc.component_id",
            (row["tid"],),
        ).fetchall():
            synonyms = self.conn.execute(
                "SELECT component_synonym, syn_type FROM component_synonyms"
                " WHERE component_id = ? ORDER BY compsyn_id",
                (comp["component_id"],),
            ).fetchall()
            components.append({
                "component_id": comp["component_id"],
                # Always present, possibly None: 27 component_sequences rows
                # in ChEMBL 37 have no accession, and the caller indexes this
                # key directly rather than .get()-ing it.
                "accession": comp["accession"],
                "component_description": comp["description"],
                "component_type": comp["component_type"],
                "organism": comp["organism"],
                "target_component_synonyms": [dict(s) for s in synonyms],
            })

        record = {
            "target_chembl_id": row["chembl_id"],
            "pref_name": row["pref_name"],
            "organism": row["organism"],
            "target_type": row["target_type"],
            "tax_id": row["tax_id"],
            "target_components": components,
        }
        self._target_cache[target_chembl_id] = record
        return record

    # -- mechanisms ------------------------------------------------------

    def mechanisms(self, molecule_chembl_id):
        """Curated mechanism-of-action records, with their mechanism_refs.

        target_chembl_id is LEFT JOINed: ChEMBL allows a curated mechanism
        with no assigned target (a phenotypic MoA), and the API returns those
        with a null target_chembl_id. None of the current seeds have one, but
        emitting the null rather than dropping the row keeps this honest to
        what the API does -- filtering is the caller's call."""
        rows = self.conn.execute(
            "SELECT dm.mec_id, dm.action_type, dm.mechanism_of_action,"
            "       dm.mechanism_comment, dm.selectivity_comment,"
            "       dm.direct_interaction, dm.molecular_mechanism,"
            "       dm.disease_efficacy, td.chembl_id AS target_chembl_id"
            " FROM drug_mechanism dm"
            " JOIN molecule_dictionary m ON m.molregno = dm.molregno"
            " LEFT JOIN target_dictionary td ON td.tid = dm.tid"
            " WHERE m.chembl_id = ? ORDER BY dm.mec_id",
            (molecule_chembl_id,),
        ).fetchall()
        out = []
        for row in rows:
            mech = dict(row)
            # (ref_type, ref_id) as *strings*, which is the order the REST
            # API returns them in -- verified against it for CHEMBL113,
            # CHEMBL799 and CHEMBL1355736. Not cosmetic: build_db's
            # chembl_mechanism_citation() takes min() over these by ref_type
            # priority alone, so every PubMed ref ties and iteration order
            # decides which paper gets cited. Ordering by mecref_id instead
            # picked PubMed 3588607 for theophylline's adenosine mechanism
            # where the API picks 12954362 ("3588607" sorts last as a
            # string), the only disagreement in a 133-row provenance diff.
            refs = self.conn.execute(
                "SELECT ref_type, ref_id, ref_url FROM mechanism_refs"
                " WHERE mec_id = ? ORDER BY ref_type, ref_id",
                (row["mec_id"],),
            ).fetchall()
            mech["mechanism_refs"] = [dict(r) for r in refs]
            mech.pop("mec_id")
            mech["molecule_chembl_id"] = molecule_chembl_id
            out.append(mech)
        return out

    # -- documents -------------------------------------------------------

    def document(self, document_chembl_id):
        """A /document/{id} record. Returns {} for an unknown id, matching
        how build_db.fetch_chembl_document degrades on an API error, so a
        missing document downgrades the citation to a ChEMBL record-card
        link instead of aborting the load."""
        row = self.conn.execute(
            "SELECT chembl_id AS document_chembl_id, title, journal, year,"
            "       doi, pubmed_id, volume, issue, first_page, last_page,"
            "       doc_type, authors, abstract"
            " FROM docs WHERE chembl_id = ?",
            (document_chembl_id,),
        ).fetchone()
        return dict(row) if row else {}
