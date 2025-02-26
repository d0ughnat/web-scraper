# app.py
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

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

# Enable CORS to allow React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://web-scraper-henna.vercel.app"],  # React dev server (Vite default)
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

# Your helper functions (download_media, download_with_requests, etc.)
def download_media(url, filename):
    """Download media file with support for YouTube and other video platforms"""
    try:
        filepath = DOWNLOAD_DIR / filename
        
        # Check if it's a video URL that yt-dlp can handle
        video_platforms = [
            'youtube.com', 'youtu.be', 'reddit.com/r', 'v.redd.it',
            'vimeo.com', 'dailymotion.com', 'facebook.com'
        ]
        
        if any(platform in url.lower() for platform in video_platforms):
            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',  # Prioritize mp4 with audio
                'outtmpl': str(filepath),
                'merge_output_format': 'mp4',          # Merge into mp4
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }, {
                    'key': 'FFmpegEmbedSubtitle',
                }, {
                    'key': 'FFmpegMetadata',
                }],
                'prefer_ffmpeg': True,                # Ensure ffmpeg is used for merging
                'keepvideo': False,                   # Don't keep the video file after merging
                'quiet': True,
                'no_warnings': True,
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                try:
                    ydl.download([url])
                    return str(filepath) if filepath.exists() else None
                except Exception as e:
                    print(f"yt-dlp download failed: {str(e)}")
                    # Fallback to regular download if yt-dlp fails
                    return download_with_requests(url, filepath)
        else:
            # Use regular request download for other media types
            return download_with_requests(url, filepath)
            
    except Exception as e:
        print(f"Download error: {str(e)}")
    return None

def download_with_requests(url, filepath):
    """Fallback function to download media using requests"""
    try:
        response = requests.get(url, stream=True, timeout=10)
        if response.status_code == 200:
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return str(filepath) if Path(filepath).exists() else None
        else:
            print(f"Failed to download {url}: Status code {response.status_code}")
            return None
    except Exception as e:
        print(f"Requests download error: {str(e)}")
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
        print(f"Upload error: {str(e)}")
        return None
    
def contains_keywords(text, keywords):
    if not keywords:
        return True
    text = text.lower()
    return any(keyword.lower() in text for keyword in keywords if keyword.strip())


def get_randomized_post_iterator(subreddit_obj, sort_by, limit):
    """Get a randomized iterator of posts from a subreddit"""
    # First collect posts according to the sort method
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
    
    # Shuffle the posts for randomization
    random.shuffle(posts)
    
    return posts

def save_to_local_folder(downloaded_file, local_folder):
    """Save downloaded file to a user-specified local folder"""
    try:
        # Create destination folder if it doesn't exist
        dest_folder = Path(local_folder)
        dest_folder.mkdir(parents=True, exist_ok=True)
        
        # Get the filename from the downloaded file path
        filename = Path(downloaded_file).name
        
        # Create destination path
        dest_path = dest_folder / filename
        
        # Copy the file to the destination
        shutil.copy2(downloaded_file, dest_path)
        
        return str(dest_path)
    except Exception as e:
        print(f"Local save error: {str(e)}")
        return None

# Your FastAPI routes
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
    
    # Validate local folder path if saving locally
    if save_locally and not local_folder:
        return {"error": "Please provide a local folder path to save files"}
    
    if not (scrape_images or scrape_videos):
        return {"error": "Please select at least one media type to scrape"}
    
    try:
        subreddit_obj = reddit.subreddit(subreddit)
        # Get randomized post iterator instead of sequential one
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
                # Use the full Reddit post URL for video downloads
                video_url = f"https://reddit.com{post.permalink}"
                filename = f"video_{post.id}.mp4"
                downloaded = download_media(video_url, filename)
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
            
            # Check if we've reached the download limit
            if download_limit is not None and len(media_files) >= download_limit:
                break
    
    except Exception as e:
        return {"error": str(e)}

    # Adding randomization stats to the response
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
        return {"error": str(e)}
