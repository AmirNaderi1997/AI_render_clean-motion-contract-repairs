# Social relay (Vercel)

The editor's server cannot reach Instagram, YouTube, TikTok, X or Vimeo. This function runs **yt-dlp on Vercel** (outside the
blocked network), downloads a reference video and streams it back; the editor then analyses it frame by frame.

Deployed as the Vercel project `editorgpt-social-relay` -> `https://editorgpt-social-relay.vercel.app/api/index`.

| | |
|---|---|
| `GET /api/index` | health, yt-dlp version |
| `POST /api/index` `{"url": "https://..."}` + header `x-relay-secret` | the video (<= 80 MB, <= 180 s), streamed |

Editor environment: `SOCIAL_RELAY_URL`, `SOCIAL_RELAY_SECRET` (same value as `RELAY_SECRET` on Vercel).

## Order of attempts
1. **yt-dlp with logged-in cookies** (`YTDLP_COOKIES_B64`) for every supported site. Instagram and YouTube refuse datacenter IPs without a login.
2. **GetInSaver** (`GETINSAVER_API_KEY`) as the fallback, for Instagram links only (posts, reels, stories, highlights). One credit per post/reel, two per
   story/highlight; failed requests are refunded. The key lives in Vercel's encrypted environment and never reaches the editor.
3. Otherwise the editor tells the person why and asks them to upload the reference video.

The relay sends a small proxy copy (ffmpeg: at most 45 s, 480p, a few MB; the original size is in `x-source-original-bytes`): the editor's server pulls
files from Vercel at roughly 20 KB/s, and a function stops after 300 s.

## Adding the cookies (Instagram + YouTube)
Use **throwaway accounts** (never your main ones): the cookies live in Vercel's encrypted environment and give access to those accounts.

1. **Export from a private window**, one site at a time. YouTube rotates its cookies in an open browser tab, which would invalidate the export:
   open a private/incognito window, log in to the throwaway account, export, then close the window and do not use that session again.
   Use the extension "Get cookies.txt LOCALLY" (Chrome/Edge/Firefox), open the site while logged in, click the extension, **Export** (Netscape format):
   `instagram.com` -> `instagram.txt`, `youtube.com` -> `youtube.txt`.
2. **Merge into one file** (a single Netscape header line first):
   ```
   (head -n 1 instagram.txt; tail -n +2 instagram.txt; tail -n +2 youtube.txt) > cookies.txt
   ```
3. **Encode and store** as a sensitive Vercel variable (the pipe passes the value without printing it):
   ```
   cd deploy/social-relay
   base64 -i cookies.txt | tr -d '\n' | npx vercel env add YTDLP_COOKIES_B64 production --sensitive
   ```
   Vercel allows 64 KB for all variables together: if `wc -c` of the base64 text is over about 40000, export only the cookies of the two sites (not "all sites").
4. **Delete the local files** (`rm cookies.txt instagram.txt youtube.txt`) and **redeploy**: `npx vercel deploy --prod`.
5. **Check**: `curl https://editorgpt-social-relay.vercel.app/api/index` should show `"getinsaver": true` (fallback ready); then ask the editor for a reel or a
   YouTube link. The relay answer's `x-source-extractor` header says which path delivered it (`Instagram`/`Youtube` = yt-dlp, `getinsaver` = fallback).

When it stops working (a session expired, the account was challenged): repeat steps 1-4 with a fresh export. Until then the GetInSaver fallback keeps
Instagram working; YouTube has no fallback and the editor asks for an upload.

## YouTube needs a JavaScript runtime
Even with valid cookies, yt-dlp answers `No video formats found!` for YouTube without a JavaScript runtime (it solves YouTube's signature challenge in JS).
Vercel's Python runtime has none, so `nodejs-wheel-binaries` ships Node and `yt-dlp[default]` ships the solver scripts (`yt-dlp-ejs`). The health page
shows `"js_runtime": true` when Node was found, and `"cookies": true` when `YTDLP_COOKIES_B64` is set. If the deployment is refused for size, drop
`imageio-ffmpeg` (the proxy copy) or `nodejs-wheel-binaries` (YouTube) from `requirements.txt`.

## Adding the GetInSaver key
```
cd deploy/social-relay
npx vercel env add GETINSAVER_API_KEY production --sensitive     # paste the key (gis_live_...) at the hidden prompt, never as an argument
npx vercel deploy --prod
```
The provider is behind Cloudflare, which refuses Python's default User-Agent; the relay sends a browser one.

## What works from Vercel's network (tested 2026-10-23)
- TikTok: works without login.
- YouTube / Vimeo / Instagram: need the cookies above (Instagram also has the GetInSaver fallback).
- Without a working login or fallback the editor says so and asks the user to upload the file; it never pretends the reference was followed.

Update yt-dlp (sites change often): bump `yt-dlp` in `requirements.txt` and redeploy.
