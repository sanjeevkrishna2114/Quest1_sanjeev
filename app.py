from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os
import traceback

from find_dialogue_asr import (
    download_video,
    get_fps,
    find_phrase_in_audio,
    extract_frame,
    format_timestamp
)

app = FastAPI(title="Video Dialogue Search API")

# Mount the current directory (or a specific output folder) to serve the extracted images
app.mount("/static", StaticFiles(directory="."), name="static")

class SearchRequest(BaseModel):
    phrase: str
    video_url: Optional[str] = None
    video_path: Optional[str] = "video.mp4"
    threshold: float = 80.0

class SearchResponse(BaseModel):
    success: bool
    match_score: Optional[float] = None
    spoken_text: Optional[str] = None
    start_timestamp: Optional[str] = None
    start_frame: Optional[int] = None
    end_timestamp: Optional[str] = None
    end_frame: Optional[int] = None
    fps: Optional[float] = None
    images: Optional[dict] = None
    message: Optional[str] = None

@app.post("/api/search", response_model=SearchResponse)
async def search_dialogue(req: SearchRequest, request: Request):
    try:
        video_path = req.video_path
        
        # 1. Download video if URL is provided
        if req.video_url:
            video_path = download_video(req.video_url, output_path=video_path)
        elif not os.path.exists(video_path):
            raise HTTPException(status_code=400, detail=f"Local video file '{video_path}' not found and no video_url provided.")
            
        # 2. Get Video FPS
        fps = get_fps(video_path)
        
        # 3. Search for Phrase
        start_sec, end_sec, text, score, confident = find_phrase_in_audio(video_path, req.phrase, req.threshold)
        
        if not confident:
            return SearchResponse(
                success=False,
                match_score=score,
                spoken_text=text,
                message="Phrase not found with sufficient confidence."
            )
            
        # 4. Extract Start & End Frames
        start_img = "start_frame.png"
        end_img = "end_frame.png"
        
        start_frame_num, _ = extract_frame(video_path, start_sec, start_img)
        end_frame_num, _ = extract_frame(video_path, end_sec, end_img)
        
        # Construct base URL for images
        base_url = str(request.base_url).rstrip("/")
        
        return SearchResponse(
            success=True,
            match_score=score,
            spoken_text=text,
            start_timestamp=format_timestamp(start_sec),
            start_frame=start_frame_num,
            end_timestamp=format_timestamp(end_sec),
            end_frame=end_frame_num,
            fps=fps,
            images={
                "start_frame_url": f"{base_url}/static/{start_img}",
                "end_frame_url": f"{base_url}/static/{end_img}"
            }
        )

    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
