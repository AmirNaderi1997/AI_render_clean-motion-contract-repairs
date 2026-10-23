# Long-video content discovery

Upload one long video (podcast, class, interview) and ask for its reels in plain words. The agent routes the request
(`app/studio_orchestrator.py::_wants_discovery`, the LLM intent `discover`, and any video >= 8 minutes asked to become "reels"),
transcribes the whole video live, understands it as a whole, finds every standalone piece, and shows each as a card **inside the same chat**.
A card opens its own child chat that edits that piece as a normal Talking Reel.

## Flow

1. **Intake** (`long_video.create`): probe duration/resolution/audio, register the analysis. The uploaded attachment *is* the shared source asset; nothing is copied.
2. **Transcription** (`engine/long_transcribe.py`): audio extracted once (16 kHz mono), split at real pauses (about 5 min, never mid-word),
   faster-whisper per chunk (VAD, word timestamps, language per video from the first confident chunk). Each chunk is written to `chunks/NNNN.json`
   when it ends; a restart resumes from the first missing chunk (`long_video.recover_interrupted` at startup, `POST /discovery/{id}/resume`).
   Segments are published in small batches as Whisper yields them (`transcription.segment.completed`), so the chat shows real text while later chunks run.
3. **Correction** (`creative/discovery.py::enhance_segments`): per finished chunk, in a second thread. Raw text stays; `enhanced_text` is kept beside it.
   A correction that changes the vocabulary or length too much is rejected (`rejected_change`); doubtful phrases are flagged `uncertain`. Failed batches are retried once before discovery.
   Timing always comes from the raw words.
4. **Understanding**: topic map per ~7-minute window, merged into one outline (what the video is, who speaks, terms, topics).
5. **Candidates**: each window is read with the outline; ranges are segment ids (several ranges allowed). A second model pass checks each one with the 60 s before it
   (standalone? natural start/end? faithful hook?), may trim or add one context sentence, and drops weak ones. Boundaries are snapped to real word edges.
   Duplicates are removed by time overlap and by meaning. The number of cards is whatever the video holds.
6. **Cards**: thumbnail from the real video, on-demand 360p preview (several ranges are joined), title, summary, hook, range, category, score, reason, status.
   Edit title/hook/times (kept as numbered revisions), hide, ask for more ("only stories"), select several.
7. **Child chat** (`long_video.start_candidate`): clip cut from the shared source, the parent's transcript sliced and re-timed as the child's transcript
   (the clip is not transcribed again), a new conversation with `forced_intent: talking` and a link to the parent. One card never makes two chats.
   Card status follows the child project: discovered, selected, editing, rendering, completed, failed.

## Data (files next to the upload + conversation state; no new database tables)

`analysis.json` = LongVideoAnalysis (status, language, transcript_version, analysis_version, progress, candidates)  
`raw.json` / `transcript.json` = raw and corrected TranscriptSegments (`start,end,text,enhanced_text,words,confidence,speaker,flags`)  
`candidates[]` = ContentCandidate (`id` stable from the first start time, `ranges`, `score`, `status`, `child_conversation_id`, `revisions[]` = CandidateRevision)

## Events (SSE, existing channel)

`discovery.created`, `transcription.started|chunk.started|segment.completed|chunk.completed|progress|enhancement.completed|completed`,
`content.discovery.started`, `content.outline.completed`, `content.candidate.found`, `content.candidate.updated`, `content.discovery.completed`, `job.failed`.

## Resources

One transcription at a time per process (`LONGVIDEO_TRANSCRIBE_CONCURRENCY`), 5-minute chunks (about 20 MB of float audio in memory), model chosen by CPU count and length
(`LONGVIDEO_WHISPER_MODEL` overrides), cached model, per-chunk and per-window caches, previews and thumbnails made on demand and cached. Measured speed is reported in the chat as an ETA.

## Limits

- Speaker diarization is not available (no diarization model on the server): `speaker` is `null`, never guessed.
- Whisper still mishears some Persian words; the correction pass fixes obvious ones and flags the rest.
- Preview and thumbnail generation use ffmpeg on the original file; very large sources make the first preview take a few seconds.
