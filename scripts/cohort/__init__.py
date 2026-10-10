"""Cohort-1 production pipeline.

The clinical cohort is built from ChEMBL 37 alone (decision D12), against two
versioned policy files in ``config/``: ``cohort1_selection.json`` decides who
is in the catalogue and ``cohort1_evidence.json`` decides what may be drawn,
ranked and counted.

This package replaces ``scripts/build_db.py`` as the producer of the active
artifacts. That script and its six live sources stay in the tree as the
legacy pipeline and the rollback path; nothing here reads from it.
"""
