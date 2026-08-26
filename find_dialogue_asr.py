import argparse
import json
import os
import subprocess
import time
import yt_dlp
# pyrefly: ignore [missing-import]
from faster_whisper import WhisperModel
from rapidfuzz import fuzz

def download_video(url: str, output_path: str = "video.mp4") -> str:
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
    }
    print(f"Downloading video from {url}...")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            print("Download complete.")
            return output_path
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                raise Exception("Video download failed after maximum retries.")

def find_phrase_in_audio(video_path: str, target_phrase: str, threshold: float = 80.0):
    """
    Transcribes audio to get word-level timestamps (or loads from cache) and searches for the target phrase using fuzzy matching.
    """
    cache_file = f"{video_path}.transcription.json"
    
    if os.path.exists(cache_file):
        print(f"Loading cached transcription from {cache_file}...")
        with open(cache_file, "r", encoding="utf-8") as f:
            all_words_data = json.load(f)
            
        class CachedWord:
            def __init__(self, word, start, end):
                self.word = word
                self.start = start
                self.end = end
                
        all_words = [CachedWord(w["word"], w["start"], w["end"]) for w in all_words_data]
    else:
        print("Loading faster-whisper model (base)...")
        # Auto-detect GPU for 10x speedup, fallback to CPU. 
        model = WhisperModel("base", device="auto", compute_type="default")
        
        print("Extracting perfectly synced audio using ffmpeg...")
        audio_path = "temp_audio.wav"
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path, 
            "-vn", "-af", "aresample=async=1:first_pts=0", 
            "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
        print("Transcribing audio (this may take a while)...")
        # We strictly use English as requested
        # Re-enabled VAD filter (now that the ffmpeg timestamp drift bug is fixed)
        # to skip silent segments and drastically reduce the Whisper processing time.
        segments, info = model.transcribe(
            audio_path, 
            word_timestamps=True, 
            language="en",
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        all_words = []
        for segment in segments:
            for word in segment.words:
                all_words.append(word)
                

        # Save cache for future runs
        print(f"Saving transcription cache to {cache_file}...")
        all_words_data = [{"word": w.word, "start": w.start, "end": w.end} for w in all_words]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(all_words_data, f, indent=2)
            
    if not all_words:
        return None, None, "", 0.0, False
        
    target_words = target_phrase.lower().split()
    target_len = len(target_words)
    
    best_score = 0.0
    best_match_start = 0.0
    best_match_end = 0.0
    best_match_text = ""
    
    # Sliding window search over transcribed words
    for i in range(max(1, len(all_words) - target_len + 1)):
        # Handle cases where transcription is shorter than target phrase
        end_idx = min(i + target_len, len(all_words))
        window_words = all_words[i:end_idx]
        
        window_text = " ".join([w.word.strip() for w in window_words]).lower()
        score = fuzz.ratio(target_phrase.lower(), window_text)
        
        if score > best_score:
            best_score = score
            best_match_start = window_words[0].start
            best_match_end = window_words[-1].end
            best_match_text = window_text
            
    confident = best_score >= threshold
    return best_match_start, best_match_end, best_match_text, best_score, confident

def get_fps(video_path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True
        )
        num, den = result.stdout.strip().split('/')
        return float(num) / float(den)
    except Exception:
        return 23.976

def extract_frame(video_path: str, timestamp_sec: float, output_image_path: str):
    """
    Extracts the exact frame corresponding to the given timestamp using ffmpeg for perfect precision.
    """
    print(f"Extracting frame at timestamp {timestamp_sec:.2f}s using ffmpeg to {output_image_path}...")
    
    # ffmpeg is flawlessly accurate for time-based seeking
    command = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp_sec),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_image_path
    ]
    
    try:
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(output_image_path):
            raise Exception("ffmpeg completed but image was not created")
            
        fps = get_fps(video_path)
        frame_number = int(round(timestamp_sec * fps))
        return frame_number, output_image_path
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to extract frame with ffmpeg. {e}")

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
    
    try:
        start_total = time.time()
        
        # Step 1: Download video if url is provided and it's not already downloaded
        if args.url and not os.path.exists(video_path):
            video_path = download_video(args.url, video_path)
            
        if not os.path.exists(video_path):
            print(f"Error: Video file '{video_path}' not found. Please provide a valid --video path or --url to download.")
            return
        
        # Step 2 & 3: Transcribe and fuzzy match
        start_time, end_time, matched_text, score, confident = find_phrase_in_audio(video_path, args.phrase, args.threshold)
        
        if start_time is None:
            print("No speech detected in the video at all.")
            return
            
        # Step 4: Extract frames
        print("=== Step 4: Extracting Start & End Frames ===")
        start_frame_num, start_image = extract_frame(video_path, start_time, "start_frame.png")
        end_frame_num, end_image = extract_frame(video_path, end_time, "end_frame.png")
        fps = get_fps(video_path)
        
        # Output Summary
        print("\n" + "="*40)
        print("FINAL SUCCESSFUL OUTPUT:")
        print(f"Start Timestamp : {format_timestamp(start_time)}")
        print(f"Start Frame     : {start_frame_num}")
        print(f"End Timestamp   : {format_timestamp(end_time)}")
        print(f"End Frame       : {end_frame_num}")
        print(f"FPS             : {fps:.2f}")
        print(f"Spoken Text     : \"{matched_text.strip()}\"")
        print(f"Saved Images    : \n  - {os.path.abspath(start_image)}\n  - {os.path.abspath(end_image)}")
        print("="*40)
        print(f"Total pipeline execution time: {time.time() - start_total:.2f} seconds")
        
        if not confident:
            print(f"\nWarning: Best match score ({round(score, 1)}) is below threshold ({args.threshold}).")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
