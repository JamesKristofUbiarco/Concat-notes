import unittest

from worker import close_ranges, selected_page_groups, table_markdown


class DocumentWorkerTests(unittest.TestCase):
    def test_outline_ranges_close_at_next_peer(self):
        entries = [
            {"level": 1, "page_start": 1},
            {"level": 2, "page_start": 3},
            {"level": 1, "page_start": 6},
        ]
        close_ranges(entries, 10)
        self.assertEqual([entry["page_end"] for entry in entries], [5, 5, 10])

    def test_table_markdown_preserves_columns(self):
        result = table_markdown([["Name", "Value"], ["A", "1"]])
        self.assertIn("| Name | Value |", result)
        self.assertIn("| A | 1 |", result)

    def test_manual_ranges_form_one_draft_group(self):
        groups = selected_page_groups(
            {"page_count": 30},
            {"mode": "pages", "ranges": [{"start": 2, "end": 3}, {"start": 8, "end": 8}]},
            [],
        )
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["pages"], [2, 3, 8])


if __name__ == "__main__":
    unittest.main()
