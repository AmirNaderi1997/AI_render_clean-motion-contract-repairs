# Shared Telegram/API relay

Recovered verbatim source from production deployment
`dpl_946V71VyXSf2SVPdrmmKiUEVKnSC` on 2026-10-23 before modifying ElevenLabs.
Project: `rafiei-telegram-api-relay`, team `rezas-projects-00aa9a21`.

Only `api/elevenlabs.js` is changed: authenticated GET voice/model discovery,
allow-listed voice search/pagination query forwarding, private/no-store GET
responses. Existing speech, transcription, Gemini, video analysis, upload and
generic proxy behavior is retained. No environment secrets are in these files.

Run offline regression tests with `node --test elevenlabs.test.mjs`. Tests mock
the upstream fetch; they never generate audio or contact a provider.

Stage production without aliases, verify authenticated discovery and negative
authentication tests, then promote that tested deployment. Keep the preceding
deployment available for rollback. Do not delete or change other project routes.

## Published fix (2026-10-23)

- Deployment: `dpl_D96WTMj6EtaTPr3si7E5EtavEzJq`, production READY.
- Main domain: `https://rafiei-telegram-api-relay.vercel.app`.
- Verified live: authenticated v1 voices, v2 voices (including Persian filter),
  and models all HTTP 200; no key HTTP 401.
- 27 account voices, zero `language=fa` matches, 11 models. Persian-supporting
  model IDs: `eleven_v4`, `eleven_v4_turbo`, `eleven_v3`, `eleven_v3_conversational`.
- Five offline regression tests pass; no synthesis or transcription was submitted.
- This is a CLI source patch, not a newly committed Git release. All files except
  `api/elevenlabs.js` match the preceding deployment's source hashes exactly.
