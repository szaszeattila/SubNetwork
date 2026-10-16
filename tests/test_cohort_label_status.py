"""D23: reading a DailyMed label's marketing category, and the verdict on a record.

Offline: the pages are fragments shaped like the label pages
scripts/check_dailymed_labels.py reads (an archived isometheptene label, a
current label with no marketing section, DailyMed's page for an unknown id).
"""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import check_dailymed_labels as check  # noqa: E402
from cohort import labels  # noqa: E402


def marketing_table(*rows):
    body = "".join(
        '<tr class="formTableRowAlt">' +
        "".join(f'<td class="formItem">{c}</td>' for c in row) + "</tr>"
        for row in rows)
    return ('<table class="formTablePetite"><tr><td class="formHeadingTitle" colspan="4">'
            'Marketing Information</td></tr><tr>'
            '<th class="formTitle" scope="col">Marketing Category</th>'
            '<th class="formTitle" scope="col">Application Number or Monograph Citation</th>'
            '<th class="formTitle" scope="col">Marketing Start Date</th>'
            '<th class="formTitle" scope="col">Marketing End Date</th></tr>'
            + body + "</table>")


SET = "0844e4a3-5b62-4f1a-9a7c-3c1d7e9a8b21"


def page(title, *tables, labeler="ECI Pharmaceuticals LLC", set_id=SET):
    # A label page names its own set id several times (its links and its
    # download buttons); DailyMed's search page never does.
    return (f"<html><head><title>DailyMed - {title}</title></head><body>"
            f'<a href="/dailymed/getFile.cfm?setid={set_id}&amp;type=zip">SPL</a>'
            '<table class="layout"><tr><td>' + "".join(tables) + "</td></tr></table>"
            '<table class="formTableMorePetite"><tr><td class="formHeadingReg" colspan="4">'
            f'<span class="formHeadingTitle">Labeler - </span>{labeler}\n (962476029)'
            "</td></tr></table></body></html>")


ISOMETHEPTENE = page(
    "ISOMETHEPTENE MUCATE, DICHLORALPHENAZONE AND ACETAMINOPHEN capsule",
    marketing_table(("unapproved drug other", "", "02/15/2011", "03/31/2018")))
KIT = page(
    "A kit",
    marketing_table(("ANDA", "ANDA076543", "01/01/2010", "")),
    marketing_table(("ANDA", "ANDA076543", "01/01/2010", "")),
    marketing_table(("OTC MONOGRAPH FINAL", "part341", "01/01/2010", "")))
NO_SECTION = page("LITHIUM CARBONATE capsule",
                  '<table><tr><th>Marketing Start Date</th></tr></table>')
UNKNOWN_ID = "<html><head><title>DailyMed</title></head><body>search</body></html>"


class ParseTest(unittest.TestCase):
    def test_an_unapproved_label_is_read_with_its_dates_and_labeler(self):
        r = check.parse_label(ISOMETHEPTENE, SET)
        self.assertTrue(r["found"])
        self.assertEqual(r["labeler"], "ECI Pharmaceuticals LLC")
        self.assertEqual(r["marketing"], [{"category": "UNAPPROVED DRUG OTHER",
                                           "application": None,
                                           "start": "02/15/2011", "end": "03/31/2018"}])

    def test_every_product_is_read_once(self):
        cats = [m["category"] for m in check.parse_label(KIT, SET)["marketing"]]
        self.assertEqual(cats, ["ANDA", "OTC MONOGRAPH FINAL"])

    def test_a_label_stating_no_category_has_none(self):
        r = check.parse_label(NO_SECTION, SET)
        self.assertTrue(r["found"])
        self.assertEqual(r["marketing"], [])

    def test_dailymeds_page_for_an_unknown_id_is_not_a_label(self):
        self.assertFalse(check.parse_label(UNKNOWN_ID, SET)["found"])

    def test_a_label_page_with_an_empty_title_is_still_the_label(self):
        # 618 label pages have an empty <title>; reading `found` off the title
        # left 25 records unresolved on labels that parse (D24).
        untitled = page("x", marketing_table(("ANDA", "ANDA070001", "01/01/2010", "")))
        untitled = untitled.replace("<title>DailyMed - x</title>", "<title></title>")
        r = check.parse_label(untitled, SET)
        self.assertTrue(r["found"])
        self.assertIsNone(r["title"])
        self.assertEqual(check.verdict(["a"], {"a": r}), "label")

    def test_a_page_naming_another_set_id_is_not_this_label(self):
        other = page("x", marketing_table(("ANDA", "A", "", "")), set_id="ffff-other")
        self.assertFalse(check.parse_label(other, SET)["found"])


