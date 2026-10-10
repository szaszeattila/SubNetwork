"""Unit tests for export_graph.py's pure data-handling logic.

Everything here runs offline, against small in-memory fixtures rather than
the real ChEMBL release or a built database - resolve_groups is a pure
function of the shape
{ chembl_id, name, target_type, n_components, wikipedia_url, members }
precisely so it can be tested this way.

Run with: python3 -m unittest discover -s tests
"""

import pathlib
import re
import sqlite3
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import export_graph  # noqa: E402


class MoleculeAliasesTest(unittest.TestCase):
    def test_export_attaches_aliases_by_identity_without_renaming(self):
        with sqlite3.connect(":memory:") as con:
            schema = pathlib.Path(export_graph.DB_PATH).with_name("schema.sql")
            con.executescript(schema.read_text())
            con.executemany(
                "INSERT INTO molecules (name, chembl_id) VALUES (?, ?)",
                [("Dronabinol", "CHEMBL465"), ("Cannabidiol", "CHEMBL190461"),
                 ("Unmapped", "CHEMBL_UNKNOWN")],
            )
            nodes = export_graph.build_graph(con)["nodes"]
        self.assertEqual(nodes[0]["label"], "Dronabinol")
        self.assertIn("THC", nodes[0]["aliases"])
        self.assertIn("CBD", nodes[1]["aliases"])
        self.assertEqual(nodes[2]["aliases"], [])


def complex_(chembl_id, name, target_type, members, n_components=None,
             wikipedia_url=None):
    """A fixture complex record, in resolve_groups' input shape.
    n_components defaults to len(members) - "every component ChEMBL lists
    happens to be present here" - tests that care about the distinction
    (n_components counting components absent from this database) pass it
    explicitly. wikipedia_url defaults to None, same as an assembly with no
    entry (or a deliberate None entry) in COMPLEX_WIKIDATA_ITEMS."""
    return {
        "chembl_id": chembl_id,
        "name": name,
        "target_type": target_type,
        "n_components": n_components if n_components is not None else len(members),
        "wikipedia_url": wikipedia_url,
        "members": list(members),
    }


class ResolveGroupsSubsetTest(unittest.TestCase):
    """The NMDA case this function exists for: a precise sub-complex nested
    inside a larger, poorly-defined complex group."""

    def test_strict_subset_is_absorbed_not_kept_as_its_own_group(self):
        nmda_group = complex_(
            "CHEMBL2094124", "Glutamate [NMDA] receptor",
            "PROTEIN COMPLEX GROUP",
            ["tgt_1", "tgt_2", "tgt_3", "tgt_4", "tgt_5", "tgt_6", "tgt_7"],
        )
        grin1_grin2a = complex_(
            "CHEMBL1907604", "NMDA receptor NR1/NR2A", "PROTEIN COMPLEX",
            ["tgt_1", "tgt_2"],
        )
        groups = export_graph.resolve_groups([nmda_group, grin1_grin2a])

        self.assertEqual([g["chembl_id"] for g in groups], ["CHEMBL2094124"])
        kept = groups[0]
        self.assertEqual(kept["members"], sorted(nmda_group["members"]))

    def test_absorbed_candidate_is_recorded_on_the_keepers_absorbed_list(self):
        nmda_group = complex_(
            "CHEMBL2094124", "Glutamate [NMDA] receptor",
            "PROTEIN COMPLEX GROUP",
            ["tgt_1", "tgt_2", "tgt_3", "tgt_4", "tgt_5", "tgt_6", "tgt_7"],
        )
        grin1_grin2a = complex_(
            "CHEMBL1907604", "NMDA receptor NR1/NR2A", "PROTEIN COMPLEX",
            ["tgt_1", "tgt_2"],
        )
        grin1_grin2b = complex_(
            "CHEMBL1907603", "NMDA receptor NR1/NR2B", "PROTEIN COMPLEX",
            ["tgt_1", "tgt_3"],
        )
        groups = export_graph.resolve_groups([nmda_group, grin1_grin2a, grin1_grin2b])

        self.assertEqual(len(groups), 1)
        absorbed_ids = {a["chembl_id"] for a in groups[0]["absorbed"]}
        self.assertEqual(absorbed_ids, {"CHEMBL1907604", "CHEMBL1907603"})
        # Absorbed records keep their own (precise) member list, not the
        # keeper's - that's the whole point of carrying them along.
        by_id = {a["chembl_id"]: a for a in groups[0]["absorbed"]}
        self.assertEqual(by_id["CHEMBL1907604"]["members"], ["tgt_1", "tgt_2"])
        self.assertEqual(by_id["CHEMBL1907603"]["members"], ["tgt_1", "tgt_3"])


