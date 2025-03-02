import cv2
import numpy as np
import os
import subprocess
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
import shutil
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import requests
from urllib.parse import urlparse, parse_qs
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
import json
import io
import tempfile
import logging
import re

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
CREDENTIALS_FOLDER = "credentials"
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(CREDENTIALS_FOLDER, exist_ok=True)

# Google Drive Credentials Setup
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service_account.json")
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_filename(filename: str) -> str:
    """Remove URL query parameters from filename."""
    return re.sub(r'\?.*$', '', filename)

def extract_folder_id(folder_input: str) -> str:
    """Extract folder ID from either a full Google Drive URL or a plain ID."""
    if not folder_input:
        return None
    if folder_input.startswith('http'):
        match = re.search(r'folders/([a-zA-Z0-9_-]+)', folder_input)
        if match:
            return match.group(1)
        parsed = urlparse(folder_input)
        if parsed.query:
            params = parse_qs(parsed.query)
            if 'id' in params:
                return params['id'][0]
        raise ValueError("Invalid Google Drive folder URL")
    return folder_input

def download_from_gdrive(gdrive_url: str, output_path: str) -> str:
    """Download a file from Google Drive using the URL."""
    try:
        parsed_url = urlparse(gdrive_url)
        file_id = None
        
        if 'drive.google.com/file/d/' in gdrive_url:
            file_id = gdrive_url.split('/file/d/')[1].split('/')[0]
        elif 'drive.google.com/open?id=' in gdrive_url:
            file_id = parse_qs(parsed_url.query)['id'][0]
        elif 'docs.google.com' in gdrive_url and 'export=download' in gdrive_url:
            file_id = parse_qs(parsed_url.query)['id'][0]
        else:
            raise ValueError("Invalid Google Drive URL format")
            
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        session = requests.Session()
        response = session.get(download_url, stream=True)
        
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                download_url = f"{download_url}&confirm={value}"
                response = session.get(download_url, stream=True)
                break
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        
        return output_path
    
    except Exception as e:
        raise ValueError(f"Failed to download from Google Drive: {str(e)}")

def get_drive_service():
    """Create a Google Drive service instance using the service account."""
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")
    
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(file_path, folder_id=None):
    """Upload file to Google Drive and set public permissions"""
    try:
        folder_id = extract_folder_id(folder_id) if folder_id else None
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

def upload_to_gdrive_stream(file_stream: io.BytesIO, filename: str, folder_id: str = None) -> dict:
    """Upload a file stream directly to Google Drive using service account."""
    try:
        service = get_drive_service()
        folder_id = extract_folder_id(folder_id) if folder_id else None
        
        file_metadata = {'name': filename}
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        media = MediaIoBaseUpload(file_stream, mimetype='video/mp4', resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,name,webViewLink'
        ).execute()
        
        permission = {'type': 'anyone', 'role': 'reader'}
        service.permissions().create(fileId=file.get('id'), body=permission).execute()
        
        return {
            'id': file.get('id'),
            'name': file.get('name'),
            'webViewLink': file.get('webViewLink'),
            'downloadLink': f"https://drive.google.com/uc?export=download&id={file.get('id')}"
        }
    except Exception as e:
        raise Exception(f"Failed to upload to Google Drive: {str(e)}")

