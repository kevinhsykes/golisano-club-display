"""Checks for tools/snapshot_news.py (no network; saved sample feed): python3 -m unittest discover -s test -p 'test_*.py'"""
import datetime
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import snapshot_news as sn  # noqa: E402

NOW = datetime.datetime(2026, 11, 12, 14, 0, tzinfo=datetime.timezone.utc)
FEED = (ROOT / "test" / "fixtures" / "yahoo_news_MU.xml").read_bytes()


def rows():
    return sn.parse_feed(FEED, "MU", "Micron Technology", NOW)


class Relevance(unittest.TestCase):
    def test_ticker_or_company_in_the_title(self):
        self.assertTrue(sn.mentions("Micron and Sandisk surge", "MU", "Micron Technology"))
        self.assertTrue(sn.mentions("Stock MU jumps", "MU", "Micron Technology"))
        self.assertFalse(sn.mentions("Why Cisco and Oracle jumped today", "MU", "Micron Technology"))

    def test_ticker_is_a_whole_case_exact_token(self):
        self.assertFalse(sn.mentions("MUMBAI traders and mu-tant ETFs", "MU", "Micron Technology"))
        self.assertFalse(sn.mentions("Why UPSIDE matters", "UPS", "United Parcel Service Class B"))
        self.assertTrue(sn.mentions("UPS (UPS) beats", "UPS", "United Parcel Service Class B"))

    def test_company_names_and_aliases(self):
        self.assertTrue(sn.mentions("Caterpillar posts record backlog", "CAT", "Caterpillar"))
        self.assertTrue(sn.mentions("Apple unveils", "AAPL", "Apple"))
        self.assertTrue(sn.mentions("Google adds a model", "GOOGL", "Alphabet Class A"))
        self.assertTrue(sn.mentions("Alphabet earnings", "GOOGL", "Alphabet Class A"))
        self.assertTrue(sn.mentions("Meta signs deal", "META", "Meta Platforms Class A"))
        self.assertTrue(sn.mentions("Berkshire sells", "BRK/B", "Berkshire Hathaway Class B"))
        self.assertTrue(sn.mentions("Berkshire Hathaway (BRK.B) stock", "BRK/B", "Berkshire Hathaway Class B"))
        self.assertEqual(sn.company_names("META", "Meta Platforms Class A")[0], "Meta Platforms")

    def test_pineapple_is_not_apple(self):
        self.assertFalse(sn.mentions("Pineapple prices fall", "AAPL", "Apple"))


class Feed(unittest.TestCase):
    def test_titles_are_verbatim_apart_from_outer_whitespace(self):
        by_link = {r["link"]: r["title"] for r in rows()}
        self.assertEqual(by_link["https://finance.yahoo.com/articles/mu-hbm-1.html?.tsrc=rss"], "Micron (MU) Has Next Year’s HBM Sold: Can It Last?")
        self.assertEqual(by_link["https://finance.yahoo.com/articles/amp.html"], "Micron & Nvidia: S&P 500 “memory” rally")

    def test_links_are_the_feeds_own(self):
        for r in rows():
            self.assertTrue(r["link"].startswith("https://"))
            self.assertEqual(set(r) - {"publisher", "teaser"}, {"symbol", "title", "link", "published_utc"})


    def test_age_cutoff_missing_date_irrelevant_and_non_https_are_dropped(self):
        titles = " | ".join(r["title"] for r in rows())
        for gone in ("older than a week", "no date", "Cisco", "non-https", "MUMBAI"):
            self.assertNotIn(gone, titles)

    def test_time_zone_offsets_become_utc_and_publisher_only_when_given(self):
        by = {r["link"]: r for r in rows()}
        self.assertEqual(by["https://finance.yahoo.com/articles/amp.html"]["published_utc"], "2026-11-11T20:00:00Z")
        self.assertEqual(by["https://finance.yahoo.com/articles/mu-hbm-1.html?.tsrc=rss"]["publisher"], "Motley Fool")
        self.assertNotIn("publisher", by["https://www.fool.com/investing/2026/11/12/memory/?.tsrc=rss"])

    def test_dedupe_by_link_and_by_identical_title_keeps_the_newest(self):
        out = sn.dedupe(rows())
        self.assertEqual(len(out), len({r["link"] for r in out}))
        self.assertEqual([r["link"] for r in out if "memory" in r["link"] or "other-link" in r["link"]],
                         ["https://www.fool.com/investing/2026/11/12/memory/?.tsrc=rss"])
        self.assertEqual([r["published_utc"] for r in out], sorted((r["published_utc"] for r in out), reverse=True))

    def test_malformed_xml_raises_so_the_symbol_counts_as_failed(self):
        with self.assertRaises(ET.ParseError):
            sn.parse_feed(b"<html>not a feed", "MU", "Micron Technology", NOW)


