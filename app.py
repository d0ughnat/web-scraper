from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import praw
import os
import requests
from yt_dlp import YoutubeDL
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import re
import random
import shutil
import time
import logging
import subprocess
import tempfile

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Enable CORS for all required origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "https://choros.io", "https://web-scraper-henna.vercel.app/", "*"],
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

# Google Drive API setup
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service_account.json")
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# Download directory for scraper
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Startup event to check FFmpeg
@app.on_event("startup")
async def startup_event():
    if not shutil.which("ffmpeg"):
        logger.error("FFmpeg is not installed on the server")
        raise RuntimeError("FFmpeg is not installed on the server")
    try:
        result = subprocess.run(["ffmpeg", "-codecs"], capture_output=True, text=True, check=True)
        if "libx264" not in result.stdout:
            logger.error("FFmpeg lacks libx264 support")
            raise RuntimeError("FFmpeg lacks libx264 support")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to check FFmpeg codecs: {e.stderr}")
        raise RuntimeError("Failed to verify FFmpeg installation")

# Helper functions (from both apps)
def download_media(url, filename, post=None):
    """Download media file with support for multiple platforms"""
    logger.info(f"Attempting to download: {url}")
    try:
        filepath = DOWNLOAD_DIR / filename
        video_platforms = ['youtube.com', 'youtu.be', 'reddit.com/r', 'v.redd.it', 'vimeo.com', 'dailymotion.com', 'facebook.com']
        
        if any(platform in url.lower() for platform in video_platforms):
            cookies_file = os.getenv("REDDIT_COOKIES_FILE")
            if cookies_file and not os.path.exists(cookies_file):
                logger.warning(f"Cookies file {cookies_file} not found")
                cookies_file = None
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': str(filepath),
                'merge_output_format': 'mp4',
                'postprocessors': [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}],
                'cookiefile': cookies_file,
                'username': os.getenv("REDDIT_USERNAME"),
                'password': os.getenv("REDDIT_PASSWORD"),
            }
            with YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                    if filepath.exists():
                        return str(filepath)
                except Exception as e:
                    logger.error(f"yt-dlp failed: {str(e)}")
            if post and post.is_video and 'reddit_video' in post.media:
                return download_reddit_video(post, filepath)
            return download_with_requests(url, filepath)
        else:
            return download_with_requests(url, filepath)
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return None

