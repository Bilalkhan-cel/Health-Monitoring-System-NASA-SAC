# AstroVital Health Context (OpenHome Ability)

Gives the Dr. NOVA personality the logged-in astronaut's real data from AstroVital.

- On trigger it calls `GET {ASTROVITAL_URL}/api/openhome/context` with the header `X-AstroVital-Token`.
- It runs a voice loop: the astronaut talks, the agent's LLM answers with the Dr. NOVA persona and the
  astronaut context as its system prompt, and the answer is spoken.
- "Log 6 hours sleep", "log my mood as 7" and "log 250 ml of water" are saved through
  `POST {ASTROVITAL_URL}/api/openhome/log`.
- The context is refreshed every 2 minutes. Exit phrases: "that's all", "thanks", "goodbye", "end consultation".
- It always calls `resume_normal_flow()` when it ends.

AstroVital answers the bridge only while the astronaut has Dr. NOVA open (an active session with a
heartbeat in the last 45 s); otherwise it answers `404 no_active_session`. Only one astronaut can use the
voice doctor at a time (prototype limit).

Do not edit `main.py` by hand: `python scripts/build_openhome_ability.py` renders it from
`main.py.tmpl`, the persona and a freshly rotated bridge token.

Optional: instead of the rendered values, save `astrovital_url` and `astrovital_bridge_token` in
OpenHome **Settings → API Keys** (third-party keys). Values saved there win.
