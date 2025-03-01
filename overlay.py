import cv2
import numpy as np
import os
import subprocess
import io
import tempfile
import shutil
from typing import Optional, Union
from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import logging

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='video_overlay.log'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Video Overlay API")

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"]
)

# Configuration for Google Drive
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
SERVICE_ACCOUNT_FILE = 'service_account.json'

class DriveVideoInput(BaseModel):
    drive_id: str = Field(..., description="Google Drive file ID of the video")

class OverlayParams(BaseModel):
    position: str = Field("top_right", description="Position of overlay: top_left, top_right, bottom_left, bottom_right")
    scale: float = Field(0.3, gt=0, le=1, description="Scale factor for overlay video (0-1)")
    main_volume: float = Field(1.0, gt=0, le=2, description="Volume level for main video (0-2)")
    overlay_volume: float = Field(1.0, gt=0, le=2, description="Volume level for overlay video (0-2)")
    speed_factor: float = Field(1.0, gt=0, le=4, description="Playback speed factor (0.25-4)")

def get_google_drive_service():
    """Initialize and return Google Drive service using service account."""
    try:
        credentials = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, 
            scopes=SCOPES
        )
        return build('drive', 'v3', credentials=credentials)
    except Exception as e:
        logger.error(f"Error initializing Drive service: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to initialize Google Drive service"
        )

async def download_from_drive(file_id: str, destination_path: str):
    """Download a file from Google Drive using service account."""
    try:
        service = get_google_drive_service()
        request = service.files().get_media(fileId=file_id)
        
        with io.FileIO(destination_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                if status:
                    logger.debug(f"Download progress: {int(status.progress() * 100)}%")
                    
    except Exception as e:
        logger.error(f"Failed to download from Drive: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to download file from Google Drive: {str(e)}"
        )

async def upload_to_drive(file_path: str, filename: str) -> str:
    """Upload a file to Google Drive and return its file ID."""
    try:
        service = get_google_drive_service()
        
        file_metadata = {
            'name': filename,
            'mimeType': 'video/mp4'
        }
        
        media = MediaFileUpload(
            file_path,
            mimetype='video/mp4',
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        return file.get('id')
        
    except Exception as e:
        logger.error(f"Failed to upload to Drive: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file to Google Drive: {str(e)}"
        )

def log_operation(user: str, operation: str):
    """Log operation details with timestamp."""
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - User: {user} - {operation}\n"
    logger.info(f"Operation - User: {user} - {operation}")
    with open('video_operations.log', 'a') as log_file:
        log_file.write(log_entry)

def process_video_overlay(main_video_path, overlay_video_path, output_path, position='top_right', 
                         scale=0.3, main_volume=1.0, overlay_volume=1.0, speed_factor=1.0):
    # [Keep your existing implementation]
    logger.debug(f"Processing video with params: position={position}, scale={scale}, "
                f"main_volume={main_volume}, overlay_volume={overlay_volume}, speed_factor={speed_factor}")
    # Add logging at key steps in your existing implementation

@app.post("/overlay-video/")
async def overlay_video(
    main_video: Union[UploadFile, None] = File(None),
    overlay_video: Union[UploadFile, None] = File(None),
    main_video_drive_id: Union[str, None] = None,
    overlay_video_drive_id: Union[str, None] = None,
    params: OverlayParams = OverlayParams(),
    upload_to_drive: bool = False
):
    """
    API endpoint to overlay one video onto another with customizable parameters.
    Accepts either direct file uploads or Google Drive file IDs.
    """
    user = "d0ughnat"  # Get from your authentication system
    logger.info(f"Request received - Main video: {bool(main_video)}, Overlay video: {bool(overlay_video)}, "
               f"Main Drive ID: {main_video_drive_id}, Overlay Drive ID: {overlay_video_drive_id}")
    log_operation(user, "Started video overlay process")

    if not ((main_video or main_video_drive_id) and (overlay_video or overlay_video_drive_id)):
        logger.error("Missing required video inputs")
        raise HTTPException(
            status_code=400,
            detail="Must provide either file uploads or Google Drive IDs for both videos"
        )

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            main_path = os.path.join(tmp_dir, "main_video.mp4")
            overlay_path = os.path.join(tmp_dir, "overlay_video.mp4")
            output_path = os.path.join(tmp_dir, "output.mp4")

            # Handle main video input
            if main_video:
                logger.debug("Processing uploaded main video")
                with open(main_path, "wb") as main_file:
                    shutil.copyfileobj(main_video.file, main_file)
                log_operation(user, f"Saved uploaded main video")
            elif main_video_drive_id:
                logger.debug(f"Downloading main video from Drive ID: {main_video_drive_id}")
                await download_from_drive(main_video_drive_id, main_path)
                log_operation(user, f"Downloaded main video from Drive ID: {main_video_drive_id}")

            # Handle overlay video input
            if overlay_video:
                logger.debug("Processing uploaded overlay video")
                with open(overlay_path, "wb") as overlay_file:
                    shutil.copyfileobj(overlay_video.file, overlay_file)
                log_operation(user, f"Saved uploaded overlay video")
            elif overlay_video_drive_id:
                logger.debug(f"Downloading overlay video from Drive ID: {overlay_video_drive_id}")
                await download_from_drive(overlay_video_drive_id, overlay_path)
                log_operation(user, f"Downloaded overlay video from Drive ID: {overlay_video_drive_id}")

            # Process the video
            process_video_overlay(
                main_path,
                overlay_path,
                output_path,
                position=params.position,
                scale=params.scale,
                main_volume=params.main_volume,
                overlay_volume=params.overlay_volume,
                speed_factor=params.speed_factor
            )

            if not os.path.exists(output_path):
                logger.error("Output video file not created")
                raise HTTPException(status_code=500, detail="Video processing failed")

            log_operation(user, "Video processing completed successfully")

            # Handle the output
            if upload_to_drive:
                timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                filename = f"processed_video_{timestamp}.mp4"
                logger.debug(f"Uploading to Drive as: {filename}")
                drive_id = await upload_to_drive(output_path, filename)
                log_operation(user, f"Uploaded result to Drive with ID: {drive_id}")
                return {"drive_file_id": drive_id}
            else:
                log_operation(user, "Returning processed video file")
                logger.debug("Returning file response")
                return FileResponse(
                    output_path,
                    filename="processed_video.mp4",
                    media_type="video/mp4"
                )

    except HTTPException as e:
        logger.error(f"HTTP Exception: {str(e.detail)}")
        raise
    except Exception as e:
        error_message = f"Processing error: {str(e)}"
        logger.error(error_message)
        log_operation(user, f"Error: {error_message}")
        raise HTTPException(status_code=500, detail=error_message)
    finally:
        if main_video:
            main_video.file.close()
        if overlay_video:
            overlay_video.file.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
