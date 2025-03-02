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
    """
    Process video overlay with improved error handling and fixed streaming issues.
    """
    if not main_video_path or not os.path.exists(main_video_path):
        raise FileNotFoundError(f"Main video file not found: {main_video_path}")
    if not overlay_video_path or not os.path.exists(overlay_video_path):
        raise FileNotFoundError(f"Overlay video file not found: {overlay_video_path}")

    logger.info(f"Processing videos: main={main_video_path}, overlay={overlay_video_path}")
    
    # Ensure output_path is a string, even if None was passed in
    if output_path is None:
        output_path = "processed_video.mp4"
    
    # Create temporary files with proper cleanup
    temp_avi = tempfile.NamedTemporaryFile(suffix='.avi', delete=False).name
    temp_mp4 = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
    
    try:
        main_cap = cv2.VideoCapture(main_video_path)
        overlay_cap = cv2.VideoCapture(overlay_video_path)

        if not main_cap.isOpened():
            raise IOError(f"Failed to open main video file: {main_video_path}")
        if not overlay_cap.isOpened():
            raise IOError(f"Failed to open overlay video file: {overlay_video_path}")

        main_width = int(main_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        main_height = int(main_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        original_fps = main_cap.get(cv2.CAP_PROP_FPS)
        main_frame_count = int(main_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        main_duration = main_frame_count / original_fps if original_fps > 0 else 0

        if main_width <= 0 or main_height <= 0:
            raise ValueError(f"Invalid main video dimensions: {main_width}x{main_height}")

        adjusted_fps = original_fps * speed_factor
        fourcc = cv2.VideoWriter_fourcc(*'XVID')

        out = cv2.VideoWriter(temp_avi, fourcc, adjusted_fps, (main_width, main_height))
        if not out.isOpened():
            raise IOError(f"Failed to create output video writer for {temp_avi}")

        valid_positions = {'top_left', 'top_right', 'bottom_left', 'bottom_right', 'center', 'custom'}
        if position not in valid_positions and not custom_layout:
            raise ValueError(f"Invalid position. Must be one of: {', '.join(valid_positions)}")

        frame_count = 0
        while True:
            main_ret, main_frame = main_cap.read()
            
            if not main_ret:
                break

            frame_count += 1
            if frame_count % 100 == 0:
                logger.info(f"Processed {frame_count} frames")

            overlay_ret, overlay_frame = overlay_cap.read()
            if not overlay_ret:
                overlay_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                _, overlay_frame = overlay_cap.read()
                if overlay_frame is None:
                    raise ValueError("Failed to read frames from overlay video")

            overlay_height, overlay_width = overlay_frame.shape[:2]
            new_height = int(overlay_height * scale)
            new_width = int(overlay_width * scale)
            
            if new_height <= 0 or new_width <= 0:
                raise ValueError(f"Overlay scale resulted in invalid dimensions: {new_width}x{new_height}")
                
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
                logger.warning(f"Overlay dimensions exceed main frame at frame {frame_count}, adjusting position")
                x_pos = min(x_pos, main_width - w)
                y_pos = min(y_pos, main_height - h)

            roi_height = min(h, main_height - y_pos)
            roi_width = min(w, main_width - x_pos)
            
            if roi_height <= 0 or roi_width <= 0:
                logger.warning(f"Invalid ROI dimensions at frame {frame_count}, skipping overlay")
                out.write(main_frame)
                continue

            if opacity < 1.0:
                try:
                    roi = main_frame[y_pos:y_pos+roi_height, x_pos:x_pos+roi_width]
                    overlay_part = overlay_resized[:roi_height, :roi_width]
                    
                    overlay_gray = cv2.cvtColor(overlay_part, cv2.COLOR_BGR2GRAY)
                    _, mask = cv2.threshold(overlay_gray, 10, 255, cv2.THRESH_BINARY)
                    mask_inv = cv2.bitwise_not(mask)
                    
                    background = cv2.bitwise_and(roi, roi, mask=mask_inv)
                    foreground = cv2.addWeighted(overlay_part, opacity, np.zeros_like(overlay_part), 0, 0)
                    foreground = cv2.bitwise_and(foreground, foreground, mask=mask)
                    
                    result = cv2.add(background, foreground)
                    main_frame[y_pos:y_pos+roi_height, x_pos:x_pos+roi_width] = result
                except Exception as e:
                    logger.error(f"Error applying overlay with opacity at frame {frame_count}: {str(e)}")
            else:
                try:
                    main_frame[y_pos:y_pos+roi_height, x_pos:x_pos+roi_width] = overlay_resized[:roi_height, :roi_width]
                except Exception as e:
                    logger.error(f"Error applying overlay at frame {frame_count}: {str(e)}")

            out.write(main_frame)

        logger.info(f"Processed {frame_count} frames total")
        
        # Clean up OpenCV resources
        main_cap.release()
        overlay_cap.release()
        out.release()
        cv2.destroyAllWindows()

        if frame_count == 0:
            raise RuntimeError("No frames were processed")

        # Ensure the AVI file was created
        if not os.path.exists(temp_avi) or os.path.getsize(temp_avi) == 0:
            raise RuntimeError(f"Failed to create intermediate video file: {temp_avi}")

        # Determine audio parameters from input files
        main_has_audio = False
        overlay_has_audio = False
        
        try:
            probe_main = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 
                 'stream=codec_type', '-of', 'csv=p=0', main_video_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            main_has_audio = 'audio' in probe_main.stdout.strip()
            
            probe_overlay = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 
                 'stream=codec_type', '-of', 'csv=p=0', overlay_video_path],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            overlay_has_audio = 'audio' in probe_overlay.stdout.strip()
        except Exception as e:
            logger.warning(f"Error checking for audio streams: {str(e)}")
            # Assume both have audio if we can't check
            main_has_audio = True
            overlay_has_audio = True

        # Build FFmpeg command based on available audio
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', temp_avi
        ]
        
        filter_complex = []
        mapping = []
        
        # Add video input and filter
        filter_complex.append(f'[0:v]setpts={1/speed_factor}*PTS[v]')
        mapping.extend(['-map', '[v]'])
        
        # Add audio inputs if available
        audio_inputs = []
        if main_has_audio:
            ffmpeg_cmd.extend(['-i', main_video_path])
            audio_inputs.append(f'[{len(ffmpeg_cmd) // 2 - 1}:a]volume={main_volume}[main_a]')
        
        if overlay_has_audio:
            ffmpeg_cmd.extend(['-stream_loop', '-1', '-i', overlay_video_path])
            audio_inputs.append(f'[{len(ffmpeg_cmd) // 2 - 1}:a]volume={overlay_volume}[overlay_a]')
        
        # Add audio mixing if needed
        if len(audio_inputs) > 0:
            filter_complex.extend(audio_inputs)
            
            if len(audio_inputs) > 1:
                filter_complex.append('[main_a][overlay_a]amix=inputs=2:duration=longest[mixed_a]')
                mapping.extend(['-map', '[mixed_a]'])
            else:
                # Only one audio stream
                mapping.extend(['-map', '[main_a]' if main_has_audio else '[overlay_a]'])
        
        # Complete FFmpeg command
        if filter_complex:
            ffmpeg_cmd.extend(['-filter_complex', ';'.join(filter_complex)])
        
        ffmpeg_cmd.extend(mapping)
        ffmpeg_cmd.extend([
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-r', str(original_fps)
        ])
        
        if main_duration > 0:
            ffmpeg_cmd.extend(['-t', str(main_duration)])
            
        ffmpeg_cmd.extend(['-y', temp_mp4])
        
        # Run FFmpeg to create the MP4 file
        logger.info(f"Executing FFmpeg command: {' '.join(ffmpeg_cmd)}")
        try:
            process = subprocess.run(ffmpeg_cmd, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            logger.info(f"FFmpeg stderr: {process.stderr.decode()}")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
            raise RuntimeError(f"FFmpeg processing failed: {e.stderr.decode() if e.stderr else str(e)}")
        
        if not os.path.exists(temp_mp4) or os.path.getsize(temp_mp4) == 0:
            raise RuntimeError("FFmpeg failed to create output file")

        drive_result = None
        if stream_to_drive or folder_id:
            # Upload the temporary MP4 to Google Drive
            output_filename = os.path.basename(clean_filename(output_path) or "processed_video.mp4")
            
            try:
                with open(temp_mp4, 'rb') as file_data:
                    file_buffer = io.BytesIO(file_data.read())
                    
                if stream_to_drive:
                    drive_result = upload_to_gdrive_stream(file_buffer, output_filename, folder_id)
                else:
                    drive_result = upload_to_drive(temp_mp4, folder_id)
                    
                logger.info(f"Successfully uploaded to Google Drive: {drive_result}")
                return drive_result
            except Exception as e:
                logger.error(f"Failed to upload to Google Drive: {str(e)}")
                if not os.path.exists(OUTPUT_FOLDER):
                    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
                # If upload fails, save locally as a fallback
                final_output = os.path.join(OUTPUT_FOLDER, output_filename)
                shutil.copy2(temp_mp4, final_output)
                logger.info(f"Saved to local file as fallback: {final_output}")
                return final_output
        else:
            # Move temporary MP4 to final location
            if not os.path.exists(OUTPUT_FOLDER):
                os.makedirs(OUTPUT_FOLDER, exist_ok=True)
                
            final_output = os.path.join(OUTPUT_FOLDER, os.path.basename(clean_filename(output_path) or "processed_video.mp4"))
            shutil.copy2(temp_mp4, final_output)
            logger.info(f"Saved to local file: {final_output}")
            return final_output

    except Exception as e:
        logger.error(f"Error in video processing: {str(e)}")
        raise
    finally:
        # Clean up temporary files
        for temp_file in [temp_avi, temp_mp4]:
            try:
                if temp_file and os.path.exists(temp_file):
                    os.remove(temp_file)
                    logger.info(f"Removed temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {temp_file}: {str(e)}")

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
    file_path = os.path.join(OUTPUT_FOLDER, clean_filename(filename))
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type="video/mp4")
    raise HTTPException(status_code=404, detail="File not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
