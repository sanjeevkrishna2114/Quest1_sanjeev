# Video Dialogue Spotter (ASR Pipeline)

## Overview
This project is an automated AI pipeline (`find_dialogue_asr.py`) designed to locate the exact timestamps and video frames where a specific dialogue phrase is spoken in a video. 

Given a target phrase and a video (either downloaded via a URL or provided locally), the pipeline:
1. Downloads the video using `yt-dlp`.
2. Extracts the audio track into a perfectly synchronized `.wav` file.
3. Transcribes the audio using OpenAI's Whisper model (`faster-whisper`), capturing precise word-level timestamps.
4. Uses fuzzy string matching to find the target phrase in the transcription, even if the AI misspelled a word.
5. Extracts the exact starting and ending video frames of the dialogue using `ffmpeg`.

## Architecture Diagram

Below is the high-level architecture of the dialogue search pipeline and how the FastAPI backend interacts with the various components:

```mermaid
flowchart TD
    Client([Frontend / Client]) --> |"POST /api/search"| API(FastAPI Backend)
    
    subgraph Pipeline [Dialogue Search Pipeline]
        Downloader[yt-dlp] 
        AudioExt[FFmpeg Audio Extractor]
        ASR[faster-whisper AI]
        Search[RapidFuzz Searcher]
        FrameExt[FFmpeg Frame Extractor]
    end
    
    API -- "Download (if URL given)" --> Downloader
    Downloader -- "video.mp4" --> API
    API --> Cache{Cache Exists?}
    
    Cache -- "No" --> AudioExt
    AudioExt -- "temp_audio.wav" --> ASR
    ASR -- "VAD Filter + Transcription" --> CacheStore[(JSON Cache)]
    
    Cache -- "Yes" --> Search
    CacheStore --> Search
    
    Search -- "Match Timestamps" --> FrameExt
    FrameExt -- "Extract PNGs" --> Static[(Static Files)]
    
    Static -. "Images" .-> API
    Search -. "JSON Text Data" .-> API
    
    API --> |"JSON Response"| Client
```

## Setup and How to Run

Follow these instructions to clone and run the backend API on your local machine.

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/Quest1_sanjeev.git
cd Quest1_sanjeev
```

### 2. System Requirements (FFmpeg)
This project **requires FFmpeg** to be installed on your system path for audio/video extraction.
- **Windows:** Download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or install via winget: `winget install ffmpeg`
- **Mac:** `brew install ffmpeg`
- **Linux:** `sudo apt install ffmpeg`

### 3. Create a Virtual Environment (Recommended)
It is highly recommended to isolate dependencies using a Python virtual environment:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate
```

### 4. Install Dependencies
Install the required Python packages:
```bash
pip install -r requirements.txt
```

### 5. Start the Backend Server
Start the backend by running the `uvicorn` ASGI server:
```bash
python -m uvicorn app:app --port 8000
```
*(The API will be hosted at `http://localhost:8000`)*

---

## FastAPI Backend Integration

We built a **FastAPI** backend to expose this powerful pipeline to frontend applications. 

### Endpoint Usage

**`POST /api/search`**

Send a JSON payload with the phrase you want to find. 

#### Request Body Fields

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `phrase` | String | **Yes** | The exact dialogue or sentence you want to search for. |
| `video_url` | String | *Optional* | A YouTube (or supported site) link. If provided, the backend will automatically download the video first. |
| `video_path` | String | *Optional* | The local filename where the video is saved (or will be saved). Defaults to `"video.mp4"`. |
| `threshold` | Float | *Optional* | The RapidFuzz match threshold (0-100). Defaults to `80.0`. Lower it for mumbled speech. |

#### Example 1: Full Download & Search
If you are searching a video for the very first time, provide the `video_url` so the backend downloads it in the background:

