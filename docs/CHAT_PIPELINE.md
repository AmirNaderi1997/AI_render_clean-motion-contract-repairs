# One path for every kind of chat work

Every message goes through the same stages; only the tools of the last stage differ (`app/studio_orchestrator.py: process_message`).

1. **Opening reply** (`_stream_response`): two short sentences, streamed at once (LM API when its route streams, otherwise the direct providers with a hedged start).
   A question is answered here. It never writes the deliverable and never says it cannot read links.
2. **Understanding** (`_resolved_intent`): the model chooses the route from the meaning of the message and the conversation. Routes: `chat`, `modify`,
   `localize`, `talking`, `discover`, `motion` (ads from pages/images), `motion_graphic` (+ `_revision`, `_answer`), `question_*`.
3. **Intake** (`_gather_sources`, the same for every route that works from sources): a reference video (uploaded, or an Instagram/YouTube/TikTok link) is analysed as
   style (frame review picture in the chat); every other link is read as content (text, screenshots when the text is thin, the page's pictures). An uploaded video
   is the reference only for `motion`/`motion_graphic`; for `talking`/`localize`/`discover` it is the footage. Flows that take one request text get the same facts
   as a block (`_with_sources`); the others receive the `Sources` object.
4. **Tools** (the only part that differs): localize, talking reel, long-video discovery, ad storyboard, HTML motion graphic.
5. **Narration** (`app/studio_narrator.py`): after each real result a short, streamed message written by the model from the facts of that step (page title, shots,
   colours, the idea chosen...), with the real pictures attached. If the model is unavailable the plain factual fallback is posted.
6. **Progress and control**: step labels name the real subject (`studio_activity.subject`); long jobs show their live log, the ETA and sit at the end of the chat;
   the composer's button is Stop while work runs and Send as soon as something is typed (`request_stop` cancels the message, a project, a motion graphic or a discovery).

## Stop and "working" across processes
On the server the API process (it receives the Stop click) and the Celery worker (it runs the work) are different processes that share one data volume, so
nothing the Stop button or the working indicator depend on may live in memory. `app/studio_flags.py` keeps it in files next to the conversation:
`.stop` (the stop generation: a message started under an older number stops at its next checkpoint) and `.busy/<id>` (one heartbeat file per running unit of work).
A motion graphic keeps a run token in its record (Stop changes it; a worker whose token is no longer current unwinds, even one that is still inside a model
call), and discovery uses a `stop.flag` file. `GET /conversations/<id>` returns `busy` and workers emit `work.state` events, so the composer shows Stop for the
whole time anything is working: understanding the request, reading sources, writing the plan, designing scenes, rendering.