async def process_video_overlay(main_video_path: str, overlay_video_path: str, output_path: str = None, 
                               position: str = "bottom_right", scale: float = 0.3,
                               main_volume: float = 1.0, overlay_volume: float = 1.0, 
                               speed_factor: float = 1.0, x: int = None, y: int = None,
                               opacity: float = 1.0, custom_layout: bool = False,
                               stream_to_drive: bool = False, folder_id: str = None):
    if not os.path.exists(main_video_path):
        raise FileNotFoundError(f"Main video file not found: {main_video_path}")
    if not os.path.exists(overlay_video_path):
        raise FileNotFoundError(f"Overlay video file not found: {overlay_video_path}")

    main_cap = cv2.VideoCapture(main_video_path)
    overlay_cap = cv2.VideoCapture(overlay_video_path)

    if not main_cap.isOpened() or not overlay_cap.isOpened():
        raise IOError("Failed to open video files")

    main_width = int(main_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    main_height = int(main_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    original_fps = main_cap.get(cv2.CAP_PROP_FPS)
    main_frame_count = int(main_cap.get(cv2.CAP_PROP_FRAME_COUNT))
    main_duration = main_frame_count / original_fps if original_fps > 0 else 0

    if main_width <= 0 or main_height <= 0:
        raise ValueError("Invalid main video dimensions")

    adjusted_fps = original_fps * speed_factor
    fourcc = cv2.VideoWriter_fourcc(*'XVID')

    temp_file = tempfile.NamedTemporaryFile(suffix='.avi', delete=False)
    temp_output = temp_file.name
    out = cv2.VideoWriter(temp_output, fourcc, adjusted_fps, (main_width, main_height))

    valid_positions = {'top_left', 'top_right', 'bottom_left', 'bottom_right', 'center', 'custom'}
    if position not in valid_positions and not custom_layout:
        raise ValueError(f"Invalid position. Must be one of: {', '.join(valid_positions)}")

    try:
        frame_count = 0
        while True:
            main_ret, main_frame = main_cap.read()
            overlay_ret, overlay_frame = overlay_cap.read()

            if not main_ret:
                break

            frame_count += 1
            if frame_count % 100 == 0:
                print(f"Processed {frame_count} frames")

            if not overlay_ret:
                overlay_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                _, overlay_frame = overlay_cap.read()

            overlay_height, overlay_width = overlay_frame.shape[:2]
            new_height = int(overlay_height * scale)
            new_width = int(overlay_width * scale)
            
            if new_height <= 0 or new_width <= 0:
                raise ValueError("Overlay scale resulted in invalid dimensions")
                
            overlay_resized = cv2.resize(overlay_frame, (new_width, new_height))
            h, w = overlay_resized.shape[:2]

            if (position == 'custom' or custom_layout) and x is not None and y is not None:
                x_pos, y_pos = x, y
            elif position == 'top_left':
                x_pos, y_pos = 10, 10
            elif position == 'top_right':
                x_pos, y_pos = main_width - w - 10, 10
            elif position == 'bottom_left':
                x_pos, y_pos = 10, main_height - h - 10
            elif position == 'bottom_right':
                x_pos, y_pos = main_width - w - 10, main_height - h - 10
            elif position == 'center':
                x_pos, y_pos = (main_width - w) // 2, (main_height - h) // 2
            else:
                x_pos, y_pos = main_width - w - 10, main_height - h - 10

            x_pos = max(0, min(x_pos, main_width - w))
            y_pos = max(0, min(y_pos, main_height - h))

            if y_pos + h > main_height or x_pos + w > main_width:
                logger.warning(f"Overlay dimensions exceed main frame at frame {frame_count}")
                continue

            if opacity < 1.0:
                roi = main_frame[y_pos:y_pos+h, x_pos:x_pos+w]
                if roi.shape[0] != h or roi.shape[1] != w:
                    logger.warning(f"ROI shape mismatch at frame {frame_count}")
                    continue
                    
                overlay_gray = cv2.cvtColor(overlay_resized, cv2.COLOR_BGR2GRAY)
                _, mask = cv2.threshold(overlay_gray, 10, 255, cv2.THRESH_BINARY)
                mask_inv = cv2.bitwise_not(mask)
                background = cv2.bitwise_and(roi, roi, mask=mask_inv)
                foreground = cv2.addWeighted(overlay_resized, opacity, np.zeros_like(overlay_resized), 0, 0)
                foreground = cv2.bitwise_and(foreground, foreground, mask=mask)
                main_frame[y_pos:y_pos+h, x_pos:x_pos+w] = cv2.add(background, foreground)
            else:
                main_frame[y_pos:y_pos+h, x_pos:x_pos+w] = overlay_resized

            out.write(main_frame)

        print(f"Processed {frame_count} frames total.")

        if frame_count == 0:
            raise RuntimeError("No frames processed.")

        # Base FFmpeg command
        base_ffmpeg_cmd = [
            'ffmpeg',
            '-i', temp_output,
            '-i', main_video_path,
            '-stream_loop', '-1',
            '-i', overlay_video_path,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-filter_complex',
            f'[0:v]setpts={1/speed_factor}*PTS[v];'
            f'[1:a]volume={main_volume}[main_a];'
            f'[2:a]volume={overlay_volume}[overlay_a];'
            '[main_a][overlay_a]amix=inputs=2:duration=longest[mixed_a]',
            '-map', '[v]',
            '-map', '[mixed_a]',
            '-r', str(original_fps),
            '-t', str(main_duration),
            '-y'
        ]

        drive_result = None
        if stream_to_drive:
            # Streaming output to pipe
            ffmpeg_cmd = base_ffmpeg_cmd.copy()
            ffmpeg_cmd.extend(['-f', 'mp4', 'pipe:'])
            logger.info(f"Executing FFmpeg streaming command: {' '.join(ffmpeg_cmd)}")
            output_buffer = io.BytesIO()
            process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {stderr.decode()}")
            output_buffer.write(stdout)
            output_buffer.seek(0)
            print(f"FFmpeg stderr: {stderr.decode()}")
            
            output_filename = os.path.basename(clean_filename(output_path) or "processed_video.mp4")
            drive_result = upload_to_gdrive_stream(output_buffer, output_filename, folder_id)
            output_buffer.close()
        else:
            # File output
            ffmpeg_output = clean_filename(output_path) if output_path else tempfile.mktemp(suffix='.mp4')
            ffmpeg_cmd = base_ffmpeg_cmd.copy()
            ffmpeg_cmd.append(ffmpeg_output)
            logger.info(f"Executing FFmpeg file command: {' '.join(ffmpeg_cmd)}")
            process = subprocess.run(ffmpeg_cmd, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            print(f"FFmpeg stderr: {process.stderr.decode()}")
            
            if not os.path.exists(ffmpeg_output):
                raise RuntimeError("Output file not created.")
            
            if upload_to_drive:
                drive_result = upload_to_drive(ffmpeg_output, folder_id)
                if os.path.exists(ffmpeg_output):
                    os.remove(ffmpeg_output)  # Clean up temporary file
                return drive_result if drive_result else ffmpeg_output
            return ffmpeg_output

        return drive_result if stream_to_drive else ffmpeg_output

    finally:
        main_cap.release()
        overlay_cap.release()
        out.release()
        cv2.destroyAllWindows()
        if os.path.exists(temp_output):
            os.remove(temp_output)

@app.post("/process-video/")
async def process_video_endpoint(
    main_video: UploadFile = File(None),
    overlay_video: UploadFile = File(None),
    main_video_url: Optional[str] = Form(None),
    overlay_video_url: Optional[str] = Form(None),
    position: str = Form("bottom_right"),
    scale: float = Form(0.3),
    main_volume: float = Form(1.0),
    overlay_volume: float = Form(1.0),
    speed_factor: float = Form(1.0),
    x: Optional[int] = Form(None),
    y: Optional[int] = Form(None),
    opacity: float = Form(1.0),
    custom_layout: bool = Form(False),
    upload_to_drive: bool = Form(False),
    drive_folder_id: Optional[str] = Form(None)
):
    try:
        main_path = None
        overlay_path = None
        
        if main_video:
            if not allowed_file(main_video.filename):
                raise HTTPException(status_code=400, detail="Invalid main video file format")
            main_path = os.path.join(UPLOAD_FOLDER, clean_filename(main_video.filename))
            with open(main_path, "wb") as main_file:
                shutil.copyfileobj(main_video.file, main_file)
        elif main_video_url:
            main_filename = f"main_video_{clean_filename(os.path.basename(main_video_url))}"
            if '.' not in main_filename:
                main_filename += '.mp4'
            main_path = os.path.join(UPLOAD_FOLDER, main_filename)
            main_path = download_from_gdrive(main_video_url, main_path)
        else:
            raise HTTPException(status_code=400, detail="Either main_video file or main_video_url must be provided")
        
        if overlay_video:
            if not allowed_file(overlay_video.filename):
                raise HTTPException(status_code=400, detail="Invalid overlay video file format")
            overlay_path = os.path.join(UPLOAD_FOLDER, clean_filename(overlay_video.filename))
            with open(overlay_path, "wb") as overlay_file:
                shutil.copyfileobj(overlay_video.file, overlay_file)
        elif overlay_video_url:
            overlay_filename = f"overlay_video_{clean_filename(os.path.basename(overlay_video_url))}"
            if '.' not in overlay_filename:
                overlay_filename += '.mp4'
            overlay_path = os.path.join(UPLOAD_FOLDER, overlay_filename)
            overlay_path = download_from_gdrive(overlay_video_url, overlay_path)
        else:
            raise HTTPException(status_code=400, detail="Either overlay_video file or overlay_video_url must be provided")
        
        output_filename = f"processed_{clean_filename(os.path.basename(main_path))}"
        if not output_filename.endswith('.mp4'):
            output_filename = os.path.splitext(output_filename)[0] + '.mp4'
        output_path = os.path.join(OUTPUT_FOLDER, output_filename) if not upload_to_drive else None

        result = await process_video_overlay(
            main_video_path=main_path,
            overlay_video_path=overlay_path,
            output_path=output_path,
            position=position,
            scale=scale,
            main_volume=main_volume,
            overlay_volume=overlay_volume,
            speed_factor=speed_factor,
            x=x,
            y=y,
            opacity=opacity,
            custom_layout=custom_layout,
            stream_to_drive=upload_to_drive,
            folder_id=drive_folder_id
        )

        for path in [main_path, overlay_path]:
            if path and os.path.exists(path):
                os.remove(path)

        response = {}
        if upload_to_drive and isinstance(result, (dict, str)):
            if isinstance(result, dict):
                response["drive_upload"] = result
            else:
                response["drive_upload"] = {"webViewLink": result}
        else:
            response["output_path"] = output_filename

        return JSONResponse(content=response)

    except Exception as e:
        for path in [main_path, overlay_path]:
            if path and os.path.exists(path):
                os.remove(path)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-to-drive/")
async def upload_to_drive_endpoint(
    file_name: str = Form(...),
    folder_id: Optional[str] = Form(None)
):
    try:
        file_path = os.path.join(OUTPUT_FOLDER, clean_filename(file_name))
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        result = upload_to_drive(file_path, folder_id)
        if result:
            return {"webViewLink": result}
        raise HTTPException(status_code=500, detail="Failed to upload to Google Drive")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{filename}")
async def download_file(filename: str):
    # First try the direct path
    file_path = os.path.join(OUTPUT_FOLDER, clean_filename(filename))
    
    # If file doesn't exist, check if it might have an mp4 extension
    if not os.path.exists(file_path) and not filename.endswith('.mp4'):
        file_path = os.path.join(OUTPUT_FOLDER, clean_filename(filename) + '.mp4')
    
    # If file still doesn't exist, try finding any file that might match the base name
    if not os.path.exists(file_path):
        base_name = os.path.splitext(clean_filename(filename))[0]
        for file in os.listdir(OUTPUT_FOLDER):
            if file.startswith(base_name):
                file_path = os.path.join(OUTPUT_FOLDER, file)
                break
    
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=os.path.basename(file_path), media_type="video/mp4")
    
    # Log the attempted file access for debugging
    logger.error(f"File not found: {filename}. Attempted path: {file_path}")
    logger.info(f"Available files in {OUTPUT_FOLDER}: {os.listdir(OUTPUT_FOLDER)}")
    
    raise HTTPException(
        status_code=404, 
        detail=f"File not found: {filename}. Please check if the file was processed successfully."
    )