*(Note for Windows PowerShell users: Wrap the command in `cmd /c '...'` to prevent PowerShell from stripping quotes!)*
```bash
cmd /c 'curl.exe -X POST "http://localhost:8000/api/search" -H "Content-Type: application/json" -d "{\"phrase\": \"hello everybody welcome to thats football\", \"video_url\": \"https://www.youtube.com/watch?v=YVygyRMeATs\", \"video_path\": \"test_video.mp4\"}"'
```

#### Example 2: Instant Cached Search (No URL)
If the video is already downloaded on your hard drive (e.g. from a previous search), **omit the `video_url` entirely**. The backend will instantly load the `.transcription.json` cache from disk and return results in ~1.3 seconds:

```bash
cmd /c 'curl.exe -X POST "http://localhost:8000/api/search" -H "Content-Type: application/json" -d "{\"phrase\": \"they have got two young wingers\", \"video_path\": \"test_video.mp4\"}"'
```

#### Response Schema:
The backend returns the exact timing boundaries, the actual spoken text from the video, and static URLs to the extracted `.png` frames:
```json
{
  "success": true,
  "match_score": 86.86,
  "spoken_text": "they've got two very young winger in munez and rio.",
  "start_timestamp": "00:01:43.299",
  "start_frame": 5165,
  "end_timestamp": "00:01:46.519",
  "end_frame": 5326,
  "fps": 50.0,
  "images": {
    "start_frame_url": "http://localhost:8000/static/start_frame.png",
    "end_frame_url": "http://localhost:8000/static/end_frame.png"
  },
  "message": null
}
```

> [!TIP]
> If you query the same `"video_path"` twice, the backend intelligently reads from the `.transcription.json` cache on your hard drive, bypassing the AI model completely and returning results in **~1.3 seconds**.

---

## Example Output

**Target Phrase:** `"My mind rebels at stagnation"`  
**Source Video:** `ok.ru/video/248244667877` (Sherlock Holmes - Scandal in Bohemia)

```text
Loading faster-whisper model (base)...
Extracting perfectly synced audio using ffmpeg...
Transcribing audio (this may take a while)...
Saving transcription cache to video.mp4.transcription.json...
=== Step 4: Extracting Start & End Frames ===
Extracting frame at timestamp 324.84s using ffmpeg to start_frame.png...
Extracting frame at timestamp 327.88s using ffmpeg to end_frame.png...

========================================
FINAL SUCCESSFUL OUTPUT:
Start Timestamp : 00:05:24.839
Start Frame     : 7788
End Timestamp   : 00:05:27.879
End Frame       : 7861
FPS             : 23.98
Spoken Text     : "my mind rebells its stagnation."
Saved Images    :
  - D:\Assignment\Quest1_sanjeev\start_frame.png
  - D:\Assignment\Quest1_sanjeev\end_frame.png
========================================
Total pipeline execution time: 354.28 seconds
```

### Subsequent Cached Runs (Lightning Fast)

Because of the **Transcription Cache**, searching for new phrases in the same video takes just ~1.3 seconds, instantly bypassing the entire Whisper transcription process.

**Target Phrase:** `"what is it it is a plumbers rocket madam'"`
```text
Loading cached transcription from video.mp4.transcription.json...
=== Step 4: Extracting Start & End Frames ===
Extracting frame at timestamp 2538.66s using ffmpeg to start_frame.png...
Extracting frame at timestamp 2544.16s using ffmpeg to end_frame.png...

========================================
FINAL SUCCESSFUL OUTPUT:
Start Timestamp : 00:42:18.659
Start Frame     : 60867
End Timestamp   : 00:42:24.159
End Frame       : 60999
FPS             : 23.98
Spoken Text     : "what is it? it is a plumber's rocket, madden."
========================================
Total pipeline execution time: 1.34 seconds
```

