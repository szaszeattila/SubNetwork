"""Generate the figures CLAUDE.md's ``## Status`` section quotes.

Every number in that section used to be typed in by hand against a report that
had been run in another terminal, and by 2026-09-17 four of them had drifted:
the build date named a rebuild two builds old, a target's accession count said
two where the database holds three, both test totals were short, and the
startup payload was quoted at a size the file had outgrown. The figures the
pipeline *computes* were all exact. The ones a human transcribed were not.

So the section is no longer transcribed. The text between the markers below is
written from the active database, the exported payload and the test suites
themselves, and :func:`check` fails when what is in the file disagrees with
what those sources say now. A stale figure is a failing test rather than
something review has to catch.

    python3 scripts/cohort_report.py --write-status   # refresh the block
    python3 scripts/cohort_report.py --check-status   # fail if it is stale

What this owns is the numbers and the sentences carrying them. Everything
outside the markers is hand-written prose and is never touched -- that prose is
the most valuable thing in the repository, and a generator that reformatted it
would be a worse problem than the drift it fixes.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sqlite3
import subprocess
import textwrap

from . import common

# CLAUDE.md is wrapped by hand at a little under 80 columns. The generated
# paragraphs are wrapped to match, so a refresh never shows up as a reflow of
# every line in the block.
WRAP = 78

DOC = common.ROOT / "CLAUDE.md"
GRAPH_DATA = common.VIZ / "graph.data.js"
GTOPDB_DATA = common.VIZ / "gtopdb.data.js"
EVIDENCE_DIR = common.VIZ / "evidence"
TESTS = common.ROOT / "tests"

BEGIN = "<!-- BEGIN GENERATED: %s -->"
END = "<!-- END GENERATED: %s -->"

NOTE = (
    "<!-- Written by `python3 scripts/cohort_report.py --write-status`. "
    "Do not edit by hand: `--check-status` fails when this block and the "
    "active build disagree, and a rewrite discards whatever was typed here. "
    "The prose outside the markers is hand-written and is never touched. -->"
)


class StatusError(RuntimeError):
    """A figure could not be measured. Always fatal: never write a zero."""


def _n(value) -> str:
    """Thousands separators, the way the prose already writes them."""
    return f"{value:,}"


def _mb(n_bytes: int) -> str:
    """Megabytes the way this document has always counted them: 1 MB = 1e6 B.

    Two decimals below 10 MB and one above, which is what the hand-written
    figures used ("4.39 MB" for the payload, "71.7 MB" for the shards).
    """
    mb = n_bytes / 1e6
    return f"{mb:.2f} MB" if mb < 10 else f"{mb:.1f} MB"


def _para(text: str) -> str:
    return textwrap.fill(
        " ".join(text.split()),
        width=WRAP,
        break_long_words=False,
        break_on_hyphens=False,
    )


# --------------------------------------------------------------------------
# measuring


def _one(db, sql, *params):
    row = db.execute(sql, params).fetchone()
    if row is None:
        raise StatusError(f"query returned no row: {sql}")
    return row[0]


def db_figures(db_path: pathlib.Path) -> dict:
    """Everything the active cohort database can answer for itself."""
    if not db_path.exists():
        raise StatusError(
            f"no cohort database at {db_path}. Build one with "
            f"`python3 scripts/build_cohort.py` before refreshing the status "
            f"block: this never writes figures it could not measure."
        )
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        manifest = {r["key"]: r["value"]
                    for r in db.execute("SELECT key, value FROM build_manifest")}
        if not manifest.get("built_at"):
            raise StatusError(f"{db_path} has no built_at in build_manifest")

        selection = json.loads(manifest.get("selection_policy", "{}"))
        evidence = json.loads(manifest.get("evidence_policy", "{}"))

        routes = {r["admission_reason"]: r["n"] for r in db.execute(
            "SELECT admission_reason, COUNT(*) n FROM molecules GROUP BY 1")}
        status = {r["evidence_status"]: r["n"] for r in db.execute(
            "SELECT evidence_status, COUNT(*) n FROM molecules GROUP BY 1")}
        supported = {(r["curated_support"], r["multiple_study_support"]): r["n"]
                     for r in db.execute(
                         "SELECT curated_support, multiple_study_support, COUNT(*) n"
                         " FROM claims WHERE basis='human_direct' AND tier='supported'"
                         " GROUP BY 1,2")}
        scan = {r["reason"]: r["n_rows"] for r in db.execute(
            "SELECT reason, n_rows FROM exclusion_summary")}

        fig = {
            "built_at": manifest["built_at"],
            "built_date": manifest["built_at"][:10],
            "chembl_release": manifest.get("chembl_release"),
            "selection_policy": selection.get("policy_id"),
            "selection_version": selection.get("version"),
            "evidence_policy": evidence.get("policy_id"),
            "evidence_version": evidence.get("version"),

            "molecules": _one(db, "SELECT COUNT(*) FROM molecules"),
            "targets": _one(db, "SELECT COUNT(*) FROM targets"),
            "claims": _one(db, "SELECT COUNT(*) FROM claims"),
            "observations": _one(db, "SELECT COUNT(*) FROM observations"),

            "in_cohort": _one(db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=1"),
            "outside_cohort": _one(db, "SELECT COUNT(*) FROM molecules WHERE in_cohort=0"),
            "route_atc_n": routes.get("route_atc_n", 0),
            "route_indication": routes.get("route_indication", 0),
            "route_both": routes.get("both_routes", 0),
            "seeds": _one(db, "SELECT COUNT(*) FROM molecules WHERE is_seed=1"),
            "seeds_admitted": _one(
                db, "SELECT COUNT(*) FROM molecules WHERE is_seed=1 AND in_cohort=1"),
            "seed_only": routes.get("seed_only", 0),
            "listed_only": routes.get("listed_only", 0),

            "supported_claims": sum(supported.values()),
            "supported_curated": supported.get((1, 0), 0),
            "supported_replicated": supported.get((0, 1), 0),
            "supported_both": supported.get((1, 1), 0),
            "supported_pairs": _one(
                db, "SELECT COUNT(*) FROM (SELECT DISTINCT parent_molregno,"
                    " target_chembl_id FROM claims WHERE basis='human_direct'"
                    " AND tier='supported')"),

            "has_supported": status.get("has_supported", 0),
            "has_preliminary": status.get("has_preliminary", 0),
            "broader_only": status.get("has_supported_broader_only", 0),
            "limited_only": status.get("limited_only", 0),
            "no_evidence": status.get("no_eligible_evidence", 0),

            "studies": _one(db, "SELECT COUNT(DISTINCT study_key) FROM observations"
                                " WHERE study_key IS NOT NULL"),
            "counted": _one(db, "SELECT COUNT(*) FROM observations WHERE counted=1"),
            "bounds": _one(db, "SELECT COUNT(*) FROM observations"
                               " WHERE value_status='bound'"),
            "conditional": _one(db, "SELECT COUNT(*) FROM observations"
                                    " WHERE value_status='conditional'"),
            "organism_format": scan.get("organism_based_format", 0),
            "documented_exclusion": scan.get("documented_exclusion", 0),
            "scanned": scan.get("scanned", 0),

            "checks_total": _one(db, "SELECT COUNT(*) FROM validation"),
            "checks_passed": _one(
                db, "SELECT COUNT(*) FROM validation WHERE result='PASS'"),

            "wiki_molecules": _one(
                db, "SELECT COUNT(*) FROM molecules WHERE wikipedia_url IS NOT NULL"),
            "single_component": _one(
                db, "SELECT COUNT(*) FROM targets WHERE n_components=1"),
            "wiki_targets": _one(
                db, "SELECT COUNT(*) FROM targets"
                    " WHERE n_components=1 AND wikipedia_url IS NOT NULL"),
            "multi_component": _one(
                db, "SELECT COUNT(*) FROM targets WHERE n_components>1"),
            "no_component": _one(
                db, "SELECT COUNT(*) FROM targets WHERE COALESCE(n_components,0)=0"),
            "multi_single_protein": _one(
                db, "SELECT COUNT(*) FROM targets"
                    " WHERE target_type='SINGLE PROTEIN' AND n_components>1"),
            "multi_single_protein_accessions": _one(
                db, "SELECT COALESCE(MAX(n_components),0) FROM targets"
                    " WHERE target_type='SINGLE PROTEIN' AND n_components>1"),
        }
        # Structure-class links arrived after the other two; a database
        # backfilled before them has no table, and the sentence is left out.
        if _one(db, "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                    " AND name IN ('class_labels', 'class_wikipedia')") == 2:
            fig["struct_classes"] = _one(
                db, "SELECT COUNT(*) FROM class_labels WHERE source='mesh_struct'")
            for route in ("item", "category"):
                fig["wiki_classes_" + route] = _one(
                    db, "SELECT COUNT(*) FROM class_wikipedia w JOIN class_labels l"
                        " USING (source, code) WHERE w.source='mesh_struct'"
                        " AND w.route=?", route)
    finally:
        db.close()

    if fig["checks_passed"] != fig["checks_total"]:
        raise StatusError(
            f"{fig['checks_total'] - fig['checks_passed']} of "
            f"{fig['checks_total']} build checks did not pass in {db_path}. "
            f"Refusing to write a status block describing a failed build."
        )
    return fig


def export_figures() -> dict:
    """Sizes of what the page actually loads, off the exported files."""
    for path in (GRAPH_DATA, GTOPDB_DATA):
        if not path.exists():
            raise StatusError(
                f"no export at {path}. Run "
                f"`python3 scripts/export_cohort.py` before refreshing the status "
                f"block."
            )
    if not EVIDENCE_DIR.is_dir():
        raise StatusError(f"no evidence shards at {EVIDENCE_DIR}")
    shards = sorted(EVIDENCE_DIR.glob("*.js"))
    if not shards:
        raise StatusError(f"no evidence shards under {EVIDENCE_DIR}")
    return {
        "payload_bytes": GRAPH_DATA.stat().st_size,
        "gtopdb_bytes": GTOPDB_DATA.stat().st_size,
        "shard_bytes": sum(p.stat().st_size for p in shards),
        "shard_count": len(shards),
    }


def python_test_count() -> int:
    """Count the pipeline suite the way its own runner discovers it.

    Loading is not running, so this is safe to call from inside a test: the
    modules are already imported and the loader just walks them again.
    """
    import unittest

    loader = unittest.TestLoader()
    suite = loader.discover(str(TESTS))
    if loader.errors:
        raise StatusError(
            "test discovery reported errors; refusing to record a count: "
            + "; ".join(str(e) for e in loader.errors))
    return suite.countTestCases()


_NODE_TOTALS = re.compile(r"^# (tests|pass|fail) (\d+)$", re.M)


def node_test_count(pattern: str) -> int:
    """Run a node suite and return how many tests it ran.

    The count is read off the runner's own summary rather than counted out of
    the source, and a suite with a failure raises instead of reporting a
    number: "404 tests" beside three failures would be a worse claim than no
    number at all.
    """
    node = shutil.which("node")
    if node is None:
        raise StatusError("node is not on PATH, so the viewer suites cannot be counted")
    proc = subprocess.run(
        [node, "--test", pattern],
        cwd=str(common.ROOT), capture_output=True, text=True,
    )
    totals = {k: int(v) for k, v in _NODE_TOTALS.findall(proc.stdout)}
    if "tests" not in totals:
        raise StatusError(
            f"could not read a test total out of `node --test {pattern}`:\n"
            + (proc.stdout or proc.stderr)[-2000:])
    if totals.get("fail", 0):
        raise StatusError(
            f"{totals['fail']} of {totals['tests']} tests failed in "
            f"`node --test {pattern}`. Refusing to record a count for a "
            f"failing suite.")
    return totals["tests"]


def suite_figures() -> dict:
    # A glob, so a viewer suite split into its own file (the GtoPdb one) is
    # counted rather than silently left out of the figure.
    cohort = node_test_count("tests/cohort_viewer*.test.mjs")
    legacy = node_test_count("tests/legacy_*.test.mjs")
    # The harness suite is counted separately and named separately, because it
    # is not a viewer test: it grades the ranking against an answer key rather
    # than asserting what the page draws. Counting it is not optional, though.
    # `node --test "tests/*.test.mjs"` is the command CLAUDE.md tells a reader
    # to run, and it picks this file up -- so a total here that left it out
    # would be a figure the documented command contradicts, which is precisely
    # the drift this module exists to stop.
    harness = node_test_count("tests/similarity_harness.test.mjs")
    return {
        "python_tests": python_test_count(),
        "viewer_cohort_tests": cohort,
        "viewer_legacy_tests": legacy,
        "harness_tests": harness,
        "node_tests": cohort + legacy + harness,
        "viewer_tests": cohort + legacy,
    }


def harness_figures() -> dict:
    """The similarity ranking's grade, from the harness's own JSON.

    Read out of ``analysis/similarity_harness/evaluate.mjs`` rather than
    recomputed here, for the reason the harness itself calls ``sharedTargets``
    instead of reimplementing it: a second implementation of the grade would
    drift from the first, and the figure quoted would stop being the figure the
    tool reports.
    """
    node = shutil.which("node")
    if node is None:
        raise StatusError("node is not on PATH, so the similarity grade cannot be read")
    if not GRAPH_DATA.exists():
        raise StatusError(
            f"{GRAPH_DATA.name} is missing, so the similarity ranking cannot "
            "be graded. Run `python3 scripts/export_cohort.py` first.")
    proc = subprocess.run(
        [node, "analysis/similarity_harness/evaluate.mjs", "--json"],
        cwd=str(common.ROOT), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise StatusError(
            "the similarity harness failed:\n" + (proc.stderr or proc.stdout)[-2000:])
    try:
        got = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise StatusError(
            f"the similarity harness printed no JSON ({exc}):\n"
            + (proc.stdout or proc.stderr)[-2000:]) from exc
    return {
        "sim_labelled": got["labelled"],
        "sim_classes": got["classes"],
        "sim_scoreable": got["scoreable"],
        "sim_unanswerable": got["unanswerable"],
        "sim_top1": got["top1"],
        "sim_mrr": got["mrr"],
    }


# --------------------------------------------------------------------------
# rendering


def render_status(fig: dict) -> str:
    """The ``## Status`` figures, in the voice the section already had."""

    # Two Supported routes that a claim could in principle carry at once. The
    # prose has always said no claim carries both, which is a measured fact
    # rather than a rule -- so it is written only while it is true.
    if fig["supported_both"]:
        routes = (
            f"{_n(fig['supported_replicated'])} by replication across "
            f"publications, {_n(fig['supported_curated'])} by curated mechanism "
            f"and {_n(fig['supported_both'])} by both")
    else:
        routes = (
            f"{_n(fig['supported_replicated'])} by replication across "
            f"publications and {_n(fig['supported_curated'])} by curated "
            f"mechanism, with no claim carrying both")

    # Multi-component targets cannot take a Wikipedia link (invariant 15), and
    # the odd one out is a target ChEMBL labels SINGLE PROTEIN while listing
    # several accessions against it. Say how many accessions rather than
    # asserting a number that has already been wrong once.
    if fig["multi_single_protein"] == 1:
        odd = (f", plus one ChEMBL-labelled SINGLE PROTEIN carrying "
               f"{_n(fig['multi_single_protein_accessions'])} accessions")
    elif fig["multi_single_protein"]:
        odd = (f", plus {_n(fig['multi_single_protein'])} ChEMBL-labelled "
               f"SINGLE PROTEIN records carrying several accessions each")
    else:
        odd = ""

    classes = ""
    if "struct_classes" in fig:
        classes = (
            f" Of the {_n(fig['struct_classes'])} MeSH structure classes, "
            f"**{_n(fig['wiki_classes_item'] + fig['wiki_classes_category'])}** "
            f"link one too, in the `class_wikipedia` table: "
            f"{_n(fig['wiki_classes_item'])} through the Wikidata item carrying "
            f"the descriptor, and {_n(fig['wiki_classes_category'])} whose item "
            f"has no article through the main article its English category "
            f"declares (Xanthines to *Xanthine*).")

    no_accession = ""
    if fig["no_component"]:
        no_accession = (
            f" The {_n(fig['no_component'])} targets ChEMBL lists with no "
            f"accession at all are left NULL for the same reason.")

    paragraphs = [
        _para(f"""
            Pipeline and viewer both working. Current database,
            `db/cohort1.db`, built {fig['built_date']} against the
            `{fig['chembl_release']}` bulk release under selection policy
            `{fig['selection_policy']} v{fig['selection_version']}` and
            evidence policy
            `{fig['evidence_policy']} v{fig['evidence_version']}`:
        """),

        f"**{_n(fig['molecules'])} catalogue entries · "
        f"{_n(fig['targets'])} targets · "
        f"{_n(fig['claims'])} claims · "
        f"{_n(fig['observations'])} observations**",

        _para(f"""
            {_n(fig['in_cohort'])} are cohort-1 members
            ({_n(fig['route_atc_n'])} by ATC N alone,
            {_n(fig['route_indication'])} by a qualifying indication alone,
            {_n(fig['route_both'])} by both); outside it, with their
            exclusion reasons, are {_n(fig['seed_only'])} seed molecules
            and {_n(fig['listed_only'])} molecules entered because a public
            list names them (D25–D27). {_n(fig['seeds_admitted'])} of the
            {_n(fig['seeds'])} seeds are admitted.
            {_n(fig['supported_claims'])} claims are Supported in the direct
            human basis — {routes} — over {_n(fig['supported_pairs'])}
            distinct molecule–target pairs. {_n(fig['has_supported'])} entries
            have a Supported claim, {_n(fig['has_preliminary'])} only
            Preliminary, {_n(fig['broader_only'])} only in the broader
            assignment layer, {_n(fig['limited_only'])} only retained
            observations, and {_n(fig['no_evidence'])} have no eligible
            evidence in ChEMBL {fig['chembl_release'].split('_')[-1]} at all.
            All of them stay searchable.
        """),

        _para(f"""
            Behind those claims sit {_n(fig['observations'])} retained
            observations resolving to {_n(fig['studies'])} distinct studies, of
            which {_n(fig['counted'])} rows are counted into a median.
            {_n(fig['bounds'])} bounds are kept with their relations and out of
            every median; {_n(fig['conditional'])} conditional mass-basis
            conversions are kept and counted into nothing.
            {_n(fig['organism_format'])} organism-format rows and
            {_n(fig['documented_exclusion'])} documented known-bad records are
            excluded with their reasons, and the exclusion accounting
            reconciles exactly to the {_n(fig['scanned'])} activity rows
            scanned. All {_n(fig['checks_total'])} build checks pass.
        """),

        _para(f"""
            What the page loads is {_mb(fig['payload_bytes'])} of startup
            payload in `viz/graph.data.js` and {_mb(fig['gtopdb_bytes'])} in
            `viz/gtopdb.data.js`, GtoPdb's part, kept apart for its licence;
            and {_mb(fig['shard_bytes'])} of
            per-molecule evidence shards across {_n(fig['shard_count'])} files
            under `viz/evidence/`, fetched one at a time on demand.
        """),

        _para(f"""
            `molecules.wikipedia_url` and `targets.wikipedia_url` are
            backfilled by `scripts/resolve_cohort_wikipedia.py` after a build:
            **{_n(fig['wiki_molecules'])} of {_n(fig['molecules'])} molecules**
            and **{_n(fig['wiki_targets'])} of {_n(fig['single_component'])}
            single-component targets** link to an English Wikipedia article.
            The other {_n(fig['multi_component'])} multi-component targets —
            every PROTEIN COMPLEX, PROTEIN COMPLEX GROUP and PROTEIN
            FAMILY{odd} — are left NULL rather than resolved to a
            guess.{no_accession}{classes}
        """),

        _para(f"""
            The pipeline suite is {_n(fig['python_tests'])} tests and the node
            suites are {_n(fig['node_tests'])}
            ({_n(fig['viewer_cohort_tests'])} cohort viewer,
            {_n(fig['viewer_legacy_tests'])} legacy viewer,
            {_n(fig['harness_tests'])} similarity harness).
        """),

        _para(f"""
            The similarity ranking is graded by
            `analysis/similarity_harness/evaluate.mjs` against ATC level-4
            classes, which are the WHO's own grouping of drugs by how they
            work and are read from `molecules.atc_level5` rather than written
            here: **top-1 {fig['sim_top1'] * 100:.1f}% and MRR
            {fig['sim_mrr']:.4f}** over {_n(fig['sim_scoreable'])} of
            {_n(fig['sim_labelled'])} labelled molecules in
            {_n(fig['sim_classes'])} classes. The other
            {_n(fig['sim_unanswerable'])} have no same-class peer anywhere in
            their list, which is a fact about ChEMBL's coverage rather than
            about the ranking, and is kept out of the rates for that reason. It
            is a proxy and not ground truth — ATC groups partly by mechanism,
            so the measure flatters any weighting term that rewards curation.
        """),
    ]
    return "\n\n".join(paragraphs)