class Merge(unittest.TestCase):
    def row(self, sym, link, when):
        return {"symbol": sym, "title": f"{sym} {link}", "link": "https://x/" + link, "published_utc": when}

    def test_failed_symbol_keeps_previous_items_until_they_age_out(self):
        prev = [self.row("MU", "a", "2026-11-11T10:00:00Z"), self.row("MU", "old", "2026-11-01T10:00:00Z"), self.row("CAT", "b", "2026-11-11T09:00:00Z")]
        fresh = [self.row("CAT", "c", "2026-11-12T10:00:00Z")]
        out = sn.merge(prev, fresh, {"MU"}, NOW)
        self.assertEqual([r["link"] for r in out], ["https://x/c", "https://x/a"])


class Main(unittest.TestCase):
    def run_main(self, fetch, previous=None):
        d = tempfile.mkdtemp()
        out = Path(d) / "news.json"
        if previous is not None:
            out.write_text(json.dumps(previous))
        with mock.patch.object(sn, "OUT", out), mock.patch.object(sn.datetime, "datetime", wraps=datetime.datetime) as dt:
            dt.now.return_value = NOW
            try:
                sn.main(fetch=fetch, pause=0)
                code = None
            except SystemExit as e:
                code = e.code
        return out, code

    def test_one_failed_symbol_is_listed_and_keeps_its_old_items(self):
        old = {"items": [{"symbol": "CAT", "title": "Caterpillar earlier", "link": "https://x/cat", "published_utc": "2026-11-11T10:00:00Z"}]}

        def fetch(url):
            if "s=CAT" in url:
                raise OSError("boom")
            return FEED       # a feed with items (only MU's titles pass the filter for MU)
        out, code = self.run_main(fetch, old)
        self.assertIsNone(code)
        doc = json.loads(out.read_text())
        self.assertEqual(doc["source"], "Yahoo Finance")
        self.assertEqual(doc["symbols_failed"], ["CAT"])
        self.assertNotIn("SPY", doc["symbols_checked"])
        self.assertIn("Caterpillar earlier", [i["title"] for i in doc["items"]])
        self.assertEqual(doc["checked_at_utc"], "2026-11-12T14:00:00Z")
        self.assertTrue(any(i["symbol"] == "MU" for i in doc["items"]))

    def test_an_empty_feed_keeps_that_symbols_old_items(self):
        old = {"items": [{"symbol": "CAT", "title": "Caterpillar earlier", "link": "https://x/cat", "published_utc": "2026-11-11T10:00:00Z"}]}

        def fetch(url):
            return b"<rss><channel></channel></rss>" if "s=CAT" in url else FEED
        out, code = self.run_main(fetch, old)
        doc = json.loads(out.read_text())
        self.assertEqual(doc["symbols_failed"], [])          # no news is not a failure
        self.assertEqual(doc["symbols_empty"], ["CAT"])
        self.assertIn("Caterpillar earlier", [i["title"] for i in doc["items"]])

    def test_every_symbol_failing_leaves_the_previous_file_untouched(self):
        old = {"checked_at_utc": "2026-11-11T00:00:00Z", "items": []}

        def fetch(url):
            raise OSError("feed discontinued")
        out, code = self.run_main(fetch, old)
        self.assertTrue(code)
        self.assertEqual(json.loads(out.read_text()), old)

    def test_requests_name_the_club_site_and_skip_funds(self):
        seen = []
        self.run_main(lambda url: seen.append(url) or b"<rss><channel></channel></rss>")
        self.assertFalse(any("s=SPY" in u for u in seen))
        self.assertTrue(any("s=BRK-B" in u for u in seen))
        self.assertIn("golisano-club-display", sn.UA)




