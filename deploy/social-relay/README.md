# Social relay (Vercel)

The editor's server cannot reach Instagram, YouTube, TikTok, X or Vimeo. This function runs **yt-dlp on Vercel** (outside the
blocked network), downloads a reference video and streams it back; the editor then analyses it frame by frame.

Deployed as the Vercel project `editorgpt-social-relay` -> `https://editorgpt-social-relay.vercel.app/api/index`.

| | |
|---|---|
| `GET /api/index` | health, yt-dlp version |
| `POST /api/index` `{"url": "https://..."}` + header `x-relay-secret` | the video (<= 80 MB, <= 180 s), streamed |

Editor environment: `SOCIAL_RELAY_URL`, `SOCIAL_RELAY_SECRET` (same value as `RELAY_SECRET` on Vercel).

## Instagram through GetInSaver (no cookies)
Instagram asks datacenter IPs to log in, so yt-dlp alone needs cookies that expire. When `GETINSAVER_API_KEY` is set on Vercel, Instagram links
(posts, reels, stories, highlights) are resolved through the GetInSaver API (`POST https://developers.getinsaver.com/v1/resolve`, Bearer key,
`items[].url`), the file is downloaded from Vercel (the Iran server cannot reach Instagram's CDN), and yt-dlp is only the fallback. The key lives in
Vercel's encrypted environment and never reaches the editor. One credit per post/reel, two per story/highlight; failed requests are refunded.

```
cd deploy/social-relay
npx vercel env add GETINSAVER_API_KEY production        # paste the key (gis_live_...) when asked
npx vercel deploy --prod
curl https://editorgpt-social-relay.vercel.app/api/index  # {"ok": true, ..., "getinsaver": true}
```

## Size of what is sent
The editor's server pulls the file from Vercel at roughly 20 KB/s, so the relay sends a small proxy copy (ffmpeg from `imageio-ffmpeg`: at most 45 s, 480p, a few MB;
the original size is in `x-source-original-bytes`). If ffmpeg is unavailable the original goes through, as before.

## What works from Vercel's network (tested 2026-10-23)
- TikTok: works without login.
- YouTube / Vimeo / Instagram: the sites ask datacenter IPs to sign in. Give the relay a logged-in session:
  1. export cookies from a logged-in browser as Netscape `cookies.txt` (extension "Get cookies.txt LOCALLY");
  2. `base64 -i cookies.txt | tr -d '\n' | npx vercel env add YTDLP_COOKIES_B64 production`;
  3. `npx vercel deploy --prod`.
  Use a throwaway account: the cookies live in Vercel's encrypted environment.
- Without a working login the editor says so and asks the user to upload the file; it never pretends the reference was followed.

Update yt-dlp (sites change often): bump `yt-dlp` in `requirements.txt` and redeploy.