# --------------------------------------------------------------------------
# reading and writing the block


def _block_re(name: str) -> re.Pattern:
    # The body runs from the line after BEGIN up to the line END sits on, and
    # is allowed to be empty: a pair of adjacent markers is how the block is
    # first put into the document, and hitting a "no block here" error at that
    # point would be the generator refusing to do the one thing it is for.
    return re.compile(
        re.escape(BEGIN % name) + r"\n(?P<body>.*?)" + re.escape(END % name),
        re.S,
    )


def current_block(text: str, name: str = "cohort-status") -> str:
    match = _block_re(name).search(text)
    if match is None:
        raise StatusError(
            f"no `{BEGIN % name}` … `{END % name}` block in the document. "
            f"The markers delimit the generated region and cannot be "
            f"regenerated from anything, so they have to be put back by hand."
        )
    return match.group("body").strip("\n")


def replace_block(text: str, body: str, name: str = "cohort-status") -> str:
    """Swap the block's contents, leaving every byte outside the markers alone."""
    match = _block_re(name).search(text)
    if match is None:
        raise StatusError(f"no `{BEGIN % name}` block in the document")
    return text[:match.start("body")] + body + "\n" + text[match.end("body"):]


def rendered(db_path=None) -> str:
    fig = db_figures(db_path or common.COHORT_DB)
    fig.update(export_figures())
    fig.update(suite_figures())
    fig.update(harness_figures())
    return NOTE + "\n\n" + render_status(fig)


def write(doc: pathlib.Path = None, db_path=None) -> int:
    doc = doc or DOC
    text = doc.read_text(encoding="utf-8")
    body = rendered(db_path)
    updated = replace_block(text, body)
    if updated == text:
        common.log(f"{doc.name} status block already up to date")
        return 0
    doc.write_text(updated, encoding="utf-8")
    common.log(f"{doc.name} status block rewritten")
    return 0


def check(doc: pathlib.Path = None, db_path=None) -> int:
    """Exit non-zero when the block disagrees with the active build."""
    doc = doc or DOC
    text = doc.read_text(encoding="utf-8")
    want = rendered(db_path)
    got = current_block(text)
    if got == want:
        common.log(f"{doc.name} status block is up to date")
        return 0

    import difflib
    diff = "\n".join(difflib.unified_diff(
        got.splitlines(), want.splitlines(),
        fromfile=f"{doc.name} (as written)", tofile="measured now", lineterm=""))
    common.log(
        f"{doc.name} status block is STALE. Refresh it with\n"
        f"    python3 scripts/cohort_report.py --write-status\n\n{diff}")
    return 1