RXNAV = {"ndcPropertyList": {"ndcProperty": [
    {"splSetIdItem": "b25457a9-6237-4ba9-84dd-847b81cbcdae", "propertyConceptList": {
        "propertyConcept": [
            {"propName": "MARKETING_CATEGORY", "propValue": "NDA"},
            {"propName": "NDA", "propValue": "NDA021306"},
            {"propName": "MARKETING_EFFECTIVE_TIME_LOW", "propValue": "20110214"},
            {"propName": "MARKETING_STATUS", "propValue": "ACTIVE"}]}},
    {"splSetIdItem": "b25457a9-6237-4ba9-84dd-847b81cbcdae", "propertyConceptList": {
        "propertyConcept": [
            {"propName": "MARKETING_CATEGORY", "propValue": "NDA"},
            {"propName": "NDA", "propValue": "NDA021306"},
            {"propName": "MARKETING_EFFECTIVE_TIME_LOW", "propValue": "20110214"}]}},
    {"splSetIdItem": "another-set-id", "propertyConceptList": {
        "propertyConcept": [{"propName": "MARKETING_CATEGORY",
                             "propValue": "UNAPPROVED DRUG OTHER"}]}}]}}


class RxNavTest(unittest.TestCase):
    """A set id DailyMed no longer serves, asked of RxNav by the same id (D24)."""

    SID = "b25457a9-6237-4ba9-84dd-847b81cbcdae"

    def test_rows_are_read_for_the_set_id_asked_only(self):
        self.assertEqual(check.parse_rxnav(RXNAV, self.SID),
                         [{"category": "NDA", "application": "NDA021306",
                           "start": "02/14/2011", "end": None}])

    def test_rxnav_answers_only_where_dailymed_did_not(self):
        rows = check.parse_rxnav(RXNAV, self.SID)
        gone = {"found": False, "marketing": [], "rxnav": rows}
        self.assertEqual(check.marketing_rows(gone), (rows, "RxNav"))
        self.assertEqual(check.verdict(["s"], {"s": gone}), "label")
        served = {"found": True, "marketing": [{"category": "ANDA"}], "rxnav": rows}
        self.assertEqual(check.marketing_rows(served)[1], "DailyMed")

    def test_a_label_neither_serves_stays_unresolved(self):
        gone = {"found": False, "marketing": [], "rxnav": []}
        self.assertEqual(check.verdict(["s"], {"s": gone}), "unresolved")
        self.assertEqual(check._label_detail("s", {"s": gone})["unread"], "not served")

    def test_a_served_label_with_no_table_says_so(self):
        old = {"found": True, "marketing": []}
        self.assertEqual(check._label_detail("s", {"s": old})["unread"], "no marketing table")


class FdaDocumentTest(unittest.TestCase):
    def test_an_fda_page_is_an_fda_document_and_a_set_id_is_not(self):
        self.assertTrue(labels.is_fda_document(
            "https://www.fda.gov/vaccines-blood-biologics/aucatzyl"))
        self.assertFalse(labels.is_fda_document("4fef6986-b988-45e4-8c20-b14f0ef1f538"))
        self.assertFalse(labels.is_fda_document("https://www.fda.gov.example.com/x"))


class VerdictTest(unittest.TestCase):
    def labels(self, **pages):
        out = {}
        for set_id, html in pages.items():
            out[set_id] = check.parse_label(html, SET)
        return out

    def test_unapproved_only_when_every_label_is_read_and_none_is_an_approval(self):
        lab = self.labels(a=ISOMETHEPTENE, b=ISOMETHEPTENE)
        self.assertEqual(check.verdict(["a", "b"], lab), "unapproved")

    def test_one_approved_label_is_enough(self):
        lab = self.labels(a=ISOMETHEPTENE, b=KIT)
        self.assertEqual(check.verdict(["a", "b"], lab), "label")

    def test_a_monograph_is_not_an_application(self):
        mono = page("x", marketing_table(("OTC MONOGRAPH NOT FINAL", "part343", "", "")))
        self.assertEqual(check.verdict(["a", "b"], self.labels(a=ISOMETHEPTENE, b=mono)),
                         "monograph")

    def test_a_label_that_cannot_be_read_never_counts_as_unapproved(self):
        for other in (NO_SECTION, UNKNOWN_ID):
            lab = self.labels(a=ISOMETHEPTENE, b=other)
            self.assertEqual(check.verdict(["a", "b"], lab), "unresolved")
        self.assertEqual(check.verdict(["a", "missing"], self.labels(a=ISOMETHEPTENE)),
                         "unresolved")

    def test_an_unknown_category_is_not_guessed(self):
        odd = page("x", marketing_table(("EMERGENCY USE AUTHORIZATION", "", "", "")))
        self.assertIsNone(labels.category_kind("EMERGENCY USE AUTHORIZATION"))
        self.assertEqual(check.verdict(["a"], self.labels(a=odd)), "unresolved")

    def test_categories(self):
        self.assertEqual(labels.category_kind("NDA AUTHORIZED GENERIC"), "application")
        self.assertEqual(labels.category_kind("bla"), "application")
        self.assertEqual(labels.category_kind("OTC MONOGRAPH DRUG"), "monograph")
        self.assertEqual(labels.category_kind("UNAPPROVED HOMEOPATHIC"), "unapproved")
        self.assertEqual(labels.category_kind("EXPORT ONLY"), "unapproved")


if __name__ == "__main__":
    unittest.main()
