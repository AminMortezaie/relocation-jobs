"""Re-exports for the ``scrape_jobs`` compatibility shim (tests monkeypatch here)."""

from __future__ import annotations

import sys

from relocation_jobs.catalog_db import load_country_catalog, touch_country_meta, upsert_company
from relocation_jobs.core.ats_constants import (
    ATS_TYPE_CHOICES,
    BOL_CAREERS_API,
    DEFAULT_CONCURRENCY,
    EXCLUDE_KEYWORDS,
    FORCE_KNOWN_ATS,
    HTTPX_AVAILABLE,
    INCLUDE_KEYWORDS,
    KNOWN_ATS,
)
from relocation_jobs.core.ats_detection import (
    ATS_HINT_URL_DETECTORS,
    HTML_ATS_PATTERNS,
    HEADERS,
    PLAYWRIGHT_AVAILABLE,
    XHR_ATS_PATTERNS,
    _CAREERS_PAGE_AS_ATS,
    _company_slug,
    _detect_applytojob_from_url,
    _detect_ats_from_careers_url,
    _detect_ats_in_html_for_hint,
    _detect_bamboohr_from_url,
    _detect_deel_from_url,
    _detect_hirehive_from_url,
    _detect_join_from_url,
    _detect_job_shop_from_url,
    _detect_recruitee_board_url,
    _detect_recruitee_from_careers_host,
    _detect_smartrecruiters_from_careers_url,
    _detect_smartrecruiters_from_redcare_careers,
    _detect_teamtailor_from_url,
    _detect_workday_from_url,
    _extract_ashby,
    _extract_greenhouse,
    _extract_greenhouse_eu,
    _extract_lever,
    _extract_personio,
    _extract_recruitee,
    _extract_smartrecruiters,
    _extract_teamtailor,
    _extract_workable,
    _extract_workday,
    _parse_job_shop_config,
    _playwright_browser_context,
    _playwright_pause,
    _playwright_sem,
    _resolve_nuxt_payload_node,
    _resolve_nuxt_scalar,
    _smartrecruiters_api_url,
    _smartrecruiters_company_id,
    _workday_api_and_base,
    detect_ats_for_hint,
    detect_ats_static,
    detect_ats_static_async,
    detect_ats_via_playwright,
    guess_ats_url_from_name,
)
from relocation_jobs.core.job_identity import job_idempotency_key, job_idempotency_key_for_job, stamp_job_identity
from relocation_jobs.core.location_tags import (
    company_expected_locations,
    filter_jobs_by_expected_locations,
    job_matches_expected_locations,
)
from relocation_jobs.core.paths import COUNTRY_ARCHIVE_FILENAMES, SUPPORTED_COUNTRIES
from relocation_jobs.core.scrape_cancel import (
    FetchCancelled,
    clear_cancel_checker,
    is_cancel_requested,
    raise_if_cancelled,
    set_cancel_checker,
)
from relocation_jobs.scrape import ashby as _scrape_ashby
from relocation_jobs.scrape import bol as _scrape_bol
from relocation_jobs.scrape import deel as _scrape_deel
from relocation_jobs.scrape import descriptions as _scrape_descriptions
from relocation_jobs.scrape import generic as _scrape_generic
from relocation_jobs.scrape import greenhouse as _scrape_greenhouse
from relocation_jobs.scrape import http as _scrape_http
from relocation_jobs.scrape import job_shop as _scrape_job_shop
from relocation_jobs.scrape import join as _scrape_join
from relocation_jobs.scrape import lever as _scrape_lever
from relocation_jobs.scrape import listing as _scrape_listing
from relocation_jobs.scrape import misc as _scrape_misc
from relocation_jobs.scrape import personio as _scrape_personio
from relocation_jobs.scrape import recruitee as _scrape_recruitee
from relocation_jobs.scrape import smartrecruiters as _scrape_smartrecruiters
from relocation_jobs.scrape import teamtailor as _scrape_teamtailor
from relocation_jobs.scrape import workday as _scrape_workday
from relocation_jobs.scrape import workable as _scrape_workable
from relocation_jobs.scrape.merge import backfill_listing_locations, merge_matching_jobs, now_iso
from relocation_jobs.scrape.playwright import sync_playwright
from relocation_jobs.scrape.relevance import explain_title_filter, is_relevant
from relocation_jobs.scrape.util import safe_print as _safe_print, today

requests = _scrape_http.requests
if HTTPX_AVAILABLE:
    httpx = _scrape_http.httpx

DEFAULT_WORKERS = DEFAULT_CONCURRENCY

