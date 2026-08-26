import argparse
import json
import os
import cv2
import yt_dlp
import time
# pyrefly: ignore [missing-import]
from faster_whisper import WhisperModel


def download_video(url: str, output_path: str = "video.mp4", max_retries: int = 10) -> str:
    """
    Downloads the video from the given URL using yt-dlp.
    """
    ydl_opts = {
        'format': 'best',
        'outtmpl': output_path,
        'quiet': False,
        'no_warnings': True,
    }
    
    for attempt in range(1, max_retries + 1):
        print(f"Downloading video from {url}... (Attempt {attempt}/{max_retries})")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            if os.path.exists(output_path):
                return output_path
        except Exception as e:
            print(f"Error downloading video: {e}")
            if attempt < max_retries:
                print("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                raise Exception("Video download failed after maximum retries.")

def find_phrase_in_audio(video_path: str, target_phrase: str, threshold: float = 80.0):
    """
    Transcribes audio to get word-level timestamps and searches for the exact target phrase.
    """
    print("Loading faster-whisper model (base)...")
    # Using 'base' model for decent speed/accuracy balance. Can be changed to 'medium' for better accuracy.
    model = WhisperModel("base", device="cpu", compute_type="int8")
    
    print("Transcribing audio (this may take a while)...")
    # We strictly use English as requested
    segments, info = model.transcribe(video_path, word_timestamps=True, language="en")
    
    all_words = []
    for segment in segments:
        for word in segment.words:
            all_words.append(word)
            
    if not all_words:
        return None, None, 0.0, False
        
    target_words = target_phrase.lower().split()
    target_len = len(target_words)
    
    # Exact sliding window search over transcribed words
    for i in range(max(1, len(all_words) - target_len + 1)):
        # Handle cases where transcription is shorter than target phrase
        end_idx = min(i + target_len, len(all_words))
        window_words = all_words[i:end_idx]
        
        window_text = " ".join([w.word.strip() for w in window_words]).lower()
        
        # Exact match checking
        if target_phrase.lower() == window_text:
            return window_words[0].start, window_text, 100.0, True
            
    return None, None, 0.0, False

def extract_frame(video_path: str, timestamp_sec: float, output_image_path: str = "matched_frame.png"):
    """
    Extracts the exact frame corresponding to the given timestamp.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception("Failed to open video file for frame extraction.")
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps == 0:
        fps = 25.0 # fallback fps if unable to read
        
    frame_number = int(round(timestamp_sec * fps))
    
    print(f"Extracting frame {frame_number} at timestamp {timestamp_sec:.2f}s...")
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    
    if ret:
        cv2.imwrite(output_image_path, frame)
        cap.release()
        return frame_number, output_image_path
    else:
        cap.release()
        raise Exception(f"Failed to read frame {frame_number}")

def format_timestamp(seconds: float) -> str:
    """Formats a time in seconds to HH:MM:SS.mmm format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def main():
    parser = argparse.ArgumentParser(description="Find the exact frame where a dialogue appears.")
    parser.add_argument("--url", required=False, help="URL of the video (optional, if you want to download)")
    parser.add_argument("--video", required=False, default="video.mp4", help="Path to local video file")
    parser.add_argument("--phrase", required=True, help="Target phrase to search for")
    parser.add_argument("--threshold", type=float, default=80.0, help="Fuzzy match confidence threshold (0-100)")
    args = parser.parse_args()

    video_path = args.video
    image_path = "matched_frame.png"
    
    try:
        # Step 1: Download video if url is provided and it's not already downloaded
        if args.url and not os.path.exists(video_path):
            video_path = download_video(args.url, video_path)
            
        if not os.path.exists(video_path):
            print(f"Error: Video file '{video_path}' not found. Please provide a valid --video path or --url to download.")
            return
        
        # Step 2 & 3 & 4: Transcribe and fuzzy match
        start_time, matched_text, score, confident = find_phrase_in_audio(video_path, args.phrase, args.threshold)
        
        if start_time is None:
            print("No speech detected in the video.")
            return
            
        # Step 5: Extract frame
        frame_number, saved_image = extract_frame(video_path, start_time, image_path)
        
        # Output result
        result = {
            "timestamp": format_timestamp(start_time),
            "frame": frame_number,
            "text": matched_text,
            "match_score": round(score, 1),
            "confident": confident,
            "image_path": os.path.abspath(saved_image)
        }
        
        print("\n--- Result ---")
        print(json.dumps(result, indent=2))
        
        if not confident:
            print(f"\nWarning: Best match score ({round(score, 1)}) is below threshold ({args.threshold}).")
            print("The phrase may not be present, or audio quality may be too poor.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
