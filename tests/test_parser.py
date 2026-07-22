import unittest

from src.parser import admissions, faculty_record, parse, profile_links


class ParserTests(unittest.TestCase):
    def test_directory_discovers_profile(self):
        page=parse('<a href="/faculty/jane-doe">Jane Doe</a>', 'https://cs.example.edu/people')
        self.assertEqual(profile_links(page), ['https://cs.example.edu/faculty/jane-doe'])

    def test_positive_admission_is_suspected_until_verified(self):
        evidence,status,confidence=admissions('I am actively recruiting Ph.D. students for Fall 2027.')
        self.assertEqual(status,'suspected_open')
        self.assertIn('Fall 2027',evidence)

    def test_negative_overrides_positive(self):
        _,status,_=admissions('I am not currently accepting PhD students. Old news: recruiting PhD students.')
        self.assertEqual(status,'not_recruiting')

    def test_faculty_profile(self):
        page=parse('<title>Jane Doe | CS</title><h1>Jane Doe</h1><p>Assistant Professor. My research interests: machine learning. I am recruiting PhD students.</p><p>jane@example.edu</p>','https://cs.example.edu/faculty/jane')
        rec=faculty_record(page,'https://cs.example.edu/faculty/jane')
        self.assertEqual(rec['name'],'Jane Doe')
        self.assertEqual(rec['email'],'jane@example.edu')


if __name__ == '__main__': unittest.main()
