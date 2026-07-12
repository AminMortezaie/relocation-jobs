# SEO indexing

How to get kuchup.com found on Google.

## Prerequisites

- Domain `kuchup.com` is live and serving the public homepage
- `robots.txt` at `https://kuchup.com/robots.txt` allows indexing
- `sitemap.xml` at `https://kuchup.com/sitemap.xml` is up to date
- Marketing pages deployed (see [ec2-panel.md](ec2-panel.md))

## Google Search Console setup

1. Go to <https://search.google.com/search-console>
2. Add property: **URL prefix** `https://kuchup.com`
3. Verify ownership — choose any method:
   - **DNS TXT record** (recommended): add the TXT record in your DNS provider (Cloudflare).
   - **HTML file**: Google provides a file; drop it into `relocation_jobs/static/` and re-deploy.
   - **Google Analytics / Google Tag Manager**: if already installed.
4. Once verified, submit the sitemap:
   - Navigate to **Sitemaps** section
   - Enter `https://kuchup.com/sitemap.xml` and submit
5. Request manual indexing for key pages:
   - **URL inspection** → paste root URL → **Request indexing**
   - Repeat for: `/how-it-works`, `/pricing`, `/relocation-jobs-germany`, `/relocation-jobs-netherlands`, `/relocation-jobs-uk`, `/relocation-jobs-portugal`

## What to expect

| Timeline | Event |
|----------|-------|
| Hours–days | Homepage indexed |
| Days–weeks | Marketing pages indexed |
| Weeks–months | Category queries start returning results |
| N/A | Job-listing-specific queries **will not rank** — positions are private |

> **Important:** This is a product-marketing SEO strategy, not a job-board SEO strategy.
> Google will index the site as a curation tool / category resource for relocation-friendly
> tech roles in Europe. Individual job listings are not public and will not appear in
> search results.

## Monitoring

- Check Search Console **Performance** tab weekly for clicks and impressions
- Watch **Coverage** for indexing errors or sitemap issues
- Fix any `noindex` flags, 404s, or crawl errors promptly

## When the paid redesign launches

- Add `JobPosting` structured data to public listing pages
- Expand sitemap with job/company detail URLs
- Re-submit sitemap in Search Console
- See [rules.md](../reference/rules.md) for public data constraints
