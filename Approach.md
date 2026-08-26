# Approach

---

## 1. Problem Description

The objective was to build a system that automatically identifies the **exact video frame** and **timestamp window** where a specific dialogue phrase (e.g., *"My mind rebels at stagnation"*) is spoken within a given video stream or URL.

The system must:
1. Download the target video from a public URL.
2. Accurately detect when the phrase begins and ends at the millisecond level.
3. Compute the corresponding exact start and end video frame numbers.
4. Extract the exact visual frame image where the dialogue is spoken.
5. Provide a robust, production-ready backend API to serve these queries instantly to frontend clients.

---

## 2. Initial Ideas

At the beginning of the project, three main architectural directions were considered:

### Idea 1: Visual Frame Scanning (OCR)
- **Concept:** Periodically sample frames across the video and run an Optical Character Recognition (OCR) engine to visually scan for the dialogue text on screen.
- **Assumptions:** Assumed that the video stream included hardcoded subtitles or on-screen captions.
- **Status:** Immediately discarded. The target videos had zero on-screen text, rendering OCR completely useless.

### Idea 2: Whisper API (Cloud LLM)
- **Concept:** Send the audio chunks to a cloud API (like OpenAI's Whisper API or Gemini) to get the transcriptions and timestamps.
- **Status:** Discarded. Relying on an external cloud API limits scalability, incurs network latency for large video files, and fails the requirement for a fully independent, offline-capable application.

### Idea 3: Local Offline Speech-to-Text (STT) Pipeline
- **Concept:** Download the video, extract the audio locally, and process it entirely on the host machine using an open-source ASR model to get word-level timestamps, followed by a fuzzy-search algorithm to pinpoint the phrase.
- **Status:** Selected. This became the foundation of our architecture.

---

## 3. Challenges & Technical Solutions

During the implementation and testing of the chosen approach, several fundamental hurdles and architectural flaws emerged:

### 1. Variable Frame Rate (VFR) Audio Desync
- **The Issue:** When downloading "sparse" web video streams, the audio track often drops packets during silence. When extracting the audio from web videos using standard tools, the resulting `.wav` timeline got squashed (e.g. shrinking a 54-min video to a 53-min audio track). The AI found the phrase at `5:15`, but in the actual video, it was spoken at `5:25`.
- **The Fix:** We forced FFmpeg to pad and strictly synchronize the audio track during extraction using the filter `-af aresample=async=1:first_pts=0`. This forces FFmpeg to respect Presentation Timestamps (PTS) and fill missing gaps with pure silence, guaranteeing the audio timeline perfectly matches the video frame timeline 1:1.

### 2. OpenCV Seeking Inaccuracy
- **The Issue:** We initially used Python's `cv2.VideoCapture` to calculate the frame number (`timestamp * fps`) and seek to it. However, OpenCV is notoriously terrible at seeking to precise frame indexes in highly compressed MP4 files due to Variable Frame Rate (VFR) keyframe gaps. It frequently grabbed the wrong frame, up to 10 seconds away.
- **The Fix:** We ripped OpenCV out of the pipeline completely and replaced it with a native FFmpeg subprocess command: `ffmpeg -ss {timestamp} -vframes 1`. FFmpeg natively handles time-based seeking flawlessly, allowing us to seek to the exact millisecond with frame-perfect precision.

### 3. Extremely Slow AI Processing & OOM Errors
- **The Issue:** Running the `medium` Whisper model locally over a full 1-hour movie took immense processing power, caused Out of Memory (OOM) errors, and wasted time analyzing silent pauses and breathing.
- **The Fix:** We switched to the `base` Whisper model with `beam_size=1` for greedy, memory-efficient decoding. To solve the slow processing times, we enabled `faster-whisper`'s built-in Silero VAD filter (`vad_filter=True`). This aggressively scans for and deletes all silence before the Whisper AI even looks at the audio, drastically cutting down compute time.

### 4. Inexact Human Queries & AI Typos
- **The Issue:** The Whisper model would occasionally misspell a word (e.g., transcribing "rebels" as "rebells its"). If a user searched for *"My mind rebels at stagnation"*, standard exact string matching completely failed.
- **The Fix:** We abandoned exact text matching and implemented a sliding-window search using the `RapidFuzz` library. This scores phrase similarity based on phonetics/characters. If the transcription is slightly garbled but matches the user's query with an 80%+ confidence score, we register it as a success.

### 5. Repeated Computations (Wasted Time)
- **The Issue:** If a user searched for three different quotes in the same movie, the backend blindly re-extracted the audio and re-ran the heavy AI transcription three separate times.
- **The Fix:** We built a `.transcription.json` local caching layer. The first time a video is analyzed, its full word-level timestamp array is dumped to a JSON file. If queried again, the script skips video downloading, audio extraction, and AI transcription entirely. It loads the cache and executes the fuzzy search instantly (dropping response times from minutes down to ~1.3 seconds).

---

## 4. Final Architecture Evolution

By combining all the technical solutions above, we moved away from a simple CLI script and refactored the pipeline into a modern, decoupled backend architecture using **FastAPI**.
- The `app.py` server hosts the `POST /api/search` endpoint.
- It seamlessly manages the `yt-dlp` download, the `find_dialogue_asr.py` AI pipeline, and statically serves the extracted `.png` images back to the client over HTTP.

---

## 5. Limitations & Future Roadmap

While highly robust, the current architecture has limits we plan to solve in future iterations:
- **Blocking API Requests:** The FastAPI endpoint holds the connection open until processing finishes. **Future fix:** Implement asynchronous Celery task queues.
- **Heavy Disk Usage:** We download the entire MP4 to extract a single frame. **Future fix:** Stream audio for transcription via `yt-dlp`, and use FFmpeg to extract the specific visual frame directly over the network, bypassing local video downloads entirely.
- **Semantic Understanding:** RapidFuzz only handles typos. **Future fix:** Integrate a Vector Database (like Chroma) to allow users to search by *meaning* or *synonyms* instead of exact wording.