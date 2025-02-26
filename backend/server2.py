import uvicorn
from video_app import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,  # Video app runs on port 8001
        reload=True
    )
