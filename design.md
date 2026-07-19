# Design — Kuchup / Relocation Jobs

A locked design system for this app. Every page redesign reads this file before
emitting code. Do not regenerate per page — extend or amend this file when the
system needs to grow.

## Genre

modern-minimal with an optimistic, human relocation tone. The system should
feel like an open door: warm light, clear guidance, approachable typography,
and enough energy to help people act without making the interface loud.

## Macrostructure family

- Marketing pages: Feature-stack / long-document with open spacing, soft
  elevation, and direct orange actions
- App pages: Workbench (dense board, filters, cards) — function carries the page
- Content pages: typography only

## Theme

Warm Horizon: a light palette derived from the Kuchup bird logo and the idea of
open skies, movement, and opportunity. Interaction and shape borrow from
Hallmark Hum, but the Hum pear/cyan/coral palette is deliberately not used.

- `--color-paper`   #fcfaf7 (warm ivory)
- `--color-paper-2` #f2f7fa (open-sky surface)
- `--color-paper-3` #e4f0f6
- `--color-ink`     #0e3a69 (logo navy)
- `--color-ink-2`   #345c7c
- `--color-muted`   #5d7488
- `--color-rule`    #a9c1d1
- `--color-accent`  #ff6b35 (logo orange)
- `--color-accent-hover` #ff7f52
- `--color-accent-2` #0e3a69 (secondary brand role)
- `--color-accent-ink` #082743 (AA text on orange)
- `--color-focus`   #ff6b35

Paper mode: **light** warm paper with sky-tinted supporting surfaces. Dark navy
is reserved for readable text and high-emphasis structure—never large
background fields. No unrelated
aubergine, oxblood, purple, cyan, or competing multi-accent palette.

## Typography

- Display: Lexend, weight 600–700, style normal
- Body:    Manrope, weight 400–600
- Mono:    JetBrains Mono, weight 400–500
- Display tracking: -0.035em (hero) / -0.025em (section)
- Type scale anchor: `--text-display` = clamp(2.25rem, 4vw + 1rem, 3.5rem)

## Spacing

4-point named scale in `design-tokens.css`. Pages must use named tokens
(`var(--space-md)`), never raw values for system rhythm.

## Motion

- Easings: `--ease-out: cubic-bezier(0.16, 1, 0.3, 1)`; `--ease-in`, `--ease-in-out`
- Reveal pattern: fade + short slide on marketing; none required on app chrome
- Reduced-motion fallback: opacity-only, ≤ 150 ms

## Microinteractions stance

- Silent success (celebratory toasts: never)
- Focus delay 0 ms; hover transitions ≤ 200 ms
- Press feedback: translateY(1px) / scale on `:active`
- Touch targets ≥ 44px

## CTA voice

- Primary CTA: orange fill (`--color-accent`), ink text (`--color-accent-ink`),
  pill radius, a restrained solid orange edge-shadow, and a physical press
- Secondary CTA: paper fill, 1px sky-blue outline, navy text, pill radius

## Hum adaptations

- Rounded, welcoming surfaces and pills in the Kuchup palette
- Primary buttons lift 1px on hover and press down 2px on active
- Cards deepen their tint and lift on hover; reduced motion removes translation
- Marketing workflow pages use a numbered narrative rail
- Orange owns primary action; sky-tinted surfaces support content; navy carries
  trust and readability
- No Hum pear, coral, lavender, or multi-accent rainbow

## Per-page allowances

- Marketing pages MAY use enrichment (Tier-A CSS art, Tier-B SVG).
- App pages MUST NOT use enrichment — function carries the page.
- Content pages: typography only.

## What pages MUST share

- The wordmark / logotype (KUCHUP bird)
- Logo navy `#0e3a69` for ink and high-emphasis structure
- Brand orange as the clear primary accent (≤ 5 % per viewport as fill)
- Display + body fonts above
- CTA voice (button shape, border-radius, padding rhythm)
- 1px boundaries, rounded surfaces, and restrained soft elevation
- Tactile primary-button press feedback

## What pages MAY differ on

- Macrostructure within the page-type family
- Hero archetype on marketing only
- Enrichment — marketing only, Tier-A or Tier-B

## Exports

Canonical CSS lives in:

- `relocation_jobs/static/design-tokens.css` (panel)
- `homepage/app/design-tokens.css` (marketing — keep in lockstep)

### tokens.css

```css
:root {
  --color-paper:      #fcfaf7;
  --color-paper-2:    #f2f7fa;
  --color-paper-3:    #e4f0f6;
  --color-ink:        #0e3a69;
  --color-ink-2:      #345c7c;
  --color-muted:      #5d7488;
  --color-rule:       #a9c1d1;
  --color-accent:     #ff6b35;
  --color-accent-ink: #082743;
  --color-focus:      #ff6b35;

  --font-display: "Lexend", sans-serif;
  --font-body:    "Manrope", sans-serif;
  --font-mono:    "JetBrains Mono", ui-monospace, monospace;

  --space-3xs: 0.25rem;  --space-2xs: 0.5rem;  --space-xs: 0.75rem;
  --space-sm:  1rem;     --space-md:  1.5rem;  --space-lg: 2rem;
  --space-xl:  3rem;     --space-2xl: 4.5rem;  --space-3xl: 7rem;

  --radius-card: 16px; --radius-button: 999px; --radius-input: 12px;
  --shadow-card: 0 8px 24px rgba(14, 58, 105, 0.10);
}
```