class ResolveGroupsDisjointnessTest(unittest.TestCase):

    def test_no_target_sits_in_two_kept_groups(self):
        a = complex_("CHEMBL_A", "Complex A", "PROTEIN COMPLEX", ["tgt_1", "tgt_2"])
        b = complex_("CHEMBL_B", "Complex B", "PROTEIN COMPLEX", ["tgt_3", "tgt_4"])
        groups = export_graph.resolve_groups([a, b])
        all_members = [m for g in groups for m in g["members"]]
        self.assertEqual(len(all_members), len(set(all_members)))
        self.assertEqual({g["chembl_id"] for g in groups}, {"CHEMBL_A", "CHEMBL_B"})

    def test_partial_overlap_assigns_the_shared_target_to_the_larger_group(self):
        # No partial overlap currently occurs in this database, but the rule
        # must still be total and deterministic rather than undefined. Both
        # candidates keep at least 2 members after the overlap is resolved,
        # so both survive as their own groups - just with the shared target
        # (tgt_3) only in the larger one.
        big = complex_(
            "CHEMBL_BIG", "Big complex", "PROTEIN COMPLEX GROUP",
            ["tgt_1", "tgt_2", "tgt_3"],
        )
        small = complex_(
            "CHEMBL_SMALL", "Small complex", "PROTEIN COMPLEX",
            ["tgt_3", "tgt_4", "tgt_5"],
        )
        groups = export_graph.resolve_groups([big, small])

        by_id = {g["chembl_id"]: g for g in groups}
        self.assertEqual(by_id["CHEMBL_BIG"]["members"], ["tgt_1", "tgt_2", "tgt_3"])
        # tgt_3 was claimed by the larger group first, so the smaller
        # candidate keeps only its unclaimed members.
        self.assertEqual(by_id["CHEMBL_SMALL"]["members"], ["tgt_4", "tgt_5"])

    def test_partial_overlap_result_is_deterministic_regardless_of_input_order(self):
        big = complex_(
            "CHEMBL_BIG", "Big complex", "PROTEIN COMPLEX GROUP",
            ["tgt_1", "tgt_2", "tgt_3"],
        )
        small = complex_(
            "CHEMBL_SMALL", "Small complex", "PROTEIN COMPLEX",
            ["tgt_3", "tgt_4", "tgt_5"],
        )
        forward = export_graph.resolve_groups([big, small])
        backward = export_graph.resolve_groups([small, big])
        self.assertEqual(forward, backward)


class ResolveGroupsDroppedCandidateTest(unittest.TestCase):

    def test_candidate_reduced_below_two_members_is_dropped_entirely(self):
        big = complex_(
            "CHEMBL_BIG", "Big complex", "PROTEIN COMPLEX GROUP",
            ["tgt_1", "tgt_2", "tgt_3"],
        )
        # Every member of this candidate is already claimed by `big` except
        # one, so after the overlap is removed it has fewer than two members
        # left and cannot stand as its own group.
        leftover = complex_(
            "CHEMBL_LEFTOVER", "Leftover complex", "PROTEIN COMPLEX",
            ["tgt_2", "tgt_3"],
        )
        groups = export_graph.resolve_groups([big, leftover])
        self.assertEqual([g["chembl_id"] for g in groups], ["CHEMBL_BIG"])

    def test_a_complex_with_only_one_member_to_begin_with_is_dropped(self):
        lone = complex_("CHEMBL_LONE", "Lone complex", "PROTEIN COMPLEX", ["tgt_1"])
        self.assertEqual(export_graph.resolve_groups([lone]), [])


