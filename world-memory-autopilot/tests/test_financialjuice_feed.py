import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from financialjuice_feed import collect, parse_rss

RSS = b'''<rss><channel><item><title>Company raises guidance</title>
<link>https://www.financialjuice.com/News/1/example.aspx</link>
<guid>1</guid><pubDate>Mon, 28 Sep 2026 14:48:10 GMT</pubDate>
<description/></item></channel></rss>'''


class FeedTests(unittest.TestCase):
    def test_headline_feed_and_timezone(self):
        result = parse_rss(RSS)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['items'][0]['publishedAt'], '2026-09-28T14:48:10+00:00')
        self.assertEqual(result['items'][0]['description'], '')

    def test_rssapp_correction_and_undated_candidates(self):
        self.assertEqual(parse_rss(RSS, 'first_squawk')['items'][0]['publishedAt'],
                         '2026-09-28T05:48:10+00:00')
        undated = RSS.replace(b'<pubDate>Mon, 28 Sep 2026 14:48:10 GMT</pubDate>', b'')
        result = parse_rss(undated, 'dow_jones')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['undatedCount'], 1)
        self.assertIsNone(result['oldestPublishedAt'])
        self.assertIsNone(result['items'][0]['publishedAt'])

    def test_feed_caches_preserve_independent_outcomes(self):
        with tempfile.TemporaryDirectory() as d:
            def request(argv, **kwargs):
                target = Path(argv[argv.index('--output') + 1])
                target.write_bytes(RSS)
                return subprocess.CompletedProcess(argv, 0,
                    '502' if 'd68ow40E3dkwaEvN' in argv[-1] else '200', '')
            with patch('financialjuice_feed.subprocess.run', side_effect=request) as call:
                self.assertEqual(collect(d, 'first_squawk')['status'], 'unavailable')
                self.assertEqual(collect(d, 'reuters')['status'], 'ok')
                self.assertEqual(collect(d, 'first_squawk')['status'], 'unavailable')
                self.assertEqual(collect(d, 'reuters')['status'], 'ok')
                self.assertEqual(call.call_count, 2)

    def test_http_200_html_is_not_a_feed(self):
        with self.assertRaises(ValueError):
            parse_rss(b'<html>Site Unavailable</html>')

    def test_success_and_failure_are_both_reused_without_network(self):
        for status in ('200', '429', '403'):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as d:
                def request(*args, **kwargs):
                    Path(d, 'response.xml').write_bytes(RSS if status == '200' else b'error code: 1015')
                    return subprocess.CompletedProcess(args, 0, status, '')
                with patch('financialjuice_feed.subprocess.run', side_effect=request) as call:
                    first = collect(d)
                    self.assertEqual(collect(d), first)
                    self.assertEqual(call.call_count, 1)
                    self.assertEqual(first['status'], 'ok' if status == '200' else 'unavailable')

    def test_interrupted_attempt_does_not_retry(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'attempted').touch()
            with patch('financialjuice_feed.subprocess.run') as call:
                self.assertEqual(collect(d)['reason'], 'already-attempted')
                call.assert_not_called()

    def test_bad_dates_rejected_and_duplicates_collapsed(self):
        bad = RSS.replace(b'Mon, 28 Sep 2026 14:48:10 GMT', b'unknown')
        self.assertEqual(parse_rss(bad)['rejectedCount'], 1)
        row = RSS.split(b'<channel>')[1].split(b'</channel>')[0]
        self.assertEqual(parse_rss(b'<rss><channel>'+row+row+b'</channel></rss>')['count'], 1)


if __name__ == '__main__':
    unittest.main()
