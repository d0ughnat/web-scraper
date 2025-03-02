import cv2
import numpy as np
import os
import subprocess
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
import shutil
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any, Union
from urllib.parse import urlparse, parse_qs
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload
import io
import tempfile
import logging
import re
import requests
from contextlib import contextmanager

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = FastAPI(title="Video Overlay API", 
              description="API for processing videos with overlays and Google Drive integration")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
CREDENTIALS_FOLDER = "credentials"
ALLOWED_EXTENSIONS = {"mp4", "avi", "mov", "webm", "mkv"}
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service_account.json")
SCOPES = ['https://www.googleapis.com/auth/drive']

# Create necessary folders
for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, CREDENTIALS_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# Temp file manager
@contextmanager
def temporary_file(suffix=None):
    """Context manager for temporary files that ensures cleanup."""
    temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        yield temp_file.name
    finally:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)

# Utility functions
def allowed_file(filename: str) -> bool:
    """Check if file has an allowed extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_filename(filename: str) -> str:
    """Remove URL query parameters and sanitize filename"""
    if not filename:
        return "unnamed_file.mp4"
    # Remove URL parameters
    cleaned = re.sub(r'\?.*$', '', filename)
    # Replace unsafe characters
    cleaned = re.sub(r'[^\w\-\.]', '_', cleaned)
    return cleaned

def extract_folder_id(folder_input: str) -> str:
    """Extract folder ID from either a full Google Drive URL or a plain ID"""
    if not folder_input:
        return None
    if folder_input.startswith('http'):
        # Try to extract from folders URL format
        match = re.search(r'folders/([a-zA-Z0-9_-]+)', folder_input)
        if match:
            return match.group(1)
        # Try to extract from query parameters
        parsed = urlparse(folder_input)
        if parsed.query:
            params = parse_qs(parsed.query)
            if 'id' in params:
                return params['id'][0]
        raise ValueError("Invalid Google Drive folder URL")
    return folder_input

def get_drive_service():
    """Create a Google Drive service instance using the service account"""
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        logger.error(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")
        raise FileNotFoundError(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"Failed to create Drive service: {str(e)}")
        raise

def download_from_gdrive(gdrive_url: str, output_path: str) -> str:
    """Download a file from Google Drive using the URL"""
    try:
        logger.info(f"Downloading from Google Drive: {gdrive_url}")
        parsed_url = urlparse(gdrive_url)
        file_id = None
        
        # Extract file ID from different Google Drive URL formats
        if 'drive.google.com/file/d/' in gdrive_url:
            file_id = gdrive_url.split('/file/d/')[1].split('/')[0]
        elif 'drive.google.com/open?id=' in gdrive_url:
            file_id = parse_qs(parsed_url.query)['id'][0]
        elif 'docs.google.com' in gdrive_url and 'export=download' in gdrive_url:
            file_id = parse_qs(parsed_url.query)['id'][0]
        elif 'drive.google.com/uc?id=' in gdrive_url:
            file_id = parse_qs(parsed_url.query)['id'][0]
        else:
            raise ValueError("Invalid Google Drive URL format")
            
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        
        # Handle large files with confirmation token
        session = requests.Session()
        response = session.get(download_url, stream=True)
        
        # Check for download warning/confirmation token
        for key, value in response.cookies.items():
            if key.startswith('download_warning'):
                download_url = f"{download_url}&confirm={value}"
                response = session.get(download_url, stream=True)
                break
        
        # Save the file
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                if chunk:
                    f.write(chunk)
        
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise ValueError("Downloaded file is empty or does not exist")
            
        logger.info(f"Successfully downloaded to: {output_path}")
        return output_path
    
    except Exception as e:
        logger.error(f"Download failed: {str(e)}")
        raise ValueError(f"Failed to download from Google Drive: {str(e)}")

def upload_to_drive(file_path: str, folder_id: str = None) -> str:
    """Upload file to Google Drive and set public permissions"""
    try:
        logger.info(f"Uploading {file_path} to Google Drive")
        folder_id = extract_folder_id(folder_id) if folder_id else None
        
        # Validate file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File to upload not found: {file_path}")
            
        service = get_drive_service()
        
        file_metadata = {'name': os.path.basename(file_path)}
        if folder_id:
            file_metadata['parents'] = [folder_id]
            
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(body=file_metadata, 
                                     media_body=media, 
                                     fields='id,webViewLink').execute()
                                     
        # Make file publicly accessible
        service.permissions().create(
            fileId=file.get('id'), 
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        logger.info(f"Upload successful. File ID: {file.get('id')}")
        return file.get('webViewLink')
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise Exception(f"Failed to upload to Google Drive: {str(e)}")

def upload_to_gdrive_stream(file_stream: io.BytesIO, filename: str, folder_id: str = None) -> Dict[str, str]:
    """Upload a file stream directly to Google Drive using service account"""
    try:
        logger.info(f"Streaming upload to Google Drive: {filename}")
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
        
        # Make file publicly accessible
        permission = {'type': 'anyone', 'role': 'reader'}
        service.permissions().create(fileId=file.get('id'), body=permission).execute()
        
        result = {
            'id': file.get('id'),
            'name': file.get('name'),
            'webViewLink': file.get('webViewLink'),
            'downloadLink': f"https://drive.google.com/uc?export=download&id={file.get('id')}"
        }
        logger.info(f"Stream upload successful. File ID: {file.get('id')}")
        return result
    except Exception as e:
        logger.error(f"Stream upload error: {str(e)}")
        raise Exception(f"Failed to upload to Google Drive: {str(e)}")

async def process_video_overlay(
    main_video_path: str, 
    overlay_video_path: str, 
    output_path: str = None, 
    position: str = "bottom_right", 
    scale: float = 0.3,
    main_volume: float = 1.0, 
    overlay_volume: float = 1.0, 
    speed_factor: float = 1.0, 
    x: int = None, 
    y: int = None,
    opacity: float = 1.0, 
    custom_layout: bool = False,
    stream_to_drive: bool = False, 
    folder_id: str = None) -> Union[str, Dict[str, Any]]:
    """
    Process a video by adding an overlay video with various customization options.
    Returns file path or Google Drive upload result.
    """
    # Validate inputs
    if not os.path.exists(main_video_path):
        raise FileNotFoundError(f"Main video file not found: {main_video_path}")
    if not os.path.exists(overlay_video_path):
        raise FileNotFoundError(f"Overlay video file not found: {overlay_video_path}")

    # Open video files
    main_cap = cv2.VideoCapture(main_video_path)
    overlay_cap = cv2.VideoCapture(overlay_video_path)

    if not main_cap.isOpened() or not overlay_cap.isOpened():
        main_cap.release()
        overlay_cap.release()
        raise IOError("Failed to open video files")

    # Get video properties
    main_width = int(main_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    main_height = int(main_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    original_fps = main_cap.get(cv2.CAP_PROP_FPS)
    main_frame_count = int(main_cap.get(cv2.CAP_PROP_FRAME_COUNT))
    main_duration = main_frame_count / original_fps if original_fps > 0 else 0

    if main_width <= 0 or main_height <= 0:
        main_cap.release()
        overlay_cap.release()
        raise ValueError("Invalid main video dimensions")

    # Validate scale and speed_factor
    scale = max(0.01, min(scale, 1.0))  # Keep scale between 0.01 and 1.0
    speed_factor = max(0.25, min(speed_factor, 4.0))  # Keep speed between 0.25x and 4.0x

    # Create intermediate video
    adjusted_fps = original_fps * speed_factor
    fourcc = cv2.VideoWriter_fourcc(*'XVID')

    with temporary_file(suffix='.avi') as temp_output:
        out = cv2.VideoWriter(temp_output, fourcc, adjusted_fps, (main_width, main_height))
        if not out.isOpened():
            main_cap.release()
            overlay_cap.release()
            raise IOError("Failed to create video writer")

        # Validate position
        valid_positions = {'top_left', 'top_right', 'bottom_left', 'bottom_right', 'center', 'custom'}
        if position not in valid_positions and not custom_layout:
            position = "bottom_right"  # Default to bottom right if invalid

        try:
            frame_count = 0
            while True:
                main_ret, main_frame = main_cap.read()
                if not main_ret:
                    break

                overlay_ret, overlay_frame = overlay_cap.read()
                if not overlay_ret:
                    # Loop overlay video
                    overlay_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    overlay_ret, overlay_frame = overlay_cap.read()
                    if not overlay_ret:  # If still can't read, break
                        logger.error("Failed to read overlay frame even after reset")
                        break

                frame_count += 1
                if frame_count % 100 == 0:
                    logger.info(f"Processed {frame_count} frames")

                # Resize overlay
                overlay_height, overlay_width = overlay_frame.shape[:2]
                new_height = int(overlay_height * scale)
                new_width = int(overlay_width * scale)
                
                if new_height <= 0 or new_width <= 0:
                    logger.warning(f"Invalid overlay dimensions at frame {frame_count}, skipping")
                    continue
                    
                overlay_resized = cv2.resize(overlay_frame, (new_width, new_height))
                h, w = overlay_resized.shape[:2]

                # Determine position
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

                # Ensure position is within frame bounds
                x_pos = max(0, min(x_pos, main_width - w))
                y_pos = max(0, min(y_pos, main_height - h))

                # Check if the overlay fits within the main frame
                if y_pos + h > main_height or x_pos + w > main_width:
                    logger.warning(f"Overlay dimensions exceed main frame at frame {frame_count}, adjusting")
                    x_pos = min(x_pos, main_width - w)
                    y_pos = min(y_pos, main_height - h)

                # Apply overlay with opacity
                try:
                    roi = main_frame[y_pos:y_pos+h, x_pos:x_pos+w]
                    if roi.shape[0] != h or roi.shape[1] != w:
                        logger.warning(f"ROI shape mismatch at frame {frame_count}, skipping overlay")
                        out.write(main_frame)
                        continue
                        
                    if opacity < 1.0:
                        # Use alpha blending for transparency
                        overlay_gray = cv2.cvtColor(overlay_resized, cv2.COLOR_BGR2GRAY)
                        _, mask = cv2.threshold(overlay_gray, 10, 255, cv2.THRESH_BINARY)
                        mask_inv = cv2.bitwise_not(mask)
                        
                        # Apply mask to preserve background where overlay is black
                        background = cv2.bitwise_and(roi, roi, mask=mask_inv)
                        foreground = cv2.addWeighted(overlay_resized, opacity, np.zeros_like(overlay_resized), 0, 0)
                        foreground = cv2.bitwise_and(foreground, foreground, mask=mask)
                        
                        # Combine background and foreground
                        main_frame[y_pos:y_pos+h, x_pos:x_pos+w] = cv2.add(background, foreground)
                    else:
                        # Direct overlay
                        main_frame[y_pos:y_pos+h, x_pos:x_pos+w] = overlay_resized
                except ValueError as e:
                    logger.warning(f"Error applying overlay at frame {frame_count}: {str(e)}")

                # Write the frame
                out.write(main_frame)

            logger.info(f"Processed {frame_count} frames total.")

            if frame_count == 0:
                raise RuntimeError("No frames processed.")

            # Close resources
            main_cap.release()
            overlay_cap.release()
            out.release()
            cv2.destroyAllWindows()

            # Check if temp output was created and has content
            if not os.path.exists(temp_output) or os.path.getsize(temp_output) == 0:
                raise RuntimeError("Failed to create intermediate video file")

            # Build FFmpeg command for final processing (adds audio)
            base_ffmpeg_cmd = [
                'ffmpeg',
                '-i', temp_output,
                '-i', main_video_path,
                '-stream_loop', '-1',
                '-i', overlay_video_path,
                '-c:v', 'libx264',
                '-preset', 'medium',  # Better balance of speed and quality
                '-crf', '23',  # Good quality
                '-c:a', 'aac',
                '-filter_complex',
                f'[0:v]setpts={1/speed_factor}*PTS[v];'
                f'[1:a]volume={main_volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[main_a];'
                f'[2:a]volume={overlay_volume},aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[overlay_a];'
                '[main_a][overlay_a]amix=inputs=2:duration=longest[mixed_a]',
                '-map', '[v]',
                '-map', '[mixed_a]',
                '-r', str(original_fps),
                '-t', str(main_duration),
                '-y'
            ]

            drive_result = None
            output_file = None
            
            if stream_to_drive:
                # Stream output directly to Google Drive
                ffmpeg_cmd = base_ffmpeg_cmd.copy()
                ffmpeg_cmd.extend(['-f', 'mp4', 'pipe:'])
                logger.info(f"Executing FFmpeg streaming command")
                
                with io.BytesIO() as output_buffer:
                    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate()
                    
                    if process.returncode != 0:
                        stderr_text = stderr.decode()
                        logger.error(f"FFmpeg failed: {stderr_text}")
                        raise RuntimeError(f"FFmpeg failed: {stderr_text}")
                    
                    output_buffer.write(stdout)
                    output_buffer.seek(0)
                    logger.debug(f"FFmpeg stderr: {stderr.decode()}")
                    
                    # Upload to Drive
                    output_filename = os.path.basename(clean_filename(output_path) or f"processed_video_{int(time.time())}.mp4")
                    drive_result = upload_to_gdrive_stream(output_buffer, output_filename, folder_id)
                    
                return drive_result
            else:
                # Create file output
                output_file = clean_filename(output_path) if output_path else os.path.join(
                    OUTPUT_FOLDER, f"processed_{int(time.time())}.mp4")
                
                ffmpeg_cmd = base_ffmpeg_cmd.copy()
                ffmpeg_cmd.append(output_file)
                logger.info(f"Executing FFmpeg file command")
                
                process = subprocess.run(ffmpeg_cmd, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
                logger.debug(f"FFmpeg stderr: {process.stderr.decode()}")
                
                if not os.path.exists(output_file):
                    raise RuntimeError("Output file not created")
                
                if os.path.getsize(output_file) == 0:
                    raise RuntimeError("Output file is empty")
                
                return output_file
                
        except Exception as e:
            logger.error(f"Error in video processing: {str(e)}")
            main_cap.release()
            overlay_cap.release()
            if 'out' in locals() and out.isOpened():
                out.release()
            cv2.destroyAllWindows()
            raise

@app.post("/process-video/", response_model=Dict[str, Any])
async def process_video_endpoint(
    background_tasks: BackgroundTasks,
    main_video: Optional[UploadFile] = File(None),
    overlay_video: Optional[UploadFile] = File(None),
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
    """
    Process a video with overlay.
    
    - At least one of main_video or main_video_url must be provided
    - At least one of overlay_video or overlay_video_url must be provided
    """
    # Track temporary files for cleanup
    temp_files = []
    
    try:
        # Process main video input
        main_path = None
        if main_video:
            if not allowed_file(main_video.filename):
                raise HTTPException(status_code=400, detail="Invalid main video file format")
            main_path = os.path.join(UPLOAD_FOLDER, clean_filename(main_video.filename))
            with open(main_path, "wb") as main_file:
                shutil.copyfileobj(main_video.file, main_file)
            temp_files.append(main_path)
        elif main_video_url:
            main_filename = f"main_video_{clean_filename(os.path.basename(main_video_url))}"
            if '.' not in main_filename:
                main_filename += '.mp4'
            main_path = os.path.join(UPLOAD_FOLDER, main_filename)
            main_path = download_from_gdrive(main_video_url, main_path)
            temp_files.append(main_path)
        else:
            raise HTTPException(status_code=400, detail="Either main_video file or main_video_url must be provided")
        
        # Process overlay video input
        overlay_path = None
        if overlay_video:
            if not allowed_file(overlay_video.filename):
                raise HTTPException(status_code=400, detail="Invalid overlay video file format")
            overlay_path = os.path.join(UPLOAD_FOLDER, clean_filename(overlay_video.filename))
            with open(overlay_path, "wb") as overlay_file:
                shutil.copyfileobj(overlay_video.file, overlay_file)
            temp_files.append(overlay_path)
        elif overlay_video_url:
            overlay_filename = f"overlay_video_{clean_filename(os.path.basename(overlay_video_url))}"
            if '.' not in overlay_filename:
                overlay_filename += '.mp4'
            overlay_path = os.path.join(UPLOAD_FOLDER, overlay_filename)
            overlay_path = download_from_gdrive(overlay_video_url, overlay_path)
            temp_files.append(overlay_path)
        else:
            raise HTTPException(status_code=400, detail="Either overlay_video file or overlay_video_url must be provided")
        
        # Validate and normalize parameters
        scale = max(0.01, min(1.0, scale))
        main_volume = max(0, min(2.0, main_volume))
        overlay_volume = max(0, min(2.0, overlay_volume))
        speed_factor = max(0.25, min(4.0, speed_factor))
        opacity = max(0.1, min(1.0, opacity))
        
        # Create output path
        output_filename = f"processed_{clean_filename(os.path.basename(main_path))}"
        if not output_filename.endswith('.mp4'):
            output_filename = os.path.splitext(output_filename)[0] + '.mp4'
        output_path = os.path.join(OUTPUT_FOLDER, output_filename) if not upload_to_drive else None

        # Process the video
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

        # Schedule cleanup of temporary files
        for file_path in temp_files:
            background_tasks.add_task(lambda p: os.remove(p) if os.path.exists(p) else None, file_path)

        # Format response
        response = {}
        if upload_to_drive:
            if isinstance(result, dict):
                response["drive_upload"] = result
            else:
                response["drive_upload"] = {"webViewLink": result}
            response["success"] = True
            response["message"] = "Video processed and uploaded to Google Drive successfully"
        else:
            filename = os.path.basename(result)
            response["output_path"] = filename
            response["download_url"] = f"/download/{filename}"
            response["success"] = True
            response["message"] = "Video processed successfully"

        return JSONResponse(content=response)

    except Exception as e:
        # Clean up temporary files in case of error
        for file_path in temp_files:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        logger.error(f"Process video error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-to-drive/")
async def upload_to_drive_endpoint(
    file_name: str = Form(...),
    folder_id: Optional[str] = Form(None)
):
    """Upload a processed video to Google Drive"""
    try:
        # Sanitize and validate filename
        file_name = clean_filename(file_name)
        file_path = os.path.join(OUTPUT_FOLDER, file_name)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Upload to Drive
        result = upload_to_drive(file_path, folder_id)
        if result:
            return {"success": True, "webViewLink": result}
        raise HTTPException(status_code=500, detail="Failed to upload to Google Drive")
    except Exception as e:
        logger.error(f"Upload to Drive error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download a processed video file"""
    # Sanitize filename
    clean_name = clean_filename(filename)
    
    # Try several possible locations
    file_path = os.path.join(OUTPUT_FOLDER, clean_name)
    
    # If file doesn't exist, check with mp4 extension
    if not os.path.exists(file_path) and not clean_name.endswith('.mp4'):
        file_path = os.path.join(OUTPUT_FOLDER, f"{clean_name}.mp4")
    
    # If still not found, try finding by base name
    if not os.path.exists(file_path):
        base_name = os.path.splitext(clean_name)[0]
        potential_matches = [
            f for f in os.listdir(OUTPUT_FOLDER) 
            if f.startswith(base_name) or base_name in f
        ]
        
        if potential_matches:
            # Use the most recently modified matching file
            most_recent = max(
                potential_matches, 
                key=lambda f: os.path.getmtime(os.path.join(OUTPUT_FOLDER, f))
            )
            file_path = os.path.join(OUTPUT_FOLDER, most_recent)
    
    if os.path.exists(file_path):
        logger.info(f"Serving file: {file_path}")
        return FileResponse(
            file_path, 
            filename=os.path.basename(file_path), 
            media_type="video/mp4"
        )
    
    # Log the error
    logger.error(f"File not found: {filename}. Attempted path: {file_path}")
    logger.info(f"Available files in {OUTPUT_FOLDER}: {os.listdir(OUTPUT_FOLDER)}")
    
    raise HTTPException(
        status_code=404, 
        detail=f"File not found: {filename}. Please check if the file was processed successfully."
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}

# Add extra imports needed above
import time