class ResolveGroupsTierTest(unittest.TestCase):

    def test_tier_maps_from_target_type(self):
        complex_type = complex_("CHEMBL_C", "A complex", "PROTEIN COMPLEX",
                                 ["tgt_1", "tgt_2"])
        group_type = complex_("CHEMBL_G", "A complex group",
                               "PROTEIN COMPLEX GROUP", ["tgt_3", "tgt_4"])
        groups = export_graph.resolve_groups([complex_type, group_type])
        tiers = {g["chembl_id"]: g["tier"] for g in groups}
        self.assertEqual(tiers["CHEMBL_C"], "complex")
        self.assertEqual(tiers["CHEMBL_G"], "complex_group")


class ResolveGroupsWikipediaUrlTest(unittest.TestCase):
    """target_complexes.wikipedia_url is a passthrough - resolve_groups
    doesn't derive or validate it, it just has to survive being carried from
    a raw ChEMBL record onto whichever kept/absorbed record it ends up on,
    the same way chembl_id, name and target_type already do."""

    def test_wikipedia_url_carried_onto_kept_group(self):
        a = complex_("CHEMBL_A", "Complex A", "PROTEIN COMPLEX",
                      ["tgt_1", "tgt_2"], wikipedia_url="https://en.wikipedia.org/wiki/A")
        groups = export_graph.resolve_groups([a])
        self.assertEqual(groups[0]["wikipedia_url"],
                          "https://en.wikipedia.org/wiki/A")

    def test_wikipedia_url_none_when_unmapped(self):
        a = complex_("CHEMBL_A", "Complex A", "PROTEIN COMPLEX", ["tgt_1", "tgt_2"])
        groups = export_graph.resolve_groups([a])
        self.assertIsNone(groups[0]["wikipedia_url"])

    def test_wikipedia_url_carried_onto_absorbed_entry(self):
        # Mirrors the real NMDA case: the keeper and the absorbed sub-complex
        # both name the same receptor, so both carry the same Wikidata
        # article - but resolve_groups must carry each candidate's own
        # value, not silently copy the keeper's onto everything absorbed.
        nmda_group = complex_(
            "CHEMBL2094124", "Glutamate [NMDA] receptor",
            "PROTEIN COMPLEX GROUP",
            ["tgt_1", "tgt_2", "tgt_3", "tgt_4", "tgt_5", "tgt_6", "tgt_7"],
            wikipedia_url="https://en.wikipedia.org/wiki/NMDA_receptor",
        )
        grin1_grin2a = complex_(
            "CHEMBL1907604", "NMDA receptor NR1/NR2A", "PROTEIN COMPLEX",
            ["tgt_1", "tgt_2"],
            wikipedia_url="https://en.wikipedia.org/wiki/NMDA_receptor",
        )
        groups = export_graph.resolve_groups([nmda_group, grin1_grin2a])

        self.assertEqual(groups[0]["wikipedia_url"],
                          "https://en.wikipedia.org/wiki/NMDA_receptor")
        absorbed = groups[0]["absorbed"][0]
        self.assertEqual(absorbed["chembl_id"], "CHEMBL1907604")
        self.assertEqual(absorbed["wikipedia_url"],
                          "https://en.wikipedia.org/wiki/NMDA_receptor")


class ResolveGroupsOrderingTest(unittest.TestCase):

    def test_kept_groups_sorted_by_member_count_desc_then_chembl_id(self):
        a = complex_("CHEMBL_A", "A", "PROTEIN COMPLEX", ["tgt_1", "tgt_2"])
        b = complex_("CHEMBL_B", "B", "PROTEIN COMPLEX",
                     ["tgt_3", "tgt_4", "tgt_5"])
        c = complex_("CHEMBL_C", "C", "PROTEIN COMPLEX", ["tgt_6", "tgt_7"])
        groups = export_graph.resolve_groups([a, b, c])
        self.assertEqual([g["chembl_id"] for g in groups],
                         ["CHEMBL_B", "CHEMBL_A", "CHEMBL_C"])


if __name__ == "__main__":
    unittest.main()
