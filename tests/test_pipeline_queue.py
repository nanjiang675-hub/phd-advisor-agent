from __future__ import annotations

import unittest

from src.pipeline import _fair_page_sample


class PipelineQueueTests(unittest.TestCase):
    def test_page_budget_is_split_between_directories_and_profiles(self) -> None:
        page_limit = 30
        directory_limit = max(1, page_limit // 2)
        profile_limit = page_limit - directory_limit

        self.assertEqual(directory_limit, 15)
        self.assertEqual(profile_limit, 15)
        self.assertEqual(directory_limit + profile_limit, page_limit)

    def test_pages_are_sampled_round_robin_across_schools(self) -> None:
        rows = [
            {"id": 1, "school_id": 1},
            {"id": 2, "school_id": 1},
            {"id": 3, "school_id": 1},
            {"id": 4, "school_id": 2},
            {"id": 5, "school_id": 2},
            {"id": 6, "school_id": 3},
        ]

        selected = _fair_page_sample(rows, 6)

        self.assertEqual(
            [row["school_id"] for row in selected],
            [1, 2, 3, 1, 2, 1],
        )


if __name__ == "__main__":
    unittest.main()
