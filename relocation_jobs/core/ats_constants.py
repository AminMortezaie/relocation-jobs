"""Shared ATS scraper constants — no scraper logic, safe for services to import."""

from __future__ import annotations

DEFAULT_CONCURRENCY = 16
MAX_CONCURRENCY = 16

INCLUDE_KEYWORDS = [
    "backend", "back-end", "back end",
    "software engineer", "software developer",
    "platform engineer", "platform developer",
    "infrastructure engineer",
    "golang", "go engineer", "go developer", "go backend",
    "java ", "java,", "java/", "java-", "javascript", "typescript",
    "kotlin", "spring boot",
    "microservice", "distributed",
    "fullstack", "full-stack", "full stack",
    "product engineer",
    "solutions engineer",
    "senior engineer",
]

EXCLUDE_KEYWORDS = [
    "frontend", "front-end", "front end",
    "android", "ios", "mobile",
    "designer", " design ", "security", "security engineer",
    "marketing", "sales", "account manager", "account executive",
    "data scientist", "data analyst", "machine learning engineer",
    "product manager", "product owner",
    "recruiter", " hr ", "human resource", "talent acquisition",
    "accounting", "legal counsel", "legal trainee",
    "customer success", "customer support", "customer service",
    "office manager", "executive assistant",
    "content ", "copywriter", "seo",
    "game designer", "game artist", "level designer",
    "3d artist", "animator", "concept artist",
    "vp of", "head of", "director of", "chief ",
    "internship", "intern ",
    "lead ", " lead",
    "engineering manager",
    "principal ",
    "junior", "AI Operations", "AI Ops", "integration engineer",
    "Data analytics", "data analytics engineer",
    "devops", "dev ops", "unity", "value engineer"
    "site reliability", " sre", "associate"
    "cloud site reliability",
]

ATS_TYPE_CHOICES: tuple[tuple[str, str], ...] = (
    ("ashby", "Ashby"),
    ("atlassian", "Atlassian"),
    ("applytojob", "ApplyToJob"),
    ("bamboohr", "BambooHR"),
    ("bol", "bol.com API"),
    ("deel", "Deel"),
    ("epam", "EPAM"),
    ("greenhouse", "Greenhouse"),
    ("greenhouse_eu", "Greenhouse (EU)"),
    ("hirehive", "HireHive"),
    ("jibe", "Jibe"),
    ("job_shop", "Job Shop / Talents Connect"),
    ("join", "JOIN"),
    ("lever", "Lever"),
    ("lever_eu", "Lever (EU)"),
    ("movingimage", "movingimage"),
    ("personio", "Personio"),
    ("project_a", "Project A"),
    ("recruitee", "Recruitee"),
    ("rss", "RSS feed"),
    ("smartrecruiters", "SmartRecruiters"),
    ("teamtailor", "Teamtailor"),
    ("workable", "Workable"),
    ("workday", "Workday"),
)

BOL_CAREERS_API = "https://careers.bol.com/wp-json/wp/v2/hggns/multilanguage_vacature_search"

