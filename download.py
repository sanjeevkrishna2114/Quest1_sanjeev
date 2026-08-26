import yt_dlp
import sys
import time

def download_video(url: str, output_path: str = "video.mp4", max_retries: int = 10):
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
            print(f"\nSuccess! Video saved to {output_path}")
            return
        except Exception as e:
            print(f"\nError downloading video: {e}")
            if attempt < max_retries:
                print("Retrying in 5 seconds...")
                time.sleep(5)
            else:
                print("Max retries reached. Download failed.")

if __name__ == "__main__":
    # The URL for the target video
    video_url = "https://ok.ru/video/248244667877"
    download_video(video_url)
