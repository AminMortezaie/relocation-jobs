from __future__ import annotations

from relocation_jobs.scrape.boards.remotedxb import parse_remotedxb_rss, remotedxb_feed_url


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:remoteDxb="https://www.remotedxb.com/rss">
  <channel>
    <item>
      <title>Principal Software Engineer</title>
      <link>https://www.remotedxb.com/job/principal-software-engineer-cyberhaven--1</link>
      <description><![CDATA[<p>Build secure browsers</p>]]></description>
      <category>Information Technology</category>
      <remoteDxb:companyName>Cyberhaven</remoteDxb:companyName>
    </item>
    <item>
      <title>Sales Manager</title>
      <link>https://www.remotedxb.com/job/sales-manager--2</link>
      <description><![CDATA[<p>Sell</p>]]></description>
      <category>Sales &amp; Business Development</category>
      <remoteDxb:companyName>SalesCo</remoteDxb:companyName>
    </item>
  </channel>
</rss>
"""


def test_remotedxb_feed_url_normalizes():
    assert remotedxb_feed_url("") == "https://www.remotedxb.com/rss"
    assert remotedxb_feed_url("https://www.remotedxb.com/") == "https://www.remotedxb.com/rss"
    assert remotedxb_feed_url("https://www.remotedxb.com/rss") == "https://www.remotedxb.com/rss"


def test_parse_remotedxb_rss_keeps_it_jobs_with_employer():
    jobs = parse_remotedxb_rss(SAMPLE_RSS)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Principal Software Engineer"
    assert jobs[0]["employer"] == "Cyberhaven"
    assert jobs[0]["location"] == "Completely Remote"
    assert "secure browsers" in jobs[0]["description_text"]
