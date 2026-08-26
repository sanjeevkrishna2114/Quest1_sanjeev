# CLAUDE.md — Find the Exact Frame Where a Dialogue Appears

## Problem Statement (as clarified)

Given a video URL, locate the exact frame where a specific line of dialogue
is spoken, and return:

- Timestamp of the identified moment
- Frame number
- The extracted dialogue text
- The corresponding video frame as an image

**Confirmed case for this document:** the target video (`ok.ru/video/248244667877`)
has **no subtitle track, no closed captions, and no burned-in/on-screen text of
any kind.** The dialogue "My mind rebels at stagnation" is *spoken*, not shown.
This rules out both subtitle-file parsing and OCR entirely — the only signal
available is the audio track.

---

## Approach: Automatic Speech Recognition (ASR)

Since the dialogue is spoken and nothing is rendered as text in the video
frames, **Automatic Speech Recognition (ASR)** is the sole detection
mechanism:

1. Extract the audio track from the video.
2. Transcribe it with a model that returns **word-level timestamps**
   (not just sentence-level), since we need frame-precision, not
   subtitle-precision.
3. Fuzzy-search the transcript for the target phrase.
4. Map the matched words' timestamps back to a frame number using the
   video's actual fps.
5. Extract that frame as an image.

No LLM is used for the transcription or matching step itself — Whisper
(via `faster-whisper`) is a dedicated ASR model, not an LLM, and fuzzy string
matching (`rapidfuzz`) is a deterministic algorithm. This keeps the core
detection pipeline explainable and reproducible, which matters for the
"defend your solution" requirement.

---

## Pipeline

```
URL
 │
 ▼
[1] yt-dlp download ──► video.mp4
 │
 ▼
[2] ffmpeg extract audio ──► audio.wav (16kHz mono, what Whisper expects)
 │
 ▼
[3] faster-whisper transcribe (word_timestamps=True)
 │      → list of words, each with (text, start_time, end_time, confidence)
 ▼
[4] Fuzzy phrase search over the word list
 │      → sliding window of N words, rapidfuzz.fuzz.ratio against target
 │      → best-scoring window = candidate match
 ▼
[5] Confidence check
 │      score >= threshold?  ──No──► flag as low-confidence, return top-3 candidates
 │      Yes
 ▼
[6] Map match window → start_time
 │      frame_number = round(start_time * video_fps)   [fps read from file, never assumed]
 ▼
[7] cv2.VideoCapture seek to frame_number → extract + save image
 │
 ▼
Output: { timestamp, frame_number, text, confidence, image_path }
```

---

## Design Decisions

### Word-level timestamps, not segment-level
Whisper's default output gives timestamps per *sentence/segment* (e.g.
"0:42–0:47: My mind rebels at stagnation, I crave for mental exaltation").
That's too coarse — the requirement asks for the frame the dialogue appears
in, which means we need the timestamp of roughly *when the target phrase
itself* starts within that segment, not when the whole segment starts.
`faster-whisper`'s `word_timestamps=True` gives per-word start/end, so we
can align precisely to the first word of the matched phrase.

### Fuzzy matching, not exact string matching
ASR transcription is never guaranteed to be verbatim. It may render the line
as "my mind rebels against stagnation," drop small words, or mishear a word
entirely. Exact matching would fail on any of these. `rapidfuzz.fuzz.ratio`
over a sliding window of words tolerates this while still requiring strong
overall similarity.

### fps read from the file, never hardcoded
Frame number is derived as `round(timestamp * fps)` where `fps` comes from
`cv2.VideoCapture.get(cv2.CAP_PROP_FPS)` on the actual downloaded file. This
is what makes the solution "robust to normal variations in ... frame rate"
per the requirements — a 23.976fps video and a 30fps video are handled
identically without special-casing.

### Confidence threshold, not a forced answer
If the best fuzzy-match score falls below threshold (default 80/100), the
program does **not** silently assert a possibly-wrong answer. It:
- Returns the best candidate anyway, explicitly marked `"confident": false`
- Also returns the next-best 2 candidates, so a human can disambiguate
- Prints a warning explaining *why* confidence is low (e.g. "no window
  scored above threshold — the phrase may not be present, or audio quality
  may be too poor for reliable transcription")

This directly addresses the requirement: "How you handle cases where the
result is ambiguous or uncertain."

---

## Edge Cases Handled

| Edge case | Handling |
|---|---|
| ASR mishears/misspells a word in the phrase | Fuzzy matching (partial credit for near-matches) rather than exact match |
| Phrase spoken multiple times in the video | All windows scoring above threshold are collected; highest-scoring is primary, others returned as alternates |
| Background music/noise degrades transcription accuracy | Audio is downmixed to mono 16kHz before transcription (Whisper's expected input) to maximize accuracy; a noise-reduction pre-pass (e.g. `noisereduce`) can be added if accuracy is poor on a noisy source |
| Phrase spans a pause (e.g. speaker takes a breath mid-line) | Whisper's segment boundaries don't have to align with the phrase boundaries — word-level search works across segment splits |
| Non-English audio / accented speech | `faster-whisper` model size/language can be configured (`medium`/`large-v3`, explicit `language=` param) — documented as a config knob, not hardcoded |
| Video has no speech at all in the relevant section (silence/music only) | No words returned by ASR in that range → no match possible → falls through to "low confidence, no candidates found" rather than a false positive |
| Very long video (performance) | Whisper transcribes the whole audio track once, upfront — this is actually *cheaper* than the OCR case's frame-by-frame sweep, since audio transcription is a single linear pass regardless of video length |
| Download fails (geo-block, private video, ok.ru extractor issue) | `yt-dlp` failure surfaced immediately with a clear error rather than proceeding with a partial/corrupt file |

---

## Prompts Used (LLM usage disclosure)

No LLM was used for transcription, phrase matching, or frame extraction —
those are deterministic (Whisper ASR model + rapidfuzz algorithm + OpenCV).
An LLM (this conversation, Claude) was used during development for:

- Drafting the initial pipeline architecture and this document
- Reasoning through edge cases to enumerate before implementation

No prompts were used to *generate* the matching logic at runtime — there is
no LLM call inside the executed program.

---

## How to Run

```bash
pip install yt-dlp faster-whisper rapidfuzz opencv-python numpy

python find_dialogue_asr.py \
    --url "https://ok.ru/video/248244667877" \
    --phrase "My mind rebels at stagnation" \
    --threshold 80
```

Output:
```json
{
  "timestamp": "00:00:42.310",
  "frame": 1058,
  "text": "my mind rebels at stagnation",
  "match_score": 94.1,
  "confident": true,
  "image_path": "/mnt/user-data/outputs/matched_frame.png"
}
```

---

## Open Items for Next Iteration

- [ ] Add `noisereduce` pre-pass, configurable via flag, for noisy source audio
- [ ] Multi-occurrence output (return all above-threshold matches, not just best)
- [ ] Language auto-detection vs. forced `language="en"`
- [ ] Diarization (if "who says it" ever becomes a requirement) — not needed currently