from fastapi import FastAPI, Form
from fastapi.responses import FileResponse
import praw
import os
import requests
from yt_dlp import YoutubeDL
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import re
import random
import shutil
import time
import logging
import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO)

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Enable CORS to allow React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "https://choros.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Reddit API setup
reddit = praw.Reddit(
    client_id=os.getenv("CLIENT_ID"),
    client_secret=os.getenv("CLIENT_SECRET"),
    user_agent=os.getenv("USER_AGENT", "webscraper")
)

# Google Drive setup with service account
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service_account.json")
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# Download directory
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Helper functions
def download_media(url, filename, post=None):
    """Download media file with support for YouTube, Reddit videos, and other platforms"""
    logging.info(f"Attempting to download: {url}")
    try:
        filepath = DOWNLOAD_DIR / filename
        
        video_platforms = [
            'youtube.com', 'youtu.be', 'reddit.com/r', 'v.redd.it',
            'vimeo.com', 'dailymotion.com', 'facebook.com'
        ]
        
        if any(platform in url.lower() for platform in video_platforms):
            # Enhanced yt-dlp configuration with cookies
            cookies_file = os.getenv("REDDIT_COOKIES_FILE")
            if cookies_file and not os.path.exists(cookies_file):
                logging.warning(f"Cookies file {cookies_file} not found. Proceeding without cookies.")
                cookies_file = None

            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': str(filepath),
                'merge_output_format': 'mp4',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }, {
                    'key': 'FFmpegEmbedSubtitle',
                }, {
                    'key': 'FFmpegMetadata',
                }],
                'prefer_ffmpeg': True,
                'keepvideo': False,
                'quiet': False,  # Changed to False to see more logs
                'no_warnings': False,  # Changed to False to see warnings
                'username': os.getenv("REDDIT_USERNAME"),
                'password': os.getenv("REDDIT_PASSWORD"),
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': '*/*',
                    'Referer': 'https://www.reddit.com/',
                    'Origin': 'https://www.reddit.com',
                },
                'retries': 5,  # Retry on failure
                'sleep_interval': 2,  # Wait 2 seconds between retries
                'cookiefile': cookies_file,  # Use cookies file if available
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                    if filepath.exists():
                        logging.info(f"yt-dlp succeeded for {url}")
                        return str(filepath)
                except Exception as e:
                    logging.error(f"yt-dlp failed for {url}: {str(e)}")
            
            # Enhanced fallback for Reddit videos with audio
            if post and post.is_video and 'reddit_video' in post.media:
                return download_reddit_video(post, filepath)
            return download_with_requests(url, filepath)
        else:
            return download_with_requests(url, filepath)
            
    except Exception as e:
        logging.error(f"Download error for {url}: {str(e)}")
    return None

def download_reddit_video(post, filepath):
    """Improved function specifically for downloading Reddit videos with audio"""
    try:
        if not post.is_video or 'reddit_video' not in post.media:
            return None
        
        video_url = post.media['reddit_video']['fallback_url']
        logging.info(f"Processing Reddit video: {video_url}")
        
        # Extract the base URL for audio
        base_url = video_url.rsplit('/', 1)[0]
        
        # Create temporary files for video and audio
        video_path = filepath.with_suffix('.video.mp4')
        audio_path = filepath.with_suffix('.audio.mp4')
        final_path = filepath.with_suffix('.mp4')
        
        # Download video
        video_downloaded = download_with_requests(video_url, video_path)
        if not video_downloaded:
            logging.error(f"Failed to download video from {video_url}")
            return None
        
        # Possible audio URLs
        audio_urls = [
            f"{base_url}/DASH_audio.mp4",
            f"{base_url}/audio",
            f"{base_url}/DASH_AUDIO_64.mp4",
            f"{base_url}/DASH_AUDIO_128.mp4",
            video_url.replace('DASH_', 'DASH_audio_')
        ]
        
        # Try each audio URL until one works
        audio_downloaded = None
        for audio_url in audio_urls:
            logging.info(f"Trying audio URL: {audio_url}")
            audio_downloaded = download_with_requests(audio_url, audio_path)
            if audio_downloaded:
                logging.info(f"Successfully downloaded audio from {audio_url}")
                break
            else:
                logging.warning(f"Failed to download audio from {audio_url}")
        
        # If video was downloaded
        if video_downloaded:
            if audio_downloaded:
                # Use subprocess instead of os.system for better error handling
                try:
                    # Convert PosixPath objects to strings
                    ffmpeg_cmd = ["ffmpeg", "-i", str(video_downloaded), "-i", str(audio_downloaded), 
                                 "-c:v", "copy", "-c:a", "aac", str(final_path), "-y"]
                    
                    logging.info(f"Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
                    result = subprocess.run(ffmpeg_cmd, 
                                           stdout=subprocess.PIPE, 
                                           stderr=subprocess.PIPE, 
                                           text=True, 
                                           check=False)
                    
                    if result.returncode != 0:
                        logging.error(f"FFmpeg error: {result.stderr}")
                        # Try a simpler ffmpeg command as fallback
                        ffmpeg_cmd = ["ffmpeg", "-i", str(video_downloaded), "-i", str(audio_downloaded), 
                                     "-c", "copy", str(final_path), "-y"]
                        logging.info(f"Trying simpler FFmpeg command: {' '.join(ffmpeg_cmd)}")
                        result = subprocess.run(ffmpeg_cmd, 
                                               stdout=subprocess.PIPE, 
                                               stderr=subprocess.PIPE, 
                                               text=True, 
                                               check=False)
                    
                    if result.returncode == 0 and final_path.exists():
                        # Clean up temp files only if successful
                        try:
                            if os.path.exists(video_downloaded):
                                os.remove(video_downloaded)
                            if os.path.exists(audio_downloaded):
                                os.remove(audio_downloaded)
                        except Exception as e:
                            logging.warning(f"Error cleaning up temp files: {str(e)}")
                            
                        logging.info(f"Successfully merged video and audio for Reddit video")
                        return str(final_path)
                    else:
                        logging.error(f"FFmpeg merge failed: {result.stderr}")
                except Exception as e:
                    logging.error(f"Error during FFmpeg execution: {str(e)}")
                
                # If we're here, ffmpeg failed - manually copy video file as last resort
                shutil.copy2(video_downloaded, final_path)
                logging.warning(f"Audio merge failed, returning video only")
                return str(final_path)
            else:
                # No audio found, just return the video
                logging.warning(f"No audio found for Reddit video, returning video only")
                video_final_path = filepath.with_suffix('.mp4')
                shutil.copy2(video_downloaded, video_final_path)
                return str(video_final_path)
        return None
    except Exception as e:
        logging.error(f"Error in download_reddit_video: {str(e)}")
        return None

def download_with_requests(url, filepath):
    """Fallback function to download media using requests"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Referer': 'https://www.reddit.com/',
            'Origin': 'https://www.reddit.com',
        }
        response = requests.get(url, stream=True, headers=headers, timeout=15)
        if response.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            if Path(filepath).exists() and os.path.getsize(filepath) > 0:
                logging.info(f"Downloaded {url} successfully with requests, size: {os.path.getsize(filepath)} bytes")
                return str(filepath)
            else:
                logging.error(f"File not created or empty for {url}")
                return None
        else:
            logging.error(f"Failed to download {url}: Status code {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Requests download error for {url}: {str(e)}")
        return None

def extract_folder_id(drive_link):
    """Extract Google Drive folder ID from URL"""
    if not drive_link:
        return None
    patterns = [
        r'https://drive.google.com/drive/folders/([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)',
        r'folders/([a-zA-Z0-9_-]+)'
    ]
    for pattern in patterns:
        match = re.search(pattern, drive_link)
        if match:
            return match.group(1)
    return None

def upload_to_drive(file_path, folder_id=None):
    """Upload file to Google Drive using service account"""
    try:
        file_metadata = {
            'name': os.path.basename(file_path),
        }
        if folder_id:
            file_metadata['parents'] = [folder_id]

        media = MediaFileUpload(file_path, resumable=True)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        return f"https://drive.google.com/file/d/{file.get('id')}/view"
    except Exception as e:
        logging.error(f"Upload error: {str(e)}")
        return None
    
def contains_keywords(text, keywords):
    if not keywords:
        return True
    text = text.lower()
    return any(keyword.lower() in text for keyword in keywords if keyword.strip())

def get_randomized_post_iterator(subreddit_obj, sort_by, limit):
    """Get a randomized iterator of posts from a subreddit"""
    if sort_by == "hot":
        posts = list(subreddit_obj.hot(limit=limit))
    elif sort_by == "new":
        posts = list(subreddit_obj.new(limit=limit))
    elif sort_by == "top":
        posts = list(subreddit_obj.top(limit=limit))
    elif sort_by == "rising":
        posts = list(subreddit_obj.rising(limit=limit))
    else:
        posts = list(subreddit_obj.hot(limit=limit))
    
    random.shuffle(posts)
    return posts

def save_to_local_folder(downloaded_file, local_folder):
    """Save downloaded file to a user-specified local folder"""
    try:
        dest_folder = Path(local_folder)
        dest_folder.mkdir(parents=True, exist_ok=True)
        filename = Path(downloaded_file).name
        dest_path = dest_folder / filename
        shutil.copy2(downloaded_file, dest_path)
        return str(dest_path)
    except Exception as e:
        logging.error(f"Local save error: {str(e)}")
        return None

# FastAPI routes
@app.post("/scrape")
async def scrape_subreddit(
    subreddit: str = Form(...),
    media_types: List[str] = Form(...),
    keywords: str = Form(""),
    sort_by: str = Form("hot"),
    limit: int = Form(25),
    date_after: Optional[str] = Form(None),
    min_upvotes: int = Form(0),
    download_limit: Optional[int] = Form(None),
    save_to_drive: bool = Form(False),
    drive_folder_url: Optional[str] = Form(None),
    save_locally: bool = Form(False),
    local_folder: Optional[str] = Form(None)
):
    media_files = []
    scrape_images = "images" in media_types
    scrape_videos = "videos" in media_types
    
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    date_filter = None
    if date_after:
        try:
            date_filter = datetime.strptime(date_after, "%Y-%m-%d").timestamp()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD."}
    
    folder_id = extract_folder_id(drive_folder_url) if save_to_drive else None
    
    if save_locally and not local_folder:
        return {"error": "Please provide a local folder path to save files"}
    
    if not (scrape_images or scrape_videos):
        return {"error": "Please select at least one media type to scrape"}
    
    try:
        subreddit_obj = reddit.subreddit(subreddit)
        posts = get_randomized_post_iterator(subreddit_obj, sort_by, limit)
        
        for post in posts:
            post_text = f"{post.title} {post.selftext}"
            if date_filter and post.created_utc < date_filter:
                continue
            if post.score < min_upvotes:
                continue
            if not contains_keywords(post_text, keyword_list):
                continue
            
            if scrape_videos and post.is_video:
                video_url = f"https://reddit.com{post.permalink}"
                filename = f"video_{post.id}.mp4"
                downloaded = download_media(video_url, filename, post=post)
                if downloaded:
                    drive_link = upload_to_drive(downloaded, folder_id) if save_to_drive else None
                    local_path = save_to_local_folder(downloaded, local_folder) if save_locally else None
                    media_files.append({
                        "type": "video",
                        "filename": Path(downloaded).name,
                        "title": post.title,
                        "url": video_url,
                        "score": post.score,
                        "created": datetime.fromtimestamp(post.created_utc).strftime("%Y-%m-%d"),
                        "drive_link": drive_link,
                        "local_path": local_path
                    })
                    time.sleep(2)  # Increased rate limiting to avoid 403
                    
            elif scrape_images and (
                "i.redd.it" in post.url or 
                post.url.endswith((".jpg", ".jpeg", ".png", ".gif"))
            ):
                extension = Path(post.url).suffix or ".jpg"
                filename = f"image_{post.id}{extension}"
                downloaded = download_media(post.url, filename)
                if downloaded:
                    drive_link = upload_to_drive(downloaded, folder_id) if save_to_drive else None
                    local_path = save_to_local_folder(downloaded, local_folder) if save_locally else None
                    media_files.append({
                        "type": "image",
                        "filename": Path(downloaded).name,
                        "title": post.title,
                        "url": f"https://reddit.com{post.permalink}",
                        "score": post.score,
                        "created": datetime.fromtimestamp(post.created_utc).strftime("%Y-%m-%d"),
                        "drive_link": drive_link,
                        "local_path": local_path
                    })
                    time.sleep(2)  # Increased rate limiting to avoid 403
            
            if download_limit is not None and len(media_files) >= download_limit:
                break
    
    except Exception as e:
        logging.error(f"Scrape error: {str(e)}")
        return {"error": str(e)}

    return {
        "subreddit": subreddit,
        "sort_by": sort_by,
        "media_types": media_types,
        "keywords": keywords,
        "date_after": date_after,
        "min_upvotes": min_upvotes,
        "download_limit": download_limit,
        "save_to_drive": save_to_drive,
        "drive_folder_url": drive_folder_url,
        "save_locally": save_locally,
        "local_folder": local_folder if save_locally else None,
        "randomized": True,
        "media": media_files
    }

@app.get("/download/{filename}")
async def download(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if file_path.exists():
        return FileResponse(path=file_path, filename=filename)
    return {"error": "File not found"}

@app.get("/local-downloads")
async def list_local_downloads(folder_path: str):
    """List all files in a local download folder"""
    try:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return {"error": "Invalid folder path"}
        
        files = []
        for file_path in folder.glob("*"):
            if file_path.is_file():
                files.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                    "created": datetime.fromtimestamp(file_path.stat().st_ctime).strftime("%Y-%m-%d %H:%M:%S")
                })
        
        return {"folder": folder_path, "files": files}
    except Exception as e:
        logging.error(f"List local downloads error: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