# Companies where auto-detection fails or returns a bad slug (embed, proxy).
KNOWN_ATS: dict[str, tuple[str, str]] = {
    "SimScale":            ("greenhouse",    "https://boards.greenhouse.io/simscale"),
    "HelloFresh":          ("greenhouse",    "https://boards.greenhouse.io/hellofresh"),
    "Talon.One":           ("greenhouse_eu", "https://boards.eu.greenhouse.io/talonone"),
    "adjoe":               ("ashby",         "https://jobs.ashbyhq.com/adjoe"),
    "ePages":              ("personio",      "https://epages-gmbh.jobs.personio.de/"),
    "epilot":              ("recruitee",     "https://epilot.recruitee.com/"),
    "Instapro Group":      ("recruitee",     "https://instaprogroup.recruitee.com/"),
    "Limehome":            ("recruitee",     "https://limehome.recruitee.com/"),
    "Adyen":               ("greenhouse",    "https://boards.greenhouse.io/adyen"),
    "bol":                 ("bol",           BOL_CAREERS_API),
    "Catawiki":            ("greenhouse",    "https://boards.greenhouse.io/catawiki"),
    "Housing Anywhere":    ("greenhouse",    "https://boards.greenhouse.io/housinganywhere"),
    "LINKIT":              ("recruitee",     "https://linkit.recruitee.com/"),
    "Mollie":              ("ashby",         "https://jobs.ashbyhq.com/mollie"),
    "Bunq":                ("recruitee",     "https://bunq.recruitee.com/"),
    "Picnic":              ("smartrecruiters", "https://api.smartrecruiters.com/v1/companies/picnic/postings"),
    "Reaktor":             ("ashby",         "https://jobs.ashbyhq.com/reaktor"),
    "GreenFlux":           ("recruitee",     "https://greenflux.recruitee.com/"),
    "HomeToGo":            ("personio",      "https://hometogo.jobs.personio.de/"),
    "Personio":            ("personio",      "https://www.personio.com/api/careers/jobs/list"),
    "ASML":                ("workday",       "https://asml.wd3.myworkdayjobs.com/wday/cxs/asml/ASMLEXT1/jobs|https://asml.wd3.myworkdayjobs.com/en-US/ASMLEXT1"),
    "Atlassian":           ("atlassian",     "https://www.atlassian.com/company/careers/all-jobs?location=Netherlands"),
    "Booking.com":         ("jibe",          "https://jobs.booking.com/booking/jobs"),
    "C Teleport":          ("teamtailor",    "https://careers.cteleport.com/jobs"),
    "Elements":            ("workable",      "https://apply.workable.com/elements/"),
    "EPAM":                ("epam",          "https://careers.epam.com/"),
    "EVBox":               ("rss",           "https://evbox.com/en/about/careers/feed/"),
    "Just Eat Takeaway.com": ("workday",     "https://wd3.myworkdaysite.com/wday/cxs/takeaway/JET-ECS-R/jobs|https://wd3.myworkdaysite.com/en-US/takeaway/JET-ECS-R"),
    "NXP":                 ("workday",       "https://nxp.wd3.myworkdayjobs.com/wday/cxs/nxp/careers/jobs|https://nxp.wd3.myworkdayjobs.com/en-US/careers"),
    "TomTom":              ("lever_eu",      "https://jobs.eu.lever.co/tomtom"),
    "ZooStation":          ("hirehive",      "https://zoostation-bv.hirehive.com"),
    "arculus":               ("greenhouse",    "https://boards.greenhouse.io/arculus"),
    "Blinkist":              ("greenhouse",    "https://boards.greenhouse.io/blinkslabgmbh"),
    "Highsnobiety":          ("teamtailor",    "KgRa_9irgDNXSf7nuil0A_ySurtx4Xgw0OGFvkFb"),
    "justDice":              ("ashby",         "https://jobs.ashbyhq.com/justDice"),
    "justtrack":             ("ashby",         "https://jobs.ashbyhq.com/justtrack"),
    "movingimage":           ("movingimage",   "https://www.movingimage.com/careers/"),
    "N26":                   ("greenhouse",    "https://boards.greenhouse.io/n26"),
    "Onefootball":           ("applytojob",    "https://onefootball.applytojob.com/"),
    "Prime Intellect":       ("ashby",         "https://jobs.ashbyhq.com/PrimeIntellect"),
    "Project A Ventures":    ("project_a",     "https://www.project-a.vc/careers"),
    "Solvians":              ("bamboohr",      "https://wsd.bamboohr.com/careers/list"),
    "Taxfix":                ("ashby",         "https://jobs.ashbyhq.com/taxfix.com"),
    "ToolTime":              ("teamtailor",    "ot2xtYSXyjp5WG59fCbHpro2vAcLiljIDNfSfqps"),
    "Vimcar":                ("workable",      "https://apply.workable.com/shiftmove/"),
    "Deutsche Boerse":       ("job_shop",      "https://careers.deutsche-boerse.com/"),
    "Redcare - Dusseldorf":  ("smartrecruiters", "https://api.smartrecruiters.com/v1/companies/Redcare-Pharmacy/postings"),
}

FORCE_KNOWN_ATS = frozenset({
    "bol", "adjoe",
    "Deutsche Boerse",
    "Highsnobiety", "ToolTime", "Vimcar",
    "ASML", "Atlassian", "Booking.com", "C Teleport", "Elements", "EPAM",
    "EVBox", "Just Eat Takeaway.com", "TomTom", "ZooStation",
})

try:
    import httpx  # noqa: F401
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
