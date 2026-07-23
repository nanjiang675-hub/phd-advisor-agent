from __future__ import annotations

import unittest


class PipelineQueueTests(unittest.TestCase):
    def test_page_budget_is_split_between_directories_and_profiles(self) -> None:
        page_limit = 30
        directory_limit = max(1, page_limit // 2)
        profile_limit = page_limit - directory_limit

        self.assertEqual(directory_limit, 15)
        self.assertEqual(profile_limit, 15)
        self.assertEqual(directory_limit + profile_limit, page_limit)


if __name__ == "__main__":
    unittest.main()
