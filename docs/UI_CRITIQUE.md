# UI critique and accessibility audit

Two passes over the finished interface: a design critique against the owner's mockups
(`ASTROVITAL UI Mockups.pdf`, 10 screens) and usability heuristics, and a WCAG 2.2 AA accessibility
audit. Each finding says what changed, or why it was left as it is.

## 1. Design critique

The mockups set the look: black canvas, white type with a grey second headline line, a left icon
rail, white pill buttons and colour reserved for status. Where a mockup conflicted with a hard rule of
the specification (no source labels, no sign-up, honest copy), the rule won.

| # | Finding (heuristic) | Resolution |
|---|---|---|
| C1 | Icon-only rail is hard to learn (recognition over recall) | Every rail item shows its label on hover and focus, has an accessible name, and the menu button keeps labels open (D16). On phones the rail becomes a bottom bar. |
| C2 | Mockup's blue "Ask Dr. NOVA" button collides with blue = "Okay" (consistency) | White pill instead; colour is only ever a status (D20). |
| C3 | Mockup shows a "Register" link (match with the real world) | Removed: the crew comes from Mission Control; a sign-up page would be a dead end. |
| C4 | Numbers without meaning (help users recognise) | Every value carries a status word and icon, a "your usual" line and an ⓘ explanation in plain language. |
| C5 | Separate mental/physical labels in the mockup vs Heart / Mind / Bones & muscle elsewhere (consistency) | One vocabulary everywhere: nav, twin hotspots, cards, History filters, Mission Control (D19). |
| C6 | Landing hero copy fought the 3D scene | Earth sits low and the ISS drifts top-left, pulled in on narrow screens so it never covers the headline or leaves the frame (D66). |
| C7 | Hero buttons could stay invisible when the intro animation never ran (error prevention) | The intro completes itself after 3 s if GSAP's ticker is paused; reduced motion skips it. |
| C8 | Gamification can pull attention from health (aesthetic and minimalist design) | XP bars are kept off the main screens; streak in Today's tasks, badges in Settings. XP never depends on the measured values. |
| C9 | History filters dominate a phone screen | Accepted for now: the filters stack and stay usable; the heatmap and timeline follow. A collapsible filter bar is a possible refinement. |
| C10 | The Downlink Report repeated the status word ("Get help now. Get help now: …") | Fixed: one sentence after the score. |
| C11 | Mission Control shows the readiness number on the grid in an early draft | Replaced by colour plus the status word; the number is never shown to the surgeon (spec Section 16, D64). |

## 2. Accessibility audit (WCAG 2.2 AA)

Method: the five layers of the accessibility-audit skill. Layer 1 is an automated scan of all 13
rendered page types (landing, login, Today, Heart, Body, Mind, Dr. NOVA, History, Notifications,
Settings, Mission Control, crew detail, 404) for missing labels, alt text, empty controls, heading
order, landmarks and the skip link. Layer 4 includes contrast computed from the theme tokens. Layers
2 and 5 (keyboard, flows) were done by reading the markup and driving the pages in the browser pane.
Layer 3 (screen reader) is a code review of names, roles and live regions only: no screen reader was
run on this machine.

### Layer 1: automated scan

All 13 pages: one `h1`, no skipped heading levels, `<main>` landmark and a skip link, every input
labelled, no empty buttons or links, every image has `alt`. **No issues.**

### Layer 4: contrast (computed)

| Token | On black | On card | Result |
|---|---|---|---|
| text `#F2F4F7` | 19.1 | 17.6 | pass |
| text-2 `#A3ABB8` | 9.1 | 8.4 | pass |
| text-3 `#8E97A6` (captions) | 7.1 | 6.6 | pass |
| good / okay / watch / alert as text | 12.8 / 7.5 / 13.3 / 6.5 | ≥ 6.0 | pass |
| primary pill (dark on white) | 18.4 | | pass |
| **white on the red alert bar `#FF4D6D`** | **3.2** | | **fail 1.4.3** |

### Findings

| # | Issue | WCAG | Severity | Fix |
|---|---|---|---|---|
| A1 | White text on the red alert bar, bell badge, recording mic and delete button: 3.2:1 | 1.4.3 AA | High | New `--alert-fill: #C8143A` for red behind white text (5.8:1; 3.6:1 against black for 1.4.11). `--alert` stays for red text and dots. |
| A2 | History calendar squares 18 px with 4 px gaps | 2.5.8 AA | Moderate | 20 px squares, 24 px centre spacing; every day is also reachable from the timeline. |
| A3 | Mission Control system dots carried status by colour alone (word only for screen readers) | 1.4.1 A | High | The status word is now visible next to each system. |
| A4 | Fixed landing nav and phone bottom bar could cover a focused element | 2.4.11 AA | Moderate | `scroll-padding-top` on the landing, `scroll-padding-bottom` on app pages at phone width. |
| A5 | Notifications "All / Unread" links used `aria-pressed` | 4.1.2 A | Low | `aria-current="page"` only; styled the same as the pressed state. |
| A6 | Reduced motion only followed the OS setting | 2.3.3 AAA | Low | Settings → Reduce motion applies the same calm mode in the app (CSS and the 3D scenes). |

### Checked and passing

- **Keyboard:** global `:focus-visible` outline; native `<dialog>` for every modal (focus moves in,
  Esc closes); account menu closes on Esc and returns focus; the 3D twin's drag rotation has a
  button alternative (system pills), so 2.5.7 passes; switches and segmented controls are native
  checkboxes and radios.
- **Status by more than colour:** status pills, notifications, the alert bar, History entries and
  the twin's tags all pair colour with an icon and a word. The heatmap is colour-coded but every
  square has an accessible name with the date and score, a tooltip, a legend and a day dialog.
- **Live regions:** the alert bar is `role="alert"`; toasts, saved messages, the trend summary and the
  demo card use `aria-live="polite"`.
- **Forms:** visible labels, errors in text next to the field, the delete confirmation asks for a typed
  word (no cognitive test at login: an Astro ID only, 3.3.8).
- **Reflow:** no horizontal scroll at 375 px on any page checked (History, Settings, Notifications,
  landing, Today).
- **Motion:** `prefers-reduced-motion` and the in-app setting stop the intro, the breathing orb, the
  voice bars and the twin's heartbeat.

### Not covered

- Real screen-reader runs (NVDA or VoiceOver), and 200 % text zoom by hand.
- The camera and microphone flows with assistive technology.
