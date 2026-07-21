from __future__ import annotations

import html
import re
from xml.etree import ElementTree

import requests

from relocation_jobs.core.ats_detection import HEADERS
from relocation_jobs.scrape.boards._async import run_sync
from relocation_jobs.scrape.listing import listing_job

DEFAULT_REMOTEDXB_RSS = "https://www.remotedxb.com/rss"
_NS = {"rd": "https://www.remotedxb.com/rss"}
_TAG_RE = re.compile(r"<[^>]+>")

_IT_CATEGORIES = frozenset({
    "information technology",
    "engineering & architecture",
    "engineering and architecture",
})


def remotedxb_feed_url(board_url: str) -> str:
    raw = (board_url or "").strip()
    if not raw:
        return DEFAULT_REMOTEDXB_RSS
    lower = raw.lower()
    if "remotedxb.com" not in lower:
        return DEFAULT_REMOTEDXB_RSS
    if "/rss" in lower:
        return "https://www.remotedxb.com/rss"
    return DEFAULT_REMOTEDXB_RSS


def _plain_text(raw: str) -> str:
    text = html.unescape(raw or "")
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _item_text(item: ElementTree.Element, tag: str) -> str:
    node = item.find(tag)
    if node is not None and (node.text or "").strip():
        return (node.text or "").strip()
    node = item.find(tag, _NS)
    if node is not None and (node.text or "").strip():
        return (node.text or "").strip()
    return ""


def parse_remotedxb_rss(feed_xml: str) -> list[dict]:
    text = (feed_xml or "").lstrip("\ufeff").strip()
    xml_start = text.find("<?xml")
    if xml_start > 0:
        text = text[xml_start:]
    if not text:
        return []
    root = ElementTree.fromstring(text.encode("utf-8"))
    jobs: list[dict] = []
    for item in root.findall(".//item"):
        title = _item_text(item, "title")
        link = _item_text(item, "link")
        employer = _item_text(item, "rd:companyName")
        if not employer:
            employer = _item_text(item, "{https://www.remotedxb.com/rss}companyName")
        category = _item_text(item, "category")
        if category and category.casefold() not in _IT_CATEGORIES:
            continue
        if not title or not link or not employer:
            continue
        description = _plain_text(_item_text(item, "description"))
        jobs.append(
            listing_job(
                title,
                link,
                location="Completely Remote",
                employer=employer,
                description_text=description or None,
            )
        )
    return jobs


def fetch_remotedxb_board_sync(feed_url: str) -> list[dict]:
    url = remotedxb_feed_url(feed_url)
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return parse_remotedxb_rss(response.text)


async def fetch_remotedxb_board(client, board_url: str, company: dict) -> list[dict]:
    url = board_url or (company.get("ats_url") or company.get("careers_url") or "")
    return await run_sync(fetch_remotedxb_board_sync, url)
