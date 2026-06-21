---
name: add-country
description: Add a new country to the job scraper by fetching companies from relocate.me and wiring up the full pipeline.
---

# Add Country to Job Scraper

When the user says "do what we did for Germany for [country]" or "add [country]", follow this workflow:

## Step 1: Fetch companies from relocate.me

```python
import requests
from bs4 import BeautifulSoup
import json

country = "PORTUGAL"  # lowercase for URL
url = f"https://relocate.me/companies-hiring/{country.lower()}"

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# Paginate through all pages
all_companies = []
page = 1
while True:
    resp = requests.get(f"{url}?page={page}", headers=headers)
    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select(".company-card, .browsing-companies-item")
    if not cards:
        break
    for card in cards:
        name = card.select_one(".company-card__title, .browsing-companies-item__title")
        city = card.select_one(".company-card__city, .browsing-companies-item__city")
        size = card.select_one(".company-card__size, .browsing-companies-item__size")
        all_companies.append({
            "company": name.get_text(strip=True) if name else "Unknown",
            "city": city.get_text(strip=True) if city else "",
            "size": size.get_text(strip=True) if size else "",
        })
    page += 1
```

## Step 2: Save to `{country}_companies.json`

```json
{
  "source": "https://relocate.me/companies-hiring/{country}",
  "fetched": "YYYY-MM-DD",
  "total": N,
  "companies": [
    {
      "company": "CompanyName",
      "city": "City",
      "size": "51-200",
      "careers_url": null,
      "ats_type": null,
      "ats_url": null,
      "matching_jobs": []
    }
  ]
}
```

## Step 3: Update `relocation_jobs/paths.py`

Add the new country filename to `COUNTRY_JSON_FILENAMES`:

```python
COUNTRY_JSON_FILENAMES = {
    "germany": "germany_companies.json",
    "portugal": "portugal_companies.json",
    # add new country here
}
```

## Step 4: Run build_companies.py

```bash
python3 scripts/build_companies.py --file {country}_companies.json
```

This discovers `careers_url` for each company.

## Step 5: Run scrape_jobs.py

```bash
python3 scripts/scrape_jobs.py --file {country}_companies.json
```

This detects ATS platforms and scrapes matching backend jobs.

## Step 6: Verify

- Check `{country}_companies.json` has `careers_url` and `matching_jobs` populated
- Run the panel server and confirm the new country appears in the UI
