import unittest
from world_memory.google_finance import parse_quote

class QuoteTests(unittest.TestCase):
    url='https://www.google.com/finance/quote/VIX:INDEXCBOE'
    def test_header_not_related_or_change(self):
        text='VIX:INDEXCBOE\nVIX\n14.81\n-4.08%\nSep 18, 3:15:01 PM GMT-5\narea_chart\nNo data\nRelated assets\nVIX 999'
        result=parse_quote(text,self.url,'2026-09-21T05:00:00Z')
        self.assertEqual(result['value'],14.81)
        self.assertEqual(result['date'],'2026-09-18')
        self.assertTrue(result['yearInferred'])
        with self.assertRaises(ValueError):
            parse_quote(text,self.url,'2026-10-01T05:00:00Z')
    def test_related_only_is_not_quote(self):
        with self.assertRaises(ValueError):
            parse_quote('VIX:INDEXCBOE\narea_chart\nRelated assets\n14.81\nSep 18, 3:15 PM GMT-5',self.url,'2026-09-21T05:00:00Z')
    def test_year_boundary_and_identity(self):
        text='VIX:INDEXCBOE\n14.81\nDec 31, 3:15 PM GMT-5\narea_chart'
        self.assertEqual(parse_quote(text,self.url,'2027-01-02T05:00:00Z')['date'],'2026-12-31')
        with self.assertRaises(ValueError):
            parse_quote(text,self.url.replace('VIX:', 'VIX3M:'),'2027-01-02T05:00:00Z')

    def test_leap_day_and_unrecognized_layout(self):
        text='VIX:INDEXCBOE\n14.81\nFeb 29, 3:15 PM GMT-5\narea_chart'
        self.assertEqual(parse_quote(text,self.url,'2024-03-01T05:00:00Z')['date'],'2024-02-29')
        with self.assertRaises(ValueError):
            parse_quote('VIX:INDEXCBOE\nPeople also search for\nVIX3M:INDEXCBOE\n20.35\nSep 18, 3:15 PM GMT-5',self.url,'2026-09-21T05:00:00Z')
