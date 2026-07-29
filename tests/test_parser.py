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

    def test_script_and_style_are_ignored(self):
        page = parse(
            "<title>Jane Doe | CS</title><style>body{color:red}</style>"
            "<script>window.bad=true</script><h1>Jane Doe</h1>"
            "<p>Professor. Research interests include machine learning.</p>",
            "https://cs.example.edu/faculty/jane",
        )
        self.assertNotIn("window.bad", page["text"])
        self.assertNotIn("color:red", page["text"])

    def test_alumni_news_is_not_faculty(self):
        page = parse(
            "<title>Alumni News</title><h1>Alumni News</h1>"
            "<p>Professor stories and research news.</p>",
            "https://cs.example.edu/news/alumni",
        )
        self.assertIsNone(
            faculty_record(page, "https://cs.example.edu/news/alumni")
        )

    def test_profile_without_research_evidence_is_rejected(self):
        page = parse(
            "<title>John Smith | CS</title><h1>John Smith</h1>"
            "<p>Professor. Alumni news, events, and department updates.</p>",
            "https://cs.example.edu/faculty/john-smith",
        )
        self.assertIsNone(
            faculty_record(page, "https://cs.example.edu/faculty/john-smith")
        )


if __name__ == '__main__': unittest.main()
