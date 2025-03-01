from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import subprocess
import tempfile
import shutil
import logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Google Drive API setup
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service_account.json")
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

@app.post("/convert-to-mp4")
async def convert_to_mp4(
    file: UploadFile = File(...),
    folder_id: str = Form(default='')  # Optional folder ID from the form data
):
    logger.info(f"Received file: {file.filename}, size: {file.size}, folder_id: {folder_id}")

    if not shutil.which("ffmpeg"):
        logger.error("FFmpeg is not installed on the server")
        raise HTTPException(status_code=500, detail="FFmpeg is not installed on the server")

    # Check for libx264 support
    try:
        result = subprocess.run(["ffmpeg", "-codecs"], capture_output=True, text=True, check=True)
        if "libx264" not in result.stdout:
            logger.error("FFmpeg is not compiled with libx264 support")
            raise HTTPException(status_code=500, detail="FFmpeg is not compiled with libx264 support")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to check FFmpeg codecs: {e.stderr}")
        raise HTTPException(status_code=500, detail="Failed to verify FFmpeg installation")

    temp_input = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    temp_output = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    
    try:
        # Write uploaded WebM content to temp file
        logger.debug(f"Writing uploaded file to {temp_input.name}")
        temp_input.write(await file.read())
        temp_input.close()

        # Convert WebM to MP4 with FFmpeg
        logger.debug(f"Running FFmpeg: {temp_input.name} -> {temp_output.name}")
        result = subprocess.run(
            [
                "ffmpeg",
                "-i", temp_input.name,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-y",
                temp_output.name
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        logger.debug(f"FFmpeg output: {result.stdout.decode()}")
        if result.stderr:
            logger.warning(f"FFmpeg warnings/errors: {result.stderr.decode()}")

        # Upload to Google Drive
        logger.debug("Uploading MP4 to Google Drive")
        file_metadata = {'name': file.filename.replace('.webm', '.mp4')}
        if folder_id:  # Only add parents if folder_id is provided
            file_metadata['parents'] = [folder_id]
        media = MediaFileUpload(temp_output.name, mimetype='video/mp4')
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        file_id = uploaded_file.get('id')

        # Set permissions to "anyone with the link" can download
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        drive_service.permissions().create(
            fileId=file_id,
            body=permission
        ).execute()

        # Generate direct download link
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        view_url = f"https://drive.google.com/file/d/{file_id}/view"
        logger.info(f"Uploaded to Google Drive{' folder ' + folder_id if folder_id else ''} with file ID: {file_id}, download URL: {download_url}")

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg conversion failed: {e.stderr.decode()}")
        raise HTTPException(status_code=500, detail=f"FFmpeg conversion failed: {e.stderr.decode()}")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")
    finally:
        if os.path.exists(temp_input.name):
            os.unlink(temp_input.name)
        if os.path.exists(temp_output.name):
            os.unlink(temp_output.name)

    logger.info("Conversion and upload successful, returning download URL only")
    return JSONResponse(content={
        "download_url": download_url,
        "view_url": view_url,
        "file_id": file_id,
        "message": "File successfully converted and uploaded to Google Drive"
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