**Target Phrase:** `"his name is goddfrey norton of the inner temple "`
```text
Loading cached transcription from video.mp4.transcription.json...
=== Step 4: Extracting Start & End Frames ===
Extracting frame at timestamp 1528.48s using ffmpeg to start_frame.png...
Extracting frame at timestamp 1530.88s using ffmpeg to end_frame.png...

========================================
FINAL SUCCESSFUL OUTPUT:
Start Timestamp : 00:25:28.480
Start Frame     : 36647
End Timestamp   : 00:25:30.880
End Frame       : 36704
FPS             : 23.98
Spoken Text     : "is a mr. godfrey norton of the inner temple."
========================================
Total pipeline execution time: 1.33 seconds
```

**Target Phrase:** `"this is not it "`
```text
Loading cached transcription from video.mp4.transcription.json...
=== Step 4: Extracting Start & End Frames ===
Extracting frame at timestamp 2806.00s using ffmpeg to start_frame.png...
Extracting frame at timestamp 2808.30s using ffmpeg to end_frame.png...

========================================
FINAL SUCCESSFUL OUTPUT:
Start Timestamp : 00:46:46.000
Start Frame     : 67277
End Timestamp   : 00:46:48.300
End Frame       : 67332
FPS             : 23.98
Spoken Text     : "this is not it."
========================================
Total pipeline execution time: 1.37 seconds
```

**Target Phrase:** `"i kept it only to safeguard myself and preserve weapon which will secure me from any steps he takes "`
```text
Loading cached transcription from video.mp4.transcription.json...
=== Step 4: Extracting Start & End Frames ===
Extracting frame at timestamp 2957.40s using ffmpeg to start_frame.png...
Extracting frame at timestamp 2964.76s using ffmpeg to end_frame.png...

========================================
FINAL SUCCESSFUL OUTPUT:
Start Timestamp : 00:49:17.400
Start Frame     : 70907
End Timestamp   : 00:49:24.760
End Frame       : 71083
FPS             : 23.98
Spoken Text     : "kept it only to safeguard myself and to preserve a weapon which will always secure me from any steps"
========================================
Total pipeline execution time: 1.41 seconds
```

### Summary Table of Test Cases

All test cases were run on the video **Sherlock Holmes - Scandal in Bohemia** (`ok.ru/video/248244667877`).

| Target Input Phrase | Actual Spoken Text Detected | Start Timestamp | End Timestamp |
| :--- | :--- | :--- | :--- |
| `"My mind rebels at stagnation"` | `"my mind rebells its stagnation."` | `00:05:24.839` | `00:05:27.879` |
| `"what is it it is a plumbers rocket madam'"` | `"what is it? it is a plumber's rocket, madden."` | `00:42:18.659` | `00:42:24.159` |
| `"his name is goddfrey norton of the inner temple "` | `"is a mr. godfrey norton of the inner temple."` | `00:25:28.480` | `00:25:30.880` |
| `"this is not it "` | `"this is not it."` | `00:46:46.000` | `00:46:48.300` |
| `"i kept it only to safeguard myself and preserve weapon which will secure me from any steps he takes "` | `"kept it only to safeguard myself and to preserve a weapon which will always secure me from any steps"` | `00:49:17.400` | `00:49:24.760` |

---

## Limitations

- **Blocking API Requests:** The FastAPI endpoint holds the connection open until processing finishes. For extremely long videos, this risks the client connection timing out before a response is sent.
- **Disk Space Overhead:** Entire video files are downloaded and stored locally. A future implementation could stream the audio directly using `yt-dlp` and extract the frame remotely via the network URL.
- **Singing & Music Videos:** The integrated Silero VAD (Voice Activity Detection) filter optimizes speed specifically for spoken dialogue. It actively filters out singing and heavy instrumentation, meaning it will likely fail to extract lyrics from music videos.
- **Semantic Understanding:** The fuzzy matching algorithm (`RapidFuzz`) perfectly handles AI transcription typos or human spelling errors, but it does *not* understand context or synonyms.
