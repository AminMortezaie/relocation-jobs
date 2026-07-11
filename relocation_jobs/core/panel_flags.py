import os


def scrape_enabled() -> bool:
    return os.environ.get("PANEL_SCRAPE_ENABLED", "1").lower() not in ("0", "false", "no")


def company_fetch_enabled() -> bool:
    raw = os.environ.get("PANEL_COMPANY_FETCH_ENABLED")
    if raw is not None and raw.strip() != "":
        return raw.lower() not in ("0", "false", "no")
    return scrape_enabled()


def fetch_process_may_reap_orphans() -> bool:
    if os.environ.get("PANEL_SCRAPE_ENABLED", "0").lower() in ("1", "true", "yes"):
        return True
    return os.environ.get("PANEL_COMPANY_FETCH_ENABLED", "0").lower() in ("1", "true", "yes")