def download_reddit_video(post, filepath):
    """Download Reddit video with audio"""
    if not post.is_video or 'reddit_video' not in post.media:
        return None
    video_url = post.media['reddit_video']['fallback_url']
    base_url = video_url.rsplit('/', 1)[0]
    video_path = filepath.with_suffix('.video.mp4')
    audio_path = filepath.with_suffix('.audio.mp4')
    final_path = filepath.with_suffix('.mp4')
    
    video_downloaded = download_with_requests(video_url, video_path)
    if not video_downloaded:
        return None
    
    audio_urls = [f"{base_url}/DASH_audio.mp4", f"{base_url}/audio"]
    audio_downloaded = None
    for audio_url in audio_urls:
        audio_downloaded = download_with_requests(audio_url, audio_path)
        if audio_downloaded:
            break
    
    if video_downloaded:
        if audio_downloaded:
            try:
                subprocess.run(
                    ["ffmpeg", "-i", str(video_downloaded), "-i", str(audio_downloaded), "-c:v", "copy", "-c:a", "aac", str(final_path), "-y"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                os.remove(video_downloaded)
                os.remove(audio_downloaded)
                return str(final_path)
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg merge failed: {e.stderr.decode()}")
        shutil.copy2(video_downloaded, final_path)
        return str(final_path)
    return None

def download_with_requests(url, filepath):
    """Download media using requests"""
    try:
        response = requests.get(url, stream=True, timeout=15)
        if response.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            if Path(filepath).exists():
                return str(filepath)
        return None
    except Exception as e:
        logger.error(f"Requests download error: {str(e)}")
        return None

def extract_folder_id(drive_link):
    """Extract Google Drive folder ID from URL"""
    if not drive_link:
        return None
    match = re.search(r'folders/([a-zA-Z0-9_-]+)', drive_link) or re.search(r'id=([a-zA-Z0-9_-]+)', drive_link)
    return match.group(1) if match else None

def upload_to_drive(file_path, folder_id=None):
    """Upload file to Google Drive and set public permissions"""
    try:
        file_metadata = {'name': os.path.basename(file_path)}
        if folder_id:
            file_metadata['parents'] = [folder_id]
        media = MediaFileUpload(file_path, resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        drive_service.permissions().create(fileId=file.get('id'), body={'type': 'anyone', 'role': 'reader'}).execute()
        return f"https://drive.google.com/file/d/{file.get('id')}/view"
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return None

def contains_keywords(text, keywords):
    if not keywords:
        return True
    return any(keyword.lower() in text.lower() for keyword in keywords if keyword.strip())

def get_randomized_post_iterator(subreddit_obj, sort_by, limit):
    posts = {
        "hot": subreddit_obj.hot,
        "new": subreddit_obj.new,
        "top": subreddit_obj.top,
        "rising": subreddit_obj.rising,
    }.get(sort_by, subreddit_obj.hot)(limit=limit)
    posts_list = list(posts)
    random.shuffle(posts_list)
    return posts_list

def save_to_local_folder(downloaded_file, local_folder):
    """Save file to a local folder"""
    try:
        dest_folder = Path(local_folder)
        dest_folder.mkdir(parents=True, exist_ok=True)
        if not os.access(dest_folder, os.W_OK):
            raise PermissionError(f"No write permission to {dest_folder}")
        dest_path = dest_folder / Path(downloaded_file).name
        shutil.copy2(downloaded_file, dest_path)
        return str(dest_path)
    except Exception as e:
        logger.error(f"Local save error: {str(e)}")
        return None

# Scraper endpoints
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
    date_filter = datetime.strptime(date_after, "%Y-%m-%d").timestamp() if date_after else None
    folder_id = extract_folder_id(drive_folder_url) if save_to_drive else None

    if save_locally and not local_folder:
        raise HTTPException(status_code=400, detail="Please provide a local folder path")
    if not (scrape_images or scrape_videos):
        raise HTTPException(status_code=400, detail="Select at least one media type")

    try:
        subreddit_obj = reddit.subreddit(subreddit)
        posts = get_randomized_post_iterator(subreddit_obj, sort_by, limit)
        for post in posts:
            post_text = f"{post.title} {post.selftext}"
            if date_filter and post.created_utc < date_filter:
                continue
            if post.score < min_upvotes or not contains_keywords(post_text, keyword_list):
                continue
            if scrape_videos and post.is_video:
                video_url = f"https://reddit.com{post.permalink}"
                filename = f"video_{post.id}.mp4"
                downloaded = download_media(video_url, filename, post=post)
                if downloaded:
                    drive_link = upload_to_drive(downloaded, folder_id) if save_to_drive else None
                    local_path = save_to_local_folder(downloaded, local_folder) if save_locally else None
                    media_files.append({"type": "video", "filename": Path(downloaded).name, "title": post.title, "url": video_url, "drive_link": drive_link, "local_path": local_path})
                    time.sleep(2)
            elif scrape_images and ("i.redd.it" in post.url or post.url.endswith((".jpg", ".jpeg", ".png", ".gif"))):
                extension = Path(post.url).suffix or ".jpg"
                filename = f"image_{post.id}{extension}"
                downloaded = download_media(post.url, filename)
                if downloaded:
                    drive_link = upload_to_drive(downloaded, folder_id) if save_to_drive else None
                    local_path = save_to_local_folder(downloaded, local_folder) if save_locally else None
                    media_files.append({"type": "image", "filename": Path(downloaded).name, "title": post.title, "url": post.url, "drive_link": drive_link, "local_path": local_path})
                    time.sleep(2)
            if download_limit and len(media_files) >= download_limit:
                break
        return {"media": media_files}
    except Exception as e:
        logger.error(f"Scrape error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{filename}")
async def download(filename: str):
    file_path = DOWNLOAD_DIR / filename
    if file_path.exists():
        return FileResponse(path=file_path, filename=filename)
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/local-downloads")
async def list_local_downloads(folder_path: str):
    try:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            raise HTTPException(status_code=400, detail="Invalid folder path")
        files = [{"name": f.name, "path": str(f)} for f in folder.glob("*") if f.is_file()]
        return {"folder": folder_path, "files": files}
    except Exception as e:
        logger.error(f"List error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Converter endpoint
@app.post("/convert-to-mp4")
async def convert_to_mp4(file: UploadFile = File(...), folder_id: str = Form(default='')):
    logger.info(f"Converting file: {file.filename}")
    temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    try:
        temp_input.write(await file.read())
        temp_input.close()
        subprocess.run(
            ["ffmpeg", "-i", temp_input.name, "-c:v", "libx264", "-c:a", "aac", "-y", temp_output.name],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        file_metadata = {'name': file.filename.replace('.webm', '.mp4')}
        if folder_id:
            file_metadata['parents'] = [folder_id]
        media = MediaFileUpload(temp_output.name, mimetype='video/mp4')
        uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = uploaded_file.get('id')
        drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
        return {
            "download_url": f"https://drive.google.com/uc?export=download&id={file_id}",
            "view_url": f"https://drive.google.com/file/d/{file_id}/view",
            "file_id": file_id
        }
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed: {e.stderr.decode()}")
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e.stderr.decode()}")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_input.name):
            os.unlink(temp_input.name)
        if os.path.exists(temp_output.name):
            os.unlink(temp_output.name)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