class MatchingEdges(unittest.TestCase):
    def test_whole_words_and_case(self):
        from snapshot_news import mentions
        self.assertFalse(mentions("Catalyst ahead for chip stocks", "CAT", "Caterpillar"))
        self.assertFalse(mentions("A meta-analysis of interest rates", "META", "Meta Platforms Class A"))
        self.assertTrue(mentions("Meta beats on revenue", "META", "Meta Platforms Class A"))
        self.assertTrue(mentions("BRK-B hits a record", "BRK/B", "Berkshire Hathaway Class B"))
        self.assertTrue(mentions("BRK.B hits a record", "BRK/B", "Berkshire Hathaway Class B"))

    def test_other_organisations_and_press_releases(self):
        from snapshot_news import mentions
        self.assertFalse(mentions("Apple Hospitality REIT raises dividend", "AAPL", "Apple"))
        self.assertFalse(mentions("Fires in the Amazon rainforest", "AMZN", "Amazon"))
        self.assertFalse(mentions("Berkshire Hills Bancorp reports", "BRK/B", "Berkshire Hathaway Class B"))
        self.assertFalse(mentions("Meta Critical Minerals Completes High-Resolution LiDAR Survey", "META", "Meta Platforms Class A"))
        self.assertFalse(mentions("Global Parcel Delivery Market Report 2026: UPS, FedEx", "UPS", "United Parcel Service Class B"))

    def test_market_research_forms_are_dropped(self):
        from snapshot_news import mentions
        for title in [
            "Global Parcel Delivery Market Report 2026: UPS, FedEx",
            "Global Parcel Delivery Market Forecast 2030: UPS, FedEx",
            "Global Parcel Delivery Market Size 2026: UPS, FedEx",
        ]:
            with self.subTest(title=title):
                self.assertFalse(mentions(title, "UPS", "United Parcel Service Class B"))

    def test_global_market_share_news_is_kept(self):
        from snapshot_news import mentions
        self.assertTrue(mentions("Apple loses global market share in China, report says", "AAPL", "Apple"))

    def test_market_share_news_is_kept(self):
        from snapshot_news import mentions
        self.assertTrue(mentions("AMD gains server CPU market share from Intel", "AMD", "Advanced Micro Devices"))
        self.assertTrue(mentions("Stock market outlook: Tesla to report", "TSLA", "Tesla"))


class PressReleaseFilter(unittest.TestCase):
    def test_title_case_market_research_releases_are_dropped(self):
        from snapshot_news import mentions
        for title in ("Global Parcel Delivery Market Report 2026: UPS, FedEx",
                      "Global Parcel Delivery Market Analysis 2026: UPS",
                      "Global Parcel Delivery Market Trends 2026-2032: UPS",
                      "Global Parcel Delivery Market Growth 2026-2032: UPS",
                      "Global Parcel Delivery Market Share Analysis 2026: UPS",
                      "Global Parcel Delivery Market Insights 2026: UPS",
                      "Retail Logistics Market Report 2026 | UPS, FedEx"):
            with self.subTest(title=title):
                self.assertFalse(mentions(title, "UPS", "United Parcel Service Class B"))

    def test_news_sentences_about_a_market_are_kept(self):
        from snapshot_news import mentions
        for title, sym, name in (("Apple loses global market share in China, report says", "AAPL", "Apple"),
                                 ("Nvidia says AI chip market size could hit $1 trillion", "NVDA", "NVIDIA"),
                                 ("UPS global market forecast cut as volumes slow", "UPS", "United Parcel Service Class B"),
                                 ("Stock Market Outlook 2026: What To Expect From Apple", "AAPL", "Apple"),
                                 ("Apple Stock Market Outlook For 2026", "AAPL", "Apple"),
                                 ("Nvidia Says AI Chip Market Size Could Hit $1 Trillion", "NVDA", "NVIDIA"),
                                 ("UPS Global Market Forecast Cut As Volumes Slow In 2026", "UPS", "United Parcel Service Class B"),
                                 ("Apple Gains Market Share In China", "AAPL", "Apple")):
            with self.subTest(title=title):
                self.assertTrue(mentions(title, sym, name))




