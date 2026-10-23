# Social relay (Vercel)

The editor's server cannot reach Instagram, YouTube, TikTok, X or Vimeo. This function runs **yt-dlp on Vercel** (outside the
blocked network), downloads a reference video and streams it back; the editor then analyses it frame by frame.

Deployed as the Vercel project `editorgpt-social-relay` -> `https://editorgpt-social-relay.vercel.app/api/index`.

| | |
|---|---|
| `GET /api/index` | health, yt-dlp version |
| `POST /api/index` `{"url": "https://..."}` + header `x-relay-secret` | the video (<= 80 MB, <= 180 s), streamed |

Editor environment: `SOCIAL_RELAY_URL`, `SOCIAL_RELAY_SECRET` (same value as `RELAY_SECRET` on Vercel).

## What works from Vercel's network (tested 2026-10-23)
- TikTok: works without login.
- YouTube / Vimeo / Instagram: the sites ask datacenter IPs to sign in. Give the relay a logged-in session:
  1. export cookies from a logged-in browser as Netscape `cookies.txt` (extension "Get cookies.txt LOCALLY");
  2. `base64 -i cookies.txt | tr -d '\n' | npx vercel env add YTDLP_COOKIES_B64 production`;
  3. `npx vercel deploy --prod`.
  Use a throwaway account: the cookies live in Vercel's encrypted environment.
- Without a working login the editor says so and asks the user to upload the file; it never pretends the reference was followed.

Update yt-dlp (sites change often): bump `yt-dlp` in `requirements.txt` and redeploy.
