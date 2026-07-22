export type CountryPageContent = {
  kicker: string;
  lede: string;
  hubs: string[];
  marketTitle: string;
  marketBody: string[];
  sponsorTitle: string;
  sponsorBody: string[];
  visaTitle: string;
  visaIntro: string;
  visaRoutes: { title: string; body: string }[];
  thresholds: { label: string; value: string }[];
  flowTitle: string;
  flowSteps: { title: string; body: string }[];
  officialLabel: string;
  officialHref: string;
  visaDisclaimer: string;
  faq: { question: string; answer: string }[];
  metaDescription: string;
};

export const COUNTRY_PAGES: Record<string, CountryPageContent> = {
  germany: {
    kicker: "Germany · visas & sponsorship",
    lede:
      "Germany is one of Europe’s deepest software markets for international hires. Most engineers relocate on an EU Blue Card after a concrete job offer that meets the published salary threshold — with IT treated as a shortage occupation.",
    hubs: ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"],
    marketTitle: "Why software engineers target Germany",
    marketBody: [
      "Germany combines large product companies, industrial software, fintech, and scale-ups that routinely hire non-EU engineers when the role and salary qualify for skilled immigration.",
      "Hiring hubs such as Berlin, Munich, Hamburg, and Frankfurt publish roles on company career pages. Kuchup indexes those pages so you can track offers before the visa paperwork starts.",
    ],
    sponsorTitle: "How sponsorship works in Germany",
    sponsorBody: [
      "There is no separate “sponsor licence” register like the UK. In practice the employer sponsors you by issuing a qualifying contract and completing the Declaration of Employment (Erklärung zum Beschäftigungsverhältnis) for the visa file.",
      "For many EU Blue Card cases in shortage occupations such as ICT, the Federal Employment Agency (BA) is involved in the approval path. Your company usually coordinates that with their immigration counsel or HR.",
      "Ask early whether the offer is intended for an EU Blue Card, another §18 residence title, or a local hire only — the contract language and salary must match the route.",
    ],
    visaTitle: "Main routes engineers discuss",
    visaIntro:
      "The EU Blue Card is the default conversation for qualified software roles. Thresholds are set annually; confirm the current figures on Make it in Germany before you negotiate.",
    visaRoutes: [
      {
        title: "EU Blue Card (ICT / shortage threshold)",
        body: "For many IT and software roles the 2026 shortage-occupation gross annual threshold is commonly cited around €45,934, with a higher general threshold for other professions (about €50,700). You need a job offer of at least six months and a recognized degree — or, for some IT cases, documented graduate-level experience instead of a formal degree.",
      },
      {
        title: "Other skilled-worker titles",
        body: "If the Blue Card salary floor is not met, employers sometimes use other skilled employment residence titles. Those paths have their own BA and qualification rules — do not assume interchangeability.",
      },
      {
        title: "Opportunity Card (Chancenkarte)",
        body: "A points-based job-seeker route exists for people exploring Germany without an offer yet. It is not a work visa by itself; once you secure a qualifying job you still switch into an employment residence title.",
      },
    ],
    thresholds: [
      { label: "Blue Card ICT / shortage (2026, commonly cited)", value: "≈ €45,934 / year gross" },
      { label: "Blue Card general (2026, commonly cited)", value: "≈ €50,700 / year gross" },
      { label: "Contract length for Blue Card", value: "At least 6 months" },
    ],
    flowTitle: "Typical Germany relocation flow",
    flowSteps: [
      {
        title: "Land a qualifying offer",
        body: "Confirm title, location, start date, and gross salary against the Blue Card (or other) threshold. Get the written contract and the employer’s declaration forms.",
      },
      {
        title: "Prepare the visa dossier",
        body: "Passport, VIDEX/application forms, degree recognition evidence (Anabin / ZAB where relevant), contract, employer declaration, and insurance as required by the consulate.",
      },
      {
        title: "Apply for the national visa",
        body: "Book the German mission or VAC in your country of residence. Processing times vary by post; employers often estimate several weeks once the file is complete.",
      },
      {
        title: "Enter Germany and convert to a residence title",
        body: "After arrival, complete registration (Anmeldung) and the local foreigner’s authority steps for your residence card. Keep the career-page offer and Kuchup tracking aligned until you have submitted.",
      },
    ],
    officialLabel: "Make it in Germany — EU Blue Card",
    officialHref: "https://www.make-it-in-germany.com/en/visa-residence/types/eu-blue-card",
    visaDisclaimer:
      "Orientation only — not immigration or legal advice. Thresholds and forms change; verify on official German government sites and with qualified counsel.",
    faq: [
      {
        question: "Do German employers need a UK-style sponsor licence?",
        answer:
          "No. Sponsorship is expressed through a qualifying employment contract and the documents the mission and authorities require. Always ask HR which residence title they intend to support.",
      },
      {
        question: "Is software engineering treated as a shortage occupation?",
        answer:
          "ICT professionals are commonly treated under the lower EU Blue Card shortage threshold, but classification and BA involvement depend on the role. Confirm with the employer’s immigration process.",
      },
      {
        question: "How does Kuchup help before the visa?",
        answer:
          "Kuchup tracks Germany roles from career pages and can connect Claude or Cursor via MCP to tailor your CV. You still submit the application and run the visa process with the employer.",
      },
    ],
    metaDescription:
      "Germany visa sponsorship for software engineers: EU Blue Card thresholds, employer declaration flow, Berlin Munich Hamburg hubs, and how to track relocation roles on Kuchup.",
  },
  netherlands: {
    kicker: "Netherlands · visas & sponsorship",
    lede:
      "The Netherlands uses a recognised-sponsor model. For most non-EU software engineers the Highly Skilled Migrant (kennismigrant) permit is the default: the employer must already be listed with the IND and files on your behalf.",
    hubs: ["Amsterdam", "Eindhoven", "Rotterdam", "Utrecht", "The Hague"],
    marketTitle: "Why software engineers target the Netherlands",
    marketBody: [
      "Amsterdam, Eindhoven, Utrecht, and surrounding hubs host product companies, fintech, deep-tech, and international engineering teams that hire in English.",
      "Speed is a practical advantage when the employer is already an IND recognised sponsor: many cases are decided in roughly two to four weeks after a complete filing.",
    ],
    sponsorTitle: "How sponsorship works in the Netherlands",
    sponsorBody: [
      "Only an IND recognised sponsor (erkend referent) can apply for your Highly Skilled Migrant residence permit. You generally cannot self-file this route.",
      "Check whether the company appears on the public register of recognised sponsors before you invest weeks in an onsite loop. Startups that are not yet recognised may need another route or delay hiring.",
      "Salary must meet the IND age-based monthly threshold (excluding holiday allowance). There is no formal degree requirement on the HSM route — the salary and recognised-sponsor conditions carry the case.",
    ],
    visaTitle: "Main routes engineers discuss",
    visaIntro:
      "Highly Skilled Migrant is the workhorse for tech offers. The EU Blue Card also exists in the Netherlands but HSM is what most product companies use day to day.",
    visaRoutes: [
      {
        title: "Highly Skilled Migrant (kennismigrant)",
        body: "Employer-led IND application. 2026 gross monthly thresholds are commonly cited around €5,942 (age 30+), €4,357 (under 30), and a lower figure for certain recent graduates — always confirm on IND before negotiating.",
      },
      {
        title: "Orientation year (zoekjaar) graduates",
        body: "Some graduates use the orientation-year residence right to search, then transition into HSM at a reduced threshold when an employer sponsors them.",
      },
      {
        title: "30% ruling (tax, not a visa)",
        body: "A separate tax facility that can exempt a portion of salary for eligible incoming employees. It is not a residence permit; eligibility and duration are decided under tax rules.",
      },
    ],
    thresholds: [
      { label: "HSM age 30+ (2026, commonly cited)", value: "≈ €5,942 / month gross*" },
      { label: "HSM under 30 (2026, commonly cited)", value: "≈ €4,357 / month gross*" },
      { label: "Typical IND target (recognised sponsor)", value: "About 2–4 weeks" },
    ],
    flowTitle: "Typical Netherlands relocation flow",
    flowSteps: [
      {
        title: "Confirm recognised-sponsor status",
        body: "Ask recruiting early. If the company is not recognised, clarify whether they will become one or use another permit.",
      },
      {
        title: "Sign an offer that clears the IND salary floor",
        body: "Compare the monthly gross (excluding holiday allowance) to the current IND table for your age band.",
      },
      {
        title: "Employer files with the IND",
        body: "HR or counsel submits the HSM application. You provide passport scans and personal details; you usually do not run a separate labour-market test.",
      },
      {
        title: "Travel, BRP registration, residence card",
        body: "Collect any entry visa (MVV) if required, register with the municipality (BRP), and collect the residence document that states work is allowed as a highly skilled migrant.",
      },
    ],
    officialLabel: "IND — Highly skilled migrant",
    officialHref: "https://ind.nl/en/residence-permits/work/highly-skilled-migrant",
    visaDisclaimer:
      "Orientation only — not immigration or tax advice. *Monthly figures exclude holiday allowance and are indexed; verify on IND.nl.",
    faq: [
      {
        question: "Can I apply for Highly Skilled Migrant myself?",
        answer:
          "No. A recognised sponsor must apply. Your leverage is choosing employers that already hold that status.",
      },
      {
        question: "Do I need a degree for HSM?",
        answer:
          "The HSM route is primarily salary- and sponsor-based rather than degree-based. Employers may still require a degree for the job itself.",
      },
      {
        question: "How does Kuchup fit?",
        answer:
          "Use Kuchup to find Netherlands roles and prepare tailored CVs via MCP. Confirm IND recognised-sponsor status directly with the company before you accept.",
      },
    ],
    metaDescription:
      "Netherlands Highly Skilled Migrant visa for software engineers: recognised sponsors, 2026 salary thresholds, IND flow, Amsterdam Eindhoven hubs, and Kuchup job tracking.",
  },
  uk: {
    kicker: "United Kingdom · visas & sponsorship",
    lede:
      "UK relocation for non-UK engineers usually means a Skilled Worker visa. The employer must hold a Home Office sponsor licence and assign a Certificate of Sponsorship (CoS) before you can apply.",
    hubs: ["London", "Manchester", "Cambridge", "Edinburgh", "Bristol"],
    marketTitle: "Why software engineers target the United Kingdom",
    marketBody: [
      "London remains a dense product, fintech, and platform market, with additional hubs in Manchester, Cambridge, Edinburgh, Bristol, and elsewhere.",
      "Sponsorship is binary in practice: either the company is on the register of licensed sponsors and will assign a CoS, or they cannot use the Skilled Worker route for you.",
    ],
    sponsorTitle: "How sponsorship works in the UK",
    sponsorBody: [
      "Employers need a valid Skilled Worker sponsor licence. You can verify licensed sponsors on GOV.UK’s public register before investing in a long process.",
      "After an offer, the sponsor assigns an electronic Certificate of Sponsorship with job title, SOC occupation code, salary, and start date. You then apply for the visa using that CoS reference.",
      "Salary must meet the higher of the general threshold and the going rate for the SOC code. English language evidence (often B1/B2 CEFR depending on the rules in force) is part of the points framework.",
    ],
    visaTitle: "Main routes engineers discuss",
    visaIntro:
      "Skilled Worker is the standard sponsored employment route. Intra-company and graduate routes exist but most external hires talk about Skilled Worker.",
    visaRoutes: [
      {
        title: "Skilled Worker visa",
        body: "Requires a licensed sponsor, eligible skilled occupation, qualifying salary, and a valid CoS. GOV.UK publishes the current general salary threshold (commonly cited around £41,700 for new certificates in recent guidance — confirm the live page) and occupation going rates.",
      },
      {
        title: "SOC coding matters",
        body: "Software roles are typically coded under skilled IT occupation codes. A mismatched SOC on the CoS is a common refusal risk — the duties must match the code.",
      },
      {
        title: "New entrant discounts",
        body: "Some new graduates or early-career hires may use reduced salary rules when they qualify as new entrants under Appendix Skilled Worker. Ask the sponsor which table applies.",
      },
    ],
    thresholds: [
      { label: "Sponsor prerequisite", value: "Home Office Skilled Worker licence" },
      { label: "Key document", value: "Certificate of Sponsorship (CoS)" },
      { label: "General salary floor", value: "Check live GOV.UK threshold" },
    ],
    flowTitle: "Typical UK relocation flow",
    flowSteps: [
      {
        title: "Verify the sponsor licence",
        body: "Search the register of licensed sponsors. Confirm the company will assign a defined CoS for your role and location.",
      },
      {
        title: "Agree SOC code and salary",
        body: "Ensure the offer clears the general threshold and the going rate for the occupation code the sponsor will use.",
      },
      {
        title: "Receive the CoS and apply",
        body: "Apply online for the Skilled Worker visa with the CoS number, English evidence, passport, and any maintenance funds rules that apply unless the sponsor certifies maintenance.",
      },
      {
        title: "Enter and start work",
        body: "Travel within the permission dates on the decision. Keep right-to-work checks and your Kuchup application tracking up to date once you submit.",
      },
    ],
    officialLabel: "GOV.UK — Skilled Worker visa",
    officialHref: "https://www.gov.uk/skilled-worker-visa",
    visaDisclaimer:
      "Orientation only — not immigration advice. UK thresholds and Appendix tables change; verify on GOV.UK and with qualified counsel.",
    faq: [
      {
        question: "Can a UK startup sponsor me without a licence?",
        answer:
          "Not on Skilled Worker. They must obtain a sponsor licence first, which takes time and cost. Prefer employers that already appear on the register.",
      },
      {
        question: "Is a job ad enough proof of sponsorship?",
        answer:
          "No. You need an assigned CoS from a licensed sponsor. Ask for sponsorship confirmation in writing before resigning elsewhere.",
      },
      {
        question: "How does Kuchup help for UK roles?",
        answer:
          "Track UK openings and prepare tailored CVs with MCP. Confirm licence and CoS timing with the employer — Kuchup does not issue visas.",
      },
    ],
    metaDescription:
      "UK Skilled Worker visa for software engineers: licensed sponsors, Certificate of Sponsorship, salary and SOC rules, London hubs, and how to track sponsored roles on Kuchup.",
  },
  portugal: {
    kicker: "Portugal · visas & sponsorship",
    lede:
      "Portugal’s tech market centres on Lisbon and Porto. International engineers usually discuss the D3 highly qualified activity route, often accelerated when the employer holds Tech Visa certification from IAPMEI.",
    hubs: ["Lisbon", "Porto", "Braga", "Aveiro", "Coimbra"],
    marketTitle: "Why software engineers target Portugal",
    marketBody: [
      "Lisbon and Porto host product companies, nearshore engineering centres, and international teams that hire across borders.",
      "Cost of living and English-friendly teams attract candidates, but the immigration path depends heavily on whether the employer is Tech Visa–certified and which residence title they support.",
    ],
    sponsorTitle: "How sponsorship works in Portugal",
    sponsorBody: [
      "Tech Visa is primarily an employer certification programme (IAPMEI), not a separate visa name you apply for alone. Certified companies can issue a term of responsibility that streamlines the worker’s highly qualified residence process.",
      "If the company is not certified, you may still use a standard D3 highly qualified activity path with a qualifying contract, subject to salary and document rules.",
      "After consular approval you typically enter on a residence visa and complete biometrics / residence card steps with AIMA (the agency that succeeded SEF).",
    ],
    visaTitle: "Main routes engineers discuss",
    visaIntro:
      "Most employed software engineers compare Tech Visa–assisted D3 filings versus a standard highly qualified D3. Digital-nomad or other D-visas are different products for different situations.",
    visaRoutes: [
      {
        title: "Tech Visa–certified employer + D3",
        body: "Employer certification speeds paperwork. Contracts are often at least twelve months. Salary floors for the Tech Visa track are commonly discussed relative to multiples of the IAS social support index — confirm current IAPMEI/AIMA guidance.",
      },
      {
        title: "D3 highly qualified activity (general)",
        body: "For highly qualified employment without relying on Tech Visa certification. Salary floors are often expressed as a multiple of the national average wage; figures move with annual updates.",
      },
      {
        title: "EU Blue Card via Portugal",
        body: "Available in some highly qualified cases with EU mobility benefits later. Salary and contract-length rules differ from the national D3 track.",
      },
    ],
    thresholds: [
      { label: "Common hubs", value: "Lisbon · Porto" },
      { label: "Employer accelerator", value: "IAPMEI Tech Visa certification" },
      { label: "After entry", value: "AIMA residence permit appointment" },
    ],
    flowTitle: "Typical Portugal relocation flow",
    flowSteps: [
      {
        title: "Clarify Tech Visa vs standard D3",
        body: "Ask whether the company is IAPMEI-certified and which residence title their counsel files.",
      },
      {
        title: "Sign a qualifying highly skilled contract",
        body: "Confirm duration, salary, role description, and supporting qualification documents (degree or experience evidence).",
      },
      {
        title: "Apply at the Portuguese consulate / VAC",
        body: "Submit the D3 (or related) residence visa file. Timelines vary by post; plan for weeks to a few months end-to-end.",
      },
      {
        title: "Enter Portugal and finish AIMA registration",
        body: "Attend the AIMA appointment for your residence permit biometrics and card. Keep employment start dates realistic around that calendar.",
      },
    ],
    officialLabel: "Portugal — work and residence overview (gov resources)",
    officialHref: "https://www.portugal.gov.pt/",
    visaDisclaimer:
      "Orientation only — not immigration advice. Portugal renamed immigration agencies and updates salary indexes; verify with AIMA/IAPMEI and counsel.",
    faq: [
      {
        question: "Is Tech Visa a visa I apply for alone?",
        answer:
          "No. Tech Visa certifies employers. You still receive a residence visa/permit (often via the highly qualified / D3 family of rules) with the company’s support documents.",
      },
      {
        question: "Lisbon or Porto — does the visa change?",
        answer:
          "The national rules are the same; employers and processing logistics differ by company and consulate, not by city name alone.",
      },
      {
        question: "How does Kuchup help?",
        answer:
          "Track Portugal roles from career pages and prepare application PDFs with MCP while you confirm the employer’s Tech Visa / D3 plan.",
      },
    ],
    metaDescription:
      "Portugal Tech Visa and D3 highly qualified visa for software engineers: employer certification, Lisbon Porto hubs, AIMA steps, and relocation job tracking on Kuchup.",
  },
  ireland: {
    kicker: "Ireland · visas & sponsorship",
    lede:
      "Ireland concentrates large technology employers around Dublin (and Cork). Non-EEA software engineers usually need an employment permit — most often the Critical Skills Employment Permit — before or alongside the entry visa / stamp process.",
    hubs: ["Dublin", "Cork", "Galway", "Limerick", "Letterkenny"],
    marketTitle: "Why software engineers target Ireland",
    marketBody: [
      "Dublin hosts European headquarters and large product engineering teams for global technology companies, with additional centres in Cork and other cities.",
      "Critical Skills is designed for strategically important occupations. Software engineer / developer roles commonly appear on the Critical Skills Occupations List, which lowers the salary bar versus the general high-earner permit path.",
    ],
    sponsorTitle: "How sponsorship works in Ireland",
    sponsorBody: [
      "The employer (or sometimes the candidate, depending on permit rules) applies through the Employment Permits Online System at the Department of Enterprise, Trade and Employment (DETE).",
      "Critical Skills normally expects a job offer of at least two years for an eligible occupation at or above the published minimum annual remuneration.",
      "Trusted Partner employers can see faster processing. After the permit, you still complete the Irish residence permission / stamp steps required for your nationality and entry point.",
    ],
    visaTitle: "Main routes engineers discuss",
    visaIntro:
      "Critical Skills Employment Permit is the headline route for listed ICT occupations. General Employment Permits exist but are a different labour-market design.",
    visaRoutes: [
      {
        title: "Critical Skills Employment Permit (CSEP)",
        body: "For occupations on the Critical Skills list with a relevant degree, the minimum annual remuneration from 1 March 2026 is commonly cited at €40,904 (with a lower recent-graduate figure in some cases). Higher thresholds apply for non-listed occupations.",
      },
      {
        title: "High-earner path on Critical Skills rules",
        body: "Roles not on the critical list may still qualify at a much higher salary floor (commonly cited around €68,911) if not on the ineligible list — confirm DETE tables.",
      },
      {
        title: "Stamp progression",
        body: "Critical Skills is often discussed together with a path toward Stamp 4 after the qualifying period, which widens labour-market freedom. Exact stamp rules depend on immigration permission practice — verify with ISD guidance.",
      },
    ],
    thresholds: [
      { label: "CSEP list + degree (from Mar 2026, commonly cited)", value: "≈ €40,904 / year" },
      { label: "Typical offer length", value: "At least 2 years" },
      { label: "Processing (indicative)", value: "Often several weeks; Trusted Partners faster" },
    ],
    flowTitle: "Typical Ireland relocation flow",
    flowSteps: [
      {
        title: "Secure a two-year eligible offer",
        body: "Confirm the occupation maps to the Critical Skills list and that salary clears the current DETE minimum for your path.",
      },
      {
        title: "File the employment permit",
        body: "Submit via Employment Permits Online with contracts, passport bio page, and qualification evidence. Fees and who may pay them are set in DETE rules.",
      },
      {
        title: "Entry visa / residence permission",
        body: "Depending on nationality, obtain any required entry visa and then the appropriate Irish residence stamp/permission to work for that employer.",
      },
      {
        title: "Start work and plan the long game",
        body: "Critical Skills conditions tie you to the permitted employment initially. Track renewals and any later Stamp 4 eligibility on official timelines.",
      },
    ],
    officialLabel: "DETE — Critical Skills Employment Permit",
    officialHref:
      "https://enterprise.gov.ie/en/what-we-do/workplace-and-skills/employment-permits/permit-types/critical-skills-employment-permit/",
    visaDisclaimer:
      "Orientation only — not immigration advice. Irish permit salaries and lists update (including March 2026 changes); verify on official DETE / ISD pages.",
    faq: [
      {
        question: "Are software engineers on the Critical Skills list?",
        answer:
          "Software engineer and software developer occupations are commonly included on the Critical Skills Occupations List, but you must match the listed title and qualification rules for your permit.",
      },
      {
        question: "Can I change employers freely on Critical Skills?",
        answer:
          "Permission is tied to permit conditions. Rules on changing roles have evolved — read current DETE guidance rather than relying on older forum advice.",
      },
      {
        question: "How does Kuchup help for Ireland?",
        answer:
          "Find Ireland roles, track applications, and tailor CVs with MCP while the employer runs the Critical Skills filing.",
      },
    ],
    metaDescription:
      "Ireland Critical Skills Employment Permit for software engineers: 2026 salary thresholds, DETE flow, Dublin Cork hubs, Trusted Partners, and relocation tracking on Kuchup.",
  },
};