class Teasers(unittest.TestCase):
    def parse(self, description, title="Micron news"):
        feed = f'<rss><channel><item><title>{title}</title><link>https://example.com/a</link><pubDate>Thu, 12 Nov 2026 12:00:00 +0000</pubDate>{description}</item></channel></rss>'
        return sn.parse_feed(feed.encode(), "MU", "Micron", NOW)

    def test_verbatim_and_entities(self):
        text = '  First sentence.  Second & third — “unchanged”.\n'
        self.assertEqual(self.parse('<description><![CDATA[' + text.replace('&', '&amp;') + ']]></description>')[0]['teaser'], text)
        self.assertEqual(self.parse('<description>A &amp;amp; B &#8212; C</description>')[0]['teaser'], 'A & B — C')

    def test_markup_text_only(self):
        self.assertEqual(self.parse('<description><![CDATA[<p>One <b>bold</b> &amp; two.</p><p>Next.</p>]]></description>')[0]['teaser'], 'One bold & two.\nNext.')
        self.assertEqual(sn.plain_teaser('<p>Micron beats.</p><p>Shares rise.</p>'), 'Micron beats.\nShares rise.')
        self.assertEqual(sn.plain_teaser('Line one<br>line two'), 'Line one\nline two')
        self.assertEqual(sn.plain_teaser('<p>Text</p><script>alert(1)</script>'), 'Text')
        self.assertEqual(self.parse('<description>One <b>bold</b> tail.</description>')[0]['teaser'], 'One bold tail.')
        self.assertEqual(sn.plain_teaser('Revenue < 5 &amp; > 2'), 'Revenue < 5 & > 2')
        # Literal text that only looks like a tag is kept as written.
        self.assertEqual(sn.plain_teaser('Micron <strong> growth'), 'Micron <strong> growth')
        self.assertEqual(self.parse('<description>Micron &lt;strong&gt; growth</description>')[0]['teaser'], 'Micron <strong> growth')

    def test_empty_omitted(self):
        for description in ('', '<description/>', '<description>  </description>', '<description>&lt;p&gt;&lt;/p&gt;</description>'):
            self.assertNotIn('teaser', self.parse(description)[0])

    def test_only_title_controls_relevance(self):
        self.assertEqual(self.parse('<description>Micron MU</description>', 'Unrelated company'), [])
        self.assertEqual(len(self.parse('<description>Apple Hospitality Market Report</description>')), 1)

    def test_real_yahoo_sample(self):
        feed = (ROOT / 'test/fixtures/yahoo_news_MU_live.xml').read_bytes()
        items = sn.parse_feed(feed, 'MU', 'Micron', NOW)
        self.assertEqual(items[0]['teaser'], 'Key TakeawaysMicron earned $37. 7 billion in its quarter to Sept.')
        self.assertEqual(len(items), 1)  # The second real title does not name Micron.


class FetchDeadline(unittest.TestCase):
    def test_a_trickling_server_cannot_hold_the_fetch(self):
        class Trickle:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                import time as _t
                _t.sleep(0.05)
                return b"x"

        with mock.patch.object(sn.urllib.request, "urlopen", return_value=Trickle()):
            started = sn.time.monotonic()
            with self.assertRaises(TimeoutError):
                sn.get("https://example.test/feed", deadline=0.3)
            self.assertLess(sn.time.monotonic() - started, 2)


if __name__ == "__main__":
    unittest.main()
