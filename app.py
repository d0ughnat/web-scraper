import cv2
import numpy as np
import os
import subprocess
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from typing import Optional
import shutil
import tempfile

# Initialize FastAPI app
app = FastAPI(title="Video Overlay API", description="Overlay one video on another with audio mixing")

def process_video_overlay(main_video_path: str, overlay_video_path: str, output_path: str, 
                         position: str = 'top_right', scale: float = 0.3, 
                         main_volume: float = 1.0, overlay_volume: float = 1.0, 
                         speed_factor: float = 1.0):
    """
    Overlay a smaller video on top of a main video at a specified position using OpenCV and FFmpeg,
    preserving and mixing audio from both videos with adjustable volume levels and playback speed.
    
    Parameters:
    -----------
    main_video_path : str
        Path to the main/background video file
    overlay_video_path : str
        Path to the video to be overlaid
    output_path : str
        Path where the output video will be saved (will be .mp4)
    position : str
        Position for overlay: 'top_left', 'top_right', 'bottom_left', 'bottom_right'
    scale : float
        Scale factor for the overlay video (0.0-1.0)
    main_volume : float
        Volume level for main video audio (default 1.0 = original volume)
    overlay_volume : float
        Volume level for overlay video audio (default 1.0 = original volume)
    speed_factor : float
        Playback speed factor (e.g., 0.5 for half speed, 1.0 for normal, 2.0 for double speed)
    """
    # Validate file paths
    if not os.path.exists(main_video_path):
        raise FileNotFoundError(f"Main video file not found: {main_video_path}")
    
    if not os.path.exists(overlay_video_path):
        raise FileNotFoundError(f"Overlay video file not found: {overlay_video_path}")
    
    # Ensure output is .mp4
    if not output_path.endswith('.mp4'):
        output_path = os.path.splitext(output_path)[0] + '.mp4'
    
    # Check if output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Create temporary file for video processing without audio
    temp_output = os.path.splitext(output_path)[0] + '_temp.avi'
    
    # Open the main video and overlay video
    main_cap = cv2.VideoCapture(main_video_path)
    overlay_cap = cv2.VideoCapture(overlay_video_path)
    
    if not main_cap.isOpened():
        raise IOError(f"Failed to open main video: {main_video_path}")
    
    if not overlay_cap.isOpened():
        raise IOError(f"Failed to open overlay video: {overlay_video_path}")
    
    # Get main video properties
    main_width = int(main_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    main_height = int(main_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    original_fps = main_cap.get(cv2.CAP_PROP_FPS)
    main_frame_count = int(main_cap.get(cv2.CAP_PROP_FRAME_COUNT))
    main_duration = main_frame_count / original_fps if original_fps > 0 else 0
    
    if main_width == 0 or main_height == 0:
        raise ValueError("Invalid main video dimensions")
    
    # Adjust FPS based on speed factor
    adjusted_fps = original_fps * speed_factor
    if adjusted_fps <= 0:
        raise ValueError("Speed factor must be positive")
    
    print(f"Main video: {main_width}x{main_height} at original {original_fps} fps, adjusted to {adjusted_fps} fps (speed factor: {speed_factor}), duration: {main_duration:.2f} seconds")
    
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(temp_output, fourcc, adjusted_fps, (main_width, main_height))
    
    if not out.isOpened():
        raise IOError(f"Failed to create temporary video file: {temp_output}")
    
    frame_count = 0
    try:
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
                if overlay_frame is None:
                    raise ValueError("Failed to read overlay video frame after reset")
            
            # Calculate new dimensions for overlay
            overlay_height, overlay_width = overlay_frame.shape[:2]
            new_height = int(overlay_height * scale)
            new_width = int(overlay_width * scale)
            overlay_resized = cv2.resize(overlay_frame, (new_width, new_height))
            
            h, w = overlay_resized.shape[:2]
            
            # Determine position coordinates
            if position == 'top_left':
                x, y = 10, 10
            elif position == 'top_right':
                x, y = main_width - w - 10, 10
            elif position == 'bottom_left':
                x, y = 10, main_height - h - 10
            elif position == 'bottom_right':
                x, y = main_width - w - 10, main_height - h - 10
            else:
                x, y = 10, 10
            
            if x < 0: x = 0
            if y < 0: y = 0
            if x + w > main_width: w = main_width - x
            if y + h > main_height: h = main_height - y
            
            main_frame_copy = main_frame.copy()
            main_frame_copy[y:y+h, x:x+w] = overlay_resized[:h, :w]
            out.write(main_frame_copy)
            
        print(f"Processing complete! Processed {frame_count} frames total.")
        
        print("Mixing audio from both videos and converting to MP4 using FFmpeg...")
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', temp_output,
            '-i', main_video_path,
            '-stream_loop', '-1',
            '-i', overlay_video_path,
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-filter_complex',
        ]
        
        if speed_factor != 1.0:
            ffmpeg_cmd.append(
                f'[0:v]setpts={1/speed_factor}*PTS[v];'
                f'[1:a]volume={main_volume}[main_a];'
                f'[2:a]volume={overlay_volume}[overlay_a];'
                '[main_a][overlay_a]amix=inputs=2:duration=longest[mixed_a]'
            )
            ffmpeg_cmd.extend(['-map', '[v]', '-map', '[mixed_a]'])
        else:
            ffmpeg_cmd.append(
                f'[1:a]volume={main_volume}[main_a];'
                f'[2:a]volume={overlay_volume}[overlay_a];'
                '[main_a][overlay_a]amix=inputs=2:duration=longest[mixed_a]'
            )
            ffmpeg_cmd.extend(['-map', '0:v:0', '-map', '[mixed_a]'])
        
        ffmpeg_cmd.extend([
            '-r', str(original_fps),
            '-t', str(main_duration),
            '-y',
            output_path
        ])
        
        try:
            result = subprocess.run(ffmpeg_cmd, check=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            print(f"FFmpeg output: {result.stdout.decode()}")
            if result.stderr:
                print(f"FFmpeg warnings/errors: {result.stderr.decode()}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg failed: {e.stderr.decode()}")
        
    except Exception as e:
        print(f"Error during processing: {str(e)}")
        raise
    finally:
        main_cap.release()
        overlay_cap.release()
        out.release()
        cv2.destroyAllWindows()
        if os.path.exists(temp_output):
            os.remove(temp_output)
        if frame_count > 0 and os.path.exists(output_path):
            print(f"Video with mixed audio saved at {output_path}")
        else:
            print("No frames were processed or output file was not created.")

# FastAPI endpoint to process videos
@app.post("/overlay-video/", response_class=FileResponse)
async def overlay_video(
    main_video: UploadFile = File(...),
    overlay_video: UploadFile = File(...),
    position: Optional[str] = 'top_right',
    scale: Optional[float] = 0.3,
    main_volume: Optional[float] = 1.0,
    overlay_volume: Optional[float] = 1.0,
    speed_factor: Optional[float] = 1.0
):
    """
    Endpoint to overlay one video on another with audio mixing.

    Parameters:
    -----------
    main_video : UploadFile
        The main/background video file
    overlay_video : UploadFile
        The video to overlay on the main video
    position : str
        Position for overlay: 'top_left', 'top_right', 'bottom_left', 'bottom_right'
    scale : float
        Scale factor for the overlay video (0.0-1.0)
    main_volume : float
        Volume level for main video audio (default 1.0 = original volume)
    overlay_volume : float
        Volume level for overlay video audio (default 1.0 = original volume)
    speed_factor : float
        Playback speed factor (e.g., 0.5 for half speed, 1.0 for normal, 2.0 for double speed)

    Returns:
    --------
    FileResponse: The processed video file
    """
    # Validate inputs
    allowed_positions = ['top_left', 'top_right', 'bottom_left', 'bottom_right']
    if position not in allowed_positions:
        raise HTTPException(status_code=400, detail=f"Position must be one of {allowed_positions}")
    if scale <= 0 or scale > 1:
        raise HTTPException(status_code=400, detail="Scale must be between 0.0 and 1.0")
    if main_volume < 0 or overlay_volume < 0:
        raise HTTPException(status_code=400, detail="Volume levels must be non-negative")
    if speed_factor <= 0:
        raise HTTPException(status_code=400, detail="Speed factor must be positive")

    # Create temporary directories and files
    with tempfile.TemporaryDirectory() as tmp_dir:
        main_path = os.path.join(tmp_dir, "main_video.mp4")
        overlay_path = os.path.join(tmp_dir, "overlay_video.mp4")
        output_path = os.path.join(tmp_dir, "output_video.mp4")

        # Save uploaded files
        try:
            with open(main_path, "wb") as main_file:
                shutil.copyfileobj(main_video.file, main_file)
            with open(overlay_path, "wb") as overlay_file:
                shutil.copyfileobj(overlay_video.file, overlay_file)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded files: {str(e)}")

        # Process the video
        try:
            process_video_overlay(
                main_path, overlay_path, output_path,
                position=position, scale=scale,
                main_volume=main_volume, overlay_volume=overlay_volume,
                speed_factor=speed_factor
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Video processing failed: {str(e)}")

        # Check if output exists
        if not os.path.exists(output_path):
            raise HTTPException(status_code=500, detail="Output video was not created")

        # Return the processed file
        return FileResponse(output_path, filename="output_video.mp4", media_type="video/mp4")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
