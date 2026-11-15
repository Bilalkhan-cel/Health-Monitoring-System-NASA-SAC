# Dr. NOVA on OpenHome: setup handoff

Everything you need to connect the voice doctor to your own OpenHome account. Until you do,
Dr. NOVA works in **practice mode** (`OPENHOME_MOCK=true`): text and voice are answered by the
offline rules engine and the chip on the Dr. NOVA page says **OFFLINE RULES**.

You need:

- an OpenHome account at https://app.openhome.com
- `cloudflared` (free, no Cloudflare account needed for a quick tunnel):
  `winget install --id Cloudflare.cloudflared`, or download it from
  https://github.com/cloudflare/cloudflared/releases
- AstroVital installed (`python scripts/setup.py`)

## How the pieces talk

```
Browser ──(your mic, WebSocket)──► Flask ──(voice stream)──► OpenHome cloud (Dr. NOVA agent)
                                                                  │
          Flask /api/openhome/context  ◄──(HTTPS via tunnel)──────┘  "AstroVital Health Context" Ability
```

- Your browser never talks to OpenHome directly: Flask holds the API key.
- The Ability running in OpenHome's cloud fetches the logged-in astronaut's data from
  `/api/openhome/context`, so Flask must be reachable from the internet. The tunnel exposes **only**
  `/api/openhome/*` and `/healthz`. The login page, the dashboard and the device routes stay local
  (the host guard refuses them on the tunnel host).
- The bridge is protected by a shared token (`OPENHOME_BRIDGE_TOKEN`) that the build script
  generates and rotates on every build. It only answers while an astronaut has the Dr. NOVA page open.

## Step 1: start the tunnel

Start AstroVital (`python run.py`), then in a second terminal:

```bash
cloudflared tunnel --url http://localhost:5000
```

It prints a URL like `https://random-words.trycloudflare.com`. Check it works: open
`https://random-words.trycloudflare.com/healthz` in a browser, which should show `{"ok": true, ...}`.
`https://…/login` should show a 404 page. That is the host guard working.

Put the URL in `.env`:

```
PUBLIC_BASE_URL=https://random-words.trycloudflare.com
```

A quick tunnel gets a **new URL each time** you start it. See "When the tunnel URL changes" below.

## Step 2: create the Dr. NOVA agent

In app.openhome.com:

1. **Personalities → New.** Name: `Dr. NOVA`. Pick a calm, warm voice.
2. Paste the persona. Print it with:
   ```bash
   python scripts/build_openhome_ability.py --persona
   ```
   (the same text is in `config/dr_nova_persona.md`).
3. Add this line at the end of the personality instructions:
   > At the start of every conversation, run the AstroVital Health Context ability before answering any health question.
4. Copy the **agent id** and your **API key** (Settings → API Keys) into `.env`:
   ```
   OPENHOME_API_KEY=...
   OPENHOME_AGENT_ID=...
   OPENHOME_MOCK=false
   ```

## Step 3: build and upload the Ability

```bash
python scripts/build_openhome_ability.py
```

This renders `build/openhome_ability/main.py` with your `PUBLIC_BASE_URL` and a fresh bridge token,
validates it against OpenHome's ability rules, writes `build/astrovital_health_context.zip`, saves the
new token into `.env` and prints these same steps. **Never commit `build/`**: the zip contains the token.

In OpenHome: **Abilities → Add Custom Ability**, upload `build/astrovital_health_context.zip`, and use
these trigger words:

```
doctor nova, dr nova, check my health, how am i doing, review my vitals, health report,
log my sleep, i feel, my heart, my head hurts
```

Install the Ability into the Dr. NOVA agent. (If you have the `openhome` CLI installed,
`python scripts/build_openhome_ability.py --push` uploads it for you.)

## Step 4: restart and test

1. Restart `python run.py` (it must pick up the new bridge token from `.env`). The boot checklist
   should say "OpenHome key and agent id set".
2. Log in as `AST-1001`, open **Dr. NOVA** and ask something. The engine chip on the reply should say
   **OPENHOME**.
3. Type "How am I doing?". The answer should quote your real numbers (heart rate, sleep, today's tasks).
4. Press the microphone and say "Dr. Nova, how am I doing?".
5. Say "log 6 hours sleep". It should appear on Today.

If replies still say **OFFLINE RULES**, check that `OPENHOME_MOCK=false` and that the key and agent id are right. If the agent answers but knows nothing
about you, the Ability cannot reach the tunnel: check `PUBLIC_BASE_URL`, that `cloudflared` is still
running, and that the Dr. NOVA page is open (the bridge answers only during a consultation).

## When the tunnel URL changes

Either rebuild and re-upload (steps 3–4), or, to avoid re-uploading, save two values in OpenHome
**Settings → API Keys** (third-party keys). The Ability reads these first:

| Name | Value |
|---|---|
| `astrovital_url` | the current tunnel URL |
| `astrovital_bridge_token` | the `OPENHOME_BRIDGE_TOKEN` value from `.env` |

A named Cloudflare tunnel (needs a free Cloudflare account) keeps the same URL across restarts.

## What Dr. NOVA can see

Only the data listed under "What Dr. NOVA sees" on the Dr. NOVA page: the current astronaut's latest
vitals with their status words, trends, baselines, recent session summaries, sleep and active alerts.
No transcripts and no other crew member's data. Voice audio goes to OpenHome's cloud; everything
else stays on this computer.

## Optional fallback LLM

If OpenHome is unreachable, text chat can fall back to another LLM when `FALLBACK_LLM_API_KEY`
(plus `FALLBACK_LLM_BASE_URL` and `FALLBACK_LLM_MODEL`) is set in `.env`. Without them, the offline rules engine answers. The chip always shows which engine replied.
