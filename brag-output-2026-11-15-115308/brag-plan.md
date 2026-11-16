# AstroVital: every module, one reel

## Brief from the user
"Don't just copy-paste UI. Cover all modules." So this cut is a designed motion reel. Each module gets
its own scene where its real component is lifted out of the running app (real markup, CSS, canvases,
3D and JS) and recomposed on a clean stage with kinetic type, instead of panning over full pages.

## What it is
A crew health system for long space missions: a live ESP32 wearable and heart check, camera rep
counting for bones and muscle, a private voice check-in for the mind, a glowing 3D body twin, Dr. NOVA
(an AI flight doctor that knows your data), history with a Downlink Report, cautious alerts that
escalate, and Mission Control for the flight surgeon. One computer, offline-first.

- **For:** astronauts far from Earth, and the flight surgeon watching the crew.
- **Sets it apart:** built for the comms delay. When Earth is 22 minutes away, the care has to be on board.
- **Hook:** the live 3D Earth and ISS, "Earth is / 22 minutes away."
- **Punchline:** "Astronaut, are you mission-ready?"

## Tone and identity
`default` pushed toward a product reel: punchy, clean, fast cuts on the beat, every module a chapter.
- One stage template for every module: mono kicker (`02 / 08 · HEART`), a two-tone Geist headline taken
  from the module's own page title, a mono caption with what runs where, and the real component on a
  floating card that tilts in from the right with a status-coloured glow.
- A **module rail** at the bottom stays on screen from the reveal to Mission Control; the active module
  slides along it, so the viewer always knows where they are in the system.
- Colours from `theme.css` (black, `#F2F4F7`, grey `#8E97A6`, glow `#7CF3FF`, status green/blue/amber/red).

## Music
120 BPM (15 frames a beat), D minor, 61 beats = 30.5 s. Hook: pad + sub + bells. Reveal: hit, then a
driving four-on-the-floor with off-beat hats, 8th-note bass and a 16th-note pluck arp. A one-beat
filter dip on every module cut (all on beats), a riser into Mission Control's last beat, home chord and
bells in the outro. UI sounds (taps, reps, typing, heat-map cells) are pitched to D and on the 16th grid.

## Storyboard (30 fps)

| # | Time | Beats | Module | Real component on stage | Headline (module's own copy) |
|---|---|---|---|---|---|
| 1 | 0.0–3.0 | 6 | Hook | Live WebGL Earth + NASA ISS model | "Earth is / 22 minutes away." |
| 2 | 3.0–5.5 | 5 | Reveal | Logo, "Crew health system for long missions", the module rail flies in | "AstroVital" |
| 3 | 5.5–8.0 | 5 | Heart + wearable | Live check: beating heart, BPM, real ECG synth trace, latest readings rows | "Heart check. / Seven quiet minutes." |
| 4 | 8.0–10.5 | 5 | Bones & muscle | Camera stage: skeleton overlay (the app's own drawing style), reps counting, cue, form HUD | "Bones & muscle. / Load them every day." |
| 5 | 10.5–13.0 | 5 | Mind | Listening stage: voice ring, timer, level meter, a real check-in question | "How are you, / really?" |
| 6 | 13.0–15.5 | 5 | Body twin | 3D hologram twin, status tags, tap → system card | "Tap your body. / See how it's doing." |
| 7 | 15.5–19.5 | 8 | Dr. NOVA | Chat: question typed and sent, orb thinks, answer streams | "A doctor who knows you. / Just ask." |
| 8 | 19.5–22.0 | 5 | History | Readiness heat map fills day by day, trend chart, tap "Downlink Report (PDF)" | "Your history. / Every check, every day." |
| 9 | 22.0–24.5 | 5 | Alerts | Real alert bar (critical BP scenario) + notifications | "Get help now. / Even 14 minutes from Earth." |
| 10 | 24.5–27.0 | 5 | Mission Control | Crew cards land one by one | "Mission Control. / The whole crew at a glance." |
| 11 | 27.0–30.5 | 7 | Outro | Earth, wider | "Astronaut, are you / mission-ready?" + wordmark + "Runs on one computer · offline-first · prototype, not a medical device" |

30.5 s is longer than the usual 15–25 s because the brief asks for every module; each module scene is
2.5 s with a headline of four to six words (settled by 0.5 s, readable for 2 s).

## Data and honesty
Crew names and vitals are the project's fictional seed personas and wearable emulator. The alert uses
the app's own "Critical BP event, 14-min comms delay" demo scenario text, rendered in the real alert bar
without changing the database. The Dr. NOVA answer is the landing page's own sample, staged in the real
chat (no cloud call). The skeleton is drawn with the app's own overlay style from synthetic keypoints,
because no camera is attached. No secrets or real people.
