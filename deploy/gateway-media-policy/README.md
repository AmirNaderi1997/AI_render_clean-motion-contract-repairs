# EditorGPT single-attempt media policy

Editor sends one paid submission per approved incomplete asset. An ambiguous
timeout must never silently resubmit: the provider may already have charged it.
Celery automatic retries and gateway model/provider fallback are disabled for media.
Manual retry requires explicit confirmation. Existing valid assets are reused.

Gateway patch targets FreeLLMAPI v0.16.5 (revision 5540efac), original image
`sha256:8bb870eed66c4527a19b80da6b86421f85f4a9dfbcafd7df315985ba1a3d55c3`.
Copy its `server/dist/services/media.js` and `server/dist/routes/proxy.js` into a
clean build directory preserving those paths. Apply `patch -p0 < gateway.patch`.
Copy `editor-media-policy.js` into `server/dist/lib/`. Build using this Dockerfile
and the original image tagged `freellmapi:editor-policy-base`. Use the existing
gateway Compose configuration plus `compose.editor-policy.yml` (preserves secrets,
mounts and networks). No stopped containers or volumes should be deleted.

Only requests explicitly carrying the Editor policy header change behavior.
Other gateway clients retain their existing configuration. Response budgets are
at least 150s image, 200s audio, 300s video; Editor sends larger complexity-aware
budgets up to one hour. These are timeouts, not artificial delays after a definite
provider rejection. Gateway upgrades must reapply and validate this patch.
Editor checks GET `/v1/editor-media-policy` and refuses paid media if the guard
is absent. Rollback to the original image therefore fails closed for Editor.

Run `node --test policy.test.mjs` plus Editor's mocked media policy tests. Never
run paid image/audio/video probes to verify deployment without user approval.
