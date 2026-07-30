import unittest

from src.parser import (
    admissions,
    faculty_record,
    is_person_name,
    is_valid_faculty_output,
    parse,
    profile_url_matches_name,
    profile_links,
)


class ParserTests(unittest.TestCase):
    def test_generic_directory_headings_are_not_people(self):
        generic_names = [
            "Computational Biology",
            "Faculty Achievements",
            "Affiliated Faculty",
            "Department Directory",
            "In Memoriam",
            "Administrative Staff",
            "Graduate Students",
            "Primary Faculty",
            "Secondary Faculty",
            "Graduate Alumni",
            "Alumni News",
            "Faculty Directory",
            "Faculty Openings",
            "People Advisory Board",
            "CIS Open Faculty Positions",
            "Our Faculty",
            "Faculty Resources",
        ]
        for name in generic_names:
            with self.subTest(name=name):
                self.assertFalse(is_person_name(name))

    def test_profile_url_must_match_person_name(self):
        self.assertTrue(profile_url_matches_name(
            "Jane Smith", "https://cs.example.edu/people/jane-smith"
        ))
        self.assertTrue(profile_url_matches_name(
            "Abhishek Jain", "https://cs.jhu.edu/faculty/abhishek-jain/"
        ))
        self.assertFalse(profile_url_matches_name(
            "Jane Smith", "https://cs.example.edu/faculty-directory/"
        ))

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
        page=parse('<title>Jane Doe | CS</title><h1>Jane Doe</h1><p>Assistant Professor. My research interests: machine learning. I am recruiting PhD students.</p><p>jane@example.edu</p>','https://cs.example.edu/faculty/jane-doe')
        rec=faculty_record(page,'https://cs.example.edu/faculty/jane-doe')
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

    def test_alumni_news_is_rejected_even_on_profile_path(self):
        page = parse(
            "<title>Alumni News | Computer Science</title>"
            "<h1>Alumni News</h1><p>Professor. Research interests include "
            "machine learning systems for scientific applications.</p>",
            "https://cs.example.edu/people/alumni-news",
        )
        self.assertIsNone(
            faculty_record(page, "https://cs.example.edu/people/alumni-news")
        )

    def test_valid_name_with_page_suffix_is_accepted(self):
        page = parse(
            "<title>Jane Q. Smith | Computer Science</title>"
            "<h1>Jane Q. Smith</h1><p>Assistant Professor. "
            "Research interests include robust machine learning systems "
            "for scientific and medical applications.</p>",
            "https://cs.example.edu/people/jane-smith",
        )
        rec = faculty_record(
            page, "https://cs.example.edu/people/jane-smith"
        )
        self.assertEqual(rec["name"], "Jane Q. Smith")

    def test_profile_without_research_evidence_is_rejected(self):
        page = parse(
            "<title>John Smith | CS</title><h1>John Smith</h1>"
            "<p>Professor. Alumni news, events, and department updates.</p>",
            "https://cs.example.edu/faculty/john-smith",
        )
        self.assertIsNone(
            faculty_record(page, "https://cs.example.edu/faculty/john-smith")
        )

    def test_directory_heading_is_not_faculty(self):
        for heading in (
            "Faculty Directory",
            "Affiliated Faculty",
            "Administrative Staff",
            "Graduate Students",
            "Faculty Openings",
            "Computational Biology",
        ):
            page = parse(
                f"<title>{heading}</title><h1>{heading}</h1>"
                "<p>Professor. Research interests include machine learning.</p>",
                "https://cs.example.edu/people",
            )
            self.assertIsNone(
                faculty_record(page, "https://cs.example.edu/people"),
                heading,
            )

    def test_css_excerpt_is_not_research(self):
        page = parse(
            "<title>Jane Doe</title><h1>Jane Doe</h1>"
            "<p>Professor. Research areas: body #backtotop "
            "{ background: red; border-color: blue; }</p>",
            "https://cs.example.edu/faculty/jane",
        )
        self.assertIsNone(
            faculty_record(page, "https://cs.example.edu/faculty/jane")
        )

    def test_output_guard_rejects_alumni_news(self):
        self.assertFalse(is_valid_faculty_output({
            "name": "Alumni News",
            "title": "Professor",
            "research_text": "Research interests include machine learning "
            "and artificial intelligence methods for scientific discovery.",
        }))

    def test_output_guard_rejects_legacy_css_payload(self):
        self.assertFalse(is_valid_faculty_output({
            "name": "Jane Doe",
            "title": "Professor",
            "profile_url": "https://cs.example.edu/people/jane",
            "research": "body #backtotop { background: blue; } "
            "window.a2a_config callbacks overlays javascript style content",
        }))

    def test_output_guard_rejects_news_profile_url(self):
        self.assertFalse(is_valid_faculty_output({
            "name": "Jane Doe",
            "title": "Professor",
            "profile_url": "https://cs.example.edu/news/jane-award",
            "research_text": "My research interests include machine learning "
            "models for reliable scientific and medical applications.",
        }))

    def test_output_guard_accepts_real_faculty(self):
        self.assertTrue(is_valid_faculty_output({
            "name": "Jane Doe",
            "title": "Assistant Professor",
            "profile_url": "https://cs.example.edu/people/jane-doe",
            "research_text": "My research interests include machine learning "
            "models for reliable scientific and medical applications.",
        }))


if __name__ == '__main__': unittest.main()