_filter_relevant_jobs = _scrape_listing.filter_relevant_jobs
_listing_job = _scrape_listing.listing_job
_workable_location_text = _scrape_listing.workable_location_text
_smartrecruiters_location_text = _scrape_listing.smartrecruiters_location_text
_bamboohr_location_text = _scrape_listing.bamboohr_location_text
_normalize_title = _scrape_listing.normalize_title
_title_from_listing_anchor = _scrape_listing.title_from_listing_anchor
_fetch_job_detail_title = _scrape_listing.fetch_job_detail_title
_needs_detail_title = _scrape_listing.needs_detail_title
_is_listing_noise_url = _scrape_listing.is_listing_noise_url
_collect_listing_job_links = _scrape_listing.collect_listing_job_links
_listing_candidates_to_jobs = _scrape_listing.listing_candidates_to_jobs
_jobs_from_listing_html = _scrape_listing.jobs_from_listing_html

scrape_greenhouse = _scrape_greenhouse.scrape_greenhouse
scrape_greenhouse_async = _scrape_greenhouse.scrape_greenhouse_async
_fetch_greenhouse_job_text = _scrape_greenhouse.fetch_greenhouse_job_text
scrape_lever = _scrape_lever.scrape_lever
scrape_lever_async = _scrape_lever.scrape_lever_async
_fetch_lever_job_text = _scrape_lever.fetch_lever_job_text
scrape_recruitee = _scrape_recruitee.scrape_recruitee
scrape_recruitee_async = _scrape_recruitee.scrape_recruitee_async
_fetch_recruitee_job_text = _scrape_recruitee.fetch_recruitee_job_text
scrape_ashby = _scrape_ashby.scrape_ashby
_fetch_ashby_job_text = _scrape_ashby.fetch_ashby_job_text
_workable_slug_from_url = _scrape_workable.workable_slug_from_url
scrape_workable = _scrape_workable.scrape_workable
scrape_workable_async = _scrape_workable.scrape_workable_async
scrape_generic = _scrape_generic.scrape_generic
scrape_with_playwright = _scrape_generic.scrape_with_playwright
scrape_generic_async = _scrape_generic.scrape_generic_async
_html_to_text = _scrape_descriptions.html_to_text
detect_visa_relocation = _scrape_descriptions.detect_visa_relocation

_parse_deel_jobs = _scrape_deel.parse_deel_jobs
_deel_slug_from_url = _scrape_deel.deel_slug_from_url
scrape_deel = _scrape_deel.scrape_deel
scrape_deel_async = _scrape_deel.scrape_deel_async
_parse_join_next_data = _scrape_join.parse_join_next_data
_join_jobs_from_items = _scrape_join.join_jobs_from_items
_fetch_join_items_via_api = _scrape_join.fetch_join_items_via_api
scrape_join = _scrape_join.scrape_join
scrape_join_async = _scrape_join.scrape_join_async
scrape_personio_com_api = _scrape_personio.scrape_personio_com_api
scrape_personio_html = _scrape_personio.scrape_personio_html
scrape_personio_async = _scrape_personio.scrape_personio_async
_bol_doelgroep_from_url = _scrape_bol.bol_doelgroep_from_url
_bol_search_payload = _scrape_bol.bol_search_payload
_jobs_from_bol_response = _scrape_bol.jobs_from_bol_response
scrape_bol = _scrape_bol.scrape_bol
scrape_bol_async = _scrape_bol.scrape_bol_async
_job_shop_search_payload = _scrape_job_shop.job_shop_search_payload
_jobs_from_job_shop_response = _scrape_job_shop.jobs_from_job_shop_response
scrape_job_shop = _scrape_job_shop.scrape_job_shop
scrape_job_shop_async = _scrape_job_shop.scrape_job_shop_async
scrape_smartrecruiters = _scrape_smartrecruiters.scrape_smartrecruiters
scrape_smartrecruiters_async = _scrape_smartrecruiters.scrape_smartrecruiters_async
scrape_workday = _scrape_workday.scrape_workday
scrape_workday_async = _scrape_workday.scrape_workday_async

_teamtailor_board_url = _scrape_teamtailor.teamtailor_board_url
_teamtailor_location_map = _scrape_teamtailor.teamtailor_location_map
_teamtailor_listing_jobs_from_feed = _scrape_teamtailor.teamtailor_listing_jobs_from_feed
_fetch_teamtailor_jobs = _scrape_teamtailor.fetch_teamtailor_jobs
_scrape_teamtailor_html_board = _scrape_teamtailor.scrape_teamtailor_html_board

scrape_applytojob = _scrape_misc.scrape_applytojob
scrape_bamboohr = _scrape_misc.scrape_bamboohr
scrape_movingimage = _scrape_misc.scrape_movingimage
scrape_project_a = _scrape_misc.scrape_project_a
scrape_hirehive = _scrape_misc.scrape_hirehive
scrape_epam = _scrape_misc.scrape_epam
scrape_rss = _scrape_misc.scrape_rss
scrape_hirehive_async = _scrape_misc.scrape_hirehive_async
scrape_epam_async = _scrape_misc.scrape_epam_async
scrape_rss_async = _scrape_misc.scrape_rss_async
