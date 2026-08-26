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

## 3. Challenges Faced

During the implementation and testing of the chosen approach, several fundamental hurdles and architectural flaws emerged:

### 1. Variable Frame Rate (VFR) Audio Desync
- **The Issue:** When extracting the audio from web videos using standard tools, the resulting `.wav` timeline got squashed or stretched. The AI found the phrase at `5:15`, but in the actual video, it was spoken at `5:25`.
- **Impact:** A massive 10-second mismatch between the audio timestamp and the visual video frame, rendering the extraction completely useless.

### 2. OpenCV Seeking Inaccuracy
- **The Issue:** We initially used Python's `cv2.VideoCapture` to calculate the frame number (`timestamp * fps`) and seek to it.
- **Impact:** OpenCV is notoriously terrible at seeking to precise frame indexes in highly compressed MP4 files (due to Keyframe/P-frame gaps). It frequently grabbed the wrong frame entirely.

### 3. Extremely Slow AI Processing (The 1-Hour Video Problem)
- **The Issue:** Running the Whisper model locally over a full 1-hour movie took immense processing power and time, mostly wasted on analyzing silent pauses, breathing, or background noise.

### 4. Repeated Computations (Wasted Time)
- **The Issue:** If a user searched for three different quotes in the same movie, the backend blindly re-extracted the audio and re-ran the heavy AI transcription three separate times.

### 5. Inexact Human Queries
- **The Issue:** If a user searched for *"My mind rebels at stagnation"*, but the speaker mumbled and the AI transcribed *"my mind rebells its stagnation"*, standard string matching completely failed.

---

### Iteration 1: Audio Sync & The RapidFuzz Upgrade
- **Fixing the Sync:** We identified the VFR audio drift. We forced FFmpeg to pad and strictly synchronize the audio track during extraction using the flag `-af aresample=async=1:first_pts=0`. This guaranteed the audio timeline perfectly matched the video frame timeline 1:1.
- **Fixing the Search:** We abandoned exact text matching and implemented `RapidFuzz`. We used a sliding window algorithm that scores phrase similarity. If the transcription is slightly garbled but matches the user's query with an 80%+ confidence score, we register it as a success.

### Iteration 2: Ditching OpenCV for Native FFmpeg Extraction
- Because OpenCV failed to grab the correct frame accurately from compressed MP4s, we ripped it out of the pipeline.
- We replaced it with a native FFmpeg subprocess command: `ffmpeg -ss {timestamp} -vframes 1`. FFmpeg natively handles keyframe decoding, allowing us to seek to the exact millisecond with frame-perfect precision.

### Iteration 3: VAD (Voice Activity Detection) Speed Optimization
- To solve the slow processing times for long videos, we enabled `faster-whisper`'s built-in Silero VAD filter (`vad_filter=True`).
- Before the Whisper AI even looks at the audio, the VAD filter aggressively scans for and deletes all silence, breathing, and non-speech background noise. This drastically cuts down the compute time.

### Iteration 4: Local Caching Layer
- To prevent redundant computations, we built a `.transcription.json` caching mechanism.
- The first time a video is analyzed, its full word-level timestamp array is dumped to a JSON file. If a user queries that same video again, the script skips video downloading, audio extraction, and AI transcription entirely. It loads the cache and executes the fuzzy search instantly (dropping response times from minutes down to ~1.3 seconds).

### Iteration 5: The FastAPI Backend Evolution
- We moved away from a simple CLI script and refactored the pipeline into a modern, decoupled backend architecture using **FastAPI**.
- The `app.py` server hosts the `POST /api/search` endpoint.
- It seamlessly manages the `yt-dlp` download, the `find_dialogue_asr.py` AI pipeline, and statically serves the extracted `.png` images back to the client over HTTP.

---

## 5. Limitations & Future Roadmap

While highly robust, the current architecture has limits we plan to solve in future iterations:
- **Blocking API Requests:** The FastAPI endpoint holds the connection open until processing finishes. **Future fix:** Implement asynchronous Celery task queues.
- **Heavy Disk Usage:** We download the entire MP4 to extract a single frame. **Future fix:** Stream audio for transcription via `yt-dlp`, and use FFmpeg to extract the specific visual frame directly over the network, bypassing local video downloads entirely.
- **Semantic Understanding:** RapidFuzz only handles typos. **Future fix:** Integrate a Vector Database (like Chroma) to allow users to search by *meaning* or *synonyms* instead of exact wording.