from __future__ import annotations

import unittest

from src.search import _host, _identity_matches, _identity_score, _same_site


class SchoolOwnershipTests(unittest.TestCase):
    def test_host_normalisation(self) -> None:
        self.assertEqual(_host("https://www.cs.princeton.edu/people"), "cs.princeton.edu")
        self.assertEqual(_host("stanford.edu"), "stanford.edu")

    def test_subdomain_is_accepted(self) -> None:
        self.assertTrue(_same_site("https://cs.stanford.edu/people", "stanford.edu"))

    def test_other_school_is_rejected(self) -> None:
        self.assertFalse(_same_site("https://cs.princeton.edu/people", "stanford.edu"))
        self.assertFalse(_same_site("https://stanford.edu.example.com", "stanford.edu"))

    def test_school_identity_distinguishes_results(self) -> None:
        princeton = {
            "title": "Princeton University Computer Science",
            "url": "https://www.cs.princeton.edu/people/faculty",
            "content": "Faculty directory",
        }
        self.assertGreater(_identity_score(princeton, "Princeton University"), 0)
        self.assertEqual(_identity_score(princeton, "Stanford University"), 0)

    def test_shared_domain_still_requires_campus_identity(self) -> None:
        new_brunswick = {
            "title": "Rutgers University–New Brunswick Computer Science",
            "url": "https://www.cs.rutgers.edu/people/faculty",
            "content": "New Brunswick faculty",
        }
        self.assertTrue(_identity_matches(new_brunswick, "Rutgers University New Brunswick"))
        self.assertFalse(_identity_matches(new_brunswick, "Rutgers University Newark"))


if __name__ == "__main__":
    unittest.main()
