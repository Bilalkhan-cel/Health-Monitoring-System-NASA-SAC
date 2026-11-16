# AstroVital launch video: plan

## What it is
AstroVital is a crew health system for long space missions: three quick daily checks (heart, bones and
muscle, mind), a glowing 3D body twin, an AI flight doctor (Dr. NOVA) that knows your data, and a
Mission Control view for the flight surgeon. It runs on one computer, offline-first.

- **For:** astronauts far from Earth (and the flight surgeon watching the crew).
- **Sets it apart:** built for the comms delay. When Earth is 22 minutes away, the doctor has to be on board.
- **Most impressive claim (the app's own):** "Built for when Earth is 22 minutes away."
- **Visual hook:** the app's real WebGL Earth with NASA's ISS model, live.
- **Real flow shown:** landing → Today (scores + 3D twin) → ask Dr. NOVA → Mission Control.
- **Share caption:** see `share-copy.txt`.

## Angle
Cinematic and restrained, like a mission trailer. The space setting carries the drama, so the copy stays
quiet and comes from the product itself. Every scene is the real app rendered headless, frame by frame on
a virtual clock (real three.js Earth, ISS, hologram twin, real CSS and Geist fonts).

## Tone and identity
- Tone: `cinematic`, restrained. Dips through black between scenes, slow camera pushes.
- Colours from `theme.css`: black `#000`, text `#F2F4F7`, grey second lines `#8E97A6`, glow `#7CF3FF`,
  status green `#2EE59D`, blue `#3B9EFF`, amber `#FFC53D`.
- Type: Geist (headlines 500, tight tracking), Geist Mono for small captions. The app's `.headline` +
  `.headline__second` two-tone pattern for every overlay line.

## Music
120 BPM (beat 0.5 s, bar 2 s), D minor. 48 beats = 24.0 s. Warm pad from frame 0, sub pulse and soft
kick enter at the reveal, hats from Today, a lift into the outro, a low hit and a tail. Every cut is on a
beat; scene-change whooshes and UI ticks are tuned to D and sit under the music.

## Storyboard (30 fps)

| # | Time | Beats | Scene | On screen |
|---|---|---|---|---|
| 1 | 0.0–3.5 | 7 | Hook | Real hero Earth + ISS, camera easing back. Hero copy hidden. Centered: "Built for when Earth is / *22 minutes away.*" |
| 2 | 3.5–7.0 | 7 | Reveal | Same shot continues; hook line lifts away, the real hero copy rises in: tag "Crew health system for long missions", "Beyond Earth. / *Always in health.*" |
| 3 | 7.0–11.5 | 9 | Today | Real dashboard as Cmdr. Sara Whitman (seed persona), camera pushing in on scores and the 3D twin. Simulated tap on the Heart pill. Lower third: "Three quick checks. / *A few minutes a day.*" |
| 4 | 11.5–17.5 | 12 | Dr. NOVA | Real Dr. NOVA page. The question "Why is my heart rate up today?" is typed and sent, the orb thinks, the answer streams in (the landing page's own sample answer, trimmed), "What Dr. NOVA sees" alongside. |
| 5 | 17.5–20.5 | 6 | Mission Control | Flight-surgeon view: "Mission Control. / *The whole crew at a glance.*", crew cards land one by one. |
| 6 | 20.5–24.0 | 7 | Outro | Earth again, wider. "Astronaut, are you / *mission-ready?*" + AstroVital wordmark + "Runs on one computer · offline-first · prototype, not a medical device". |

## Data and privacy
Crew names are the project's fictional seed personas. Vitals come from the project's own wearable
emulator and seed history. The Dr. NOVA exchange is staged in the real page with the landing page's sample
copy (no cloud call). No secrets, hostnames or real people appear.
