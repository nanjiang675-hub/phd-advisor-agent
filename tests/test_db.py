from __future__ import annotations

import unittest
from pathlib import Path

import src.db as database


class DatabaseBootstrapTests(unittest.TestCase):
    def test_all_ranked_schools_receive_official_domains(self) -> None:
        original_path = database.DB_PATH
        test_path = database.ROOT / "database" / "test-official-domains.sqlite"
        test_path.unlink(missing_ok=True)
        database.DB_PATH = test_path
        try:
            database.init_db(load_inputs=True)
            with database.connect() as db:
                row = db.execute(
                    "SELECT COUNT(*) total, "
                    "SUM(CASE WHEN website IS NOT NULL AND website<>'' THEN 1 ELSE 0 END) domains "
                    "FROM schools"
                ).fetchone()
                self.assertEqual(row["total"], row["domains"])
                stanford = db.execute(
                    "SELECT website FROM schools WHERE name='Stanford University'"
                ).fetchone()
                self.assertEqual(stanford["website"], "https://stanford.edu")
        finally:
            database.DB_PATH = original_path
            test_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
