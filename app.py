import os
import subprocess
from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Literal
import shutil
import tempfile
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Video Overlay API")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def process_video_overlay(main_video_path, overlay_video_path, output_path, position='top_right',
                         scale=0.3, main_volume=1.0, overlay_volume=1.0, speed_factor=1.0):
    """Overlay a video using FFmpeg directly for simplicity and reliability."""
    logger.info(f"Processing video: main={main_video_path}, overlay={overlay_video_path}")

    # Validate file existence
    if not os.path.exists(main_video_path) or not os.path.exists(overlay_video_path):
        raise FileNotFoundError(f"Input video files not found: {main_video_path}, {overlay_video_path}")

    # Get main video duration
    ffprobe_cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', main_video_path
    ]
    duration = float(subprocess.check_output(ffprobe_cmd, text=True).strip())
    logger.info(f"Main video duration: {duration}s")

    # Define overlay position
    if position == 'top_left':
        overlay_pos = '10:10'
    elif position == 'top_right':
        overlay_pos = 'main_w-overlay_w-10:10'
    elif position == 'bottom_left':
        overlay_pos = '10:main_h-overlay_h-10'
    else:  # bottom_right
        overlay_pos = 'main_w-overlay_w-10:main_h-overlay_h-10'

    # FFmpeg command for overlay and audio mixing
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', main_video_path,
        '-i', overlay_video_path,
        '-filter_complex',
        f'[1:v]scale=iw*{scale}:ih*{scale}[ov];[0:v][ov]overlay={overlay_pos}[v];'
        f'[0:a]volume={main_volume}[main_a];[1:a]volume={overlay_volume}[ov_a];'
        f'[main_a][ov_a]amix=inputs=2:duration=longest[a]',
        '-map', '[v]',
        '-map', '[a]',
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-r', '30',  # Standard frame rate, adjust if needed
        '-t', str(duration),
        '-y',  # Overwrite output
        output_path
    ]

    if speed_factor != 1.0:
        ffmpeg_cmd.insert(5, f'[0:v]setpts={1/speed_factor}*PTS[v0];[0:a]atempo={speed_factor}[a0];')
        ffmpeg_cmd[6] = f'[v0][ov]overlay={overlay_pos}[v];[a0][ov_a]amix=inputs=2:duration=longest[a]'

    logger.info(f"Executing FFmpeg command: {' '.join(ffmpeg_cmd)}") # Log the full command

    try:
        result = subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        logger.info(f"FFmpeg output: {result.stdout}")
        if result.stderr:
            logger.warning(f"FFmpeg warnings/errors: {result.stderr}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed: {e}")
        logger.error(f"FFmpeg stderr:\n{e.stderr}")  # Log the stderr for detailed diagnostics
        raise RuntimeError(f"FFmpeg processing failed: {e}") #Reduced information, the exception carries everything already

    if not os.path.exists(output_path):
        raise FileNotFoundError(f"Output file was not created: {output_path}")
    logger.info(f"Output file created: {output_path}")


@app.post("/overlay-video/")
async def overlay_video(
    main_video: UploadFile,
    overlay_video: UploadFile,
    position: Literal['top_left', 'top_right', 'bottom_left', 'bottom_right'] = 'top_right',
    scale: float = 0.3,
    main_volume: float = 1.0,
    overlay_volume: float = 1.0,
    speed_factor: float = 1.0
):
    """Handle video overlay request."""
    try:
        if not 0 < scale <= 1.0 or main_volume < 0 or overlay_volume < 0 or speed_factor <= 0:
            raise HTTPException(status_code=400, detail="Invalid parameter values")

        with tempfile.TemporaryDirectory() as temp_dir:
            main_path = os.path.join(temp_dir, "main_video.mp4")
            overlay_path = os.path.join(temp_dir, "overlay_video.mp4")
            output_path = os.path.join(temp_dir, "output_video.mp4")

            logger.info(f"Saving files: {main_path}, {overlay_path}")
            with open(main_path, "wb") as main_file:
                shutil.copyfileobj(main_video.file, main_file)
            with open(overlay_path, "wb") as overlay_file:
                shutil.copyfileobj(overlay_video.file, overlay_file)

            process_video_overlay(main_path, overlay_path, output_path, position, scale,
                                 main_volume, overlay_volume, speed_factor)

            if not os.path.exists(output_path):
                logger.error(f"Output file missing: {output_path}")
                raise HTTPException(status_code=500, detail="Failed to generate output video")

            logger.info(f"Attempting to serve file: {output_path}")  # Log right before reading file
            with open(output_path, "rb") as video_file:
                video_data = video_file.read()

            return StreamingResponse(content=iter([video_data]), media_type="video/mp4",
                                       headers={"Content-Disposition": "attachment;filename=output_video.mp4"})

    except Exception as e:
        logger.exception(f"Endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    finally:
        await main_video.close()
        await overlay_video.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
