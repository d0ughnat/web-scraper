import React, { useState } from 'react';
import axios from 'axios';

const VideoOverlayForm = () => {
  // State for form inputs
  const [mainVideo, setMainVideo] = useState(null);
  const [overlayVideo, setOverlayVideo] = useState(null);
  const [mainDriveId, setMainDriveId] = useState('');
  const [overlayDriveId, setOverlayDriveId] = useState('');
  const [position, setPosition] = useState('top_right');
  const [scale, setScale] = useState(0.3);
  const [mainVolume, setMainVolume] = useState(1.0);
  const [overlayVolume, setOverlayVolume] = useState(1.0);
  const [speedFactor, setSpeedFactor] = useState(1.0);
  const [uploadToDrive, setUploadToDrive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setResult(null);

    // Prepare form data
    const formData = new FormData();
    if (mainVideo) {
      formData.append('main_video', mainVideo);
    } else if (mainDriveId) {
      formData.append('main_video_drive_id', mainDriveId);
    }
    if (overlayVideo) {
      formData.append('overlay_video', overlayVideo);
    } else if (overlayDriveId) {
      formData.append('overlay_video_drive_id', overlayDriveId);
    }
    formData.append('params', JSON.stringify({
      position,
      scale,
      main_volume: mainVolume,
      overlay_volume: overlayVolume,
      speed_factor: speedFactor,
    }));
    formData.append('upload_to_drive', uploadToDrive);

    try {
      const response = await axios.post('http://localhost:8000/overlay-video/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        responseType: uploadToDrive ? 'json' : 'blob',
      });

      if (uploadToDrive) {
        setResult({ driveFileId: response.data.drive_file_id });
      } else {
        // Trigger file download
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', 'processed_video.mp4');
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
    } catch (error) {
      console.error('Error processing video:', error);
      setResult({ error: 'Failed to process video' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px' }}>
      <h1>Video Overlay</h1>
      <form onSubmit={handleSubmit}>
        <div>
          <label>Main Video Upload:</label><br />
          <input type="file" onChange={(e) => setMainVideo(e.target.files[0])} />
        </div>
        <div>
          <label>Or Main Video Drive ID:</label><br />
          <input type="text" value={mainDriveId} onChange={(e) => setMainDriveId(e.target.value)} />
        </div>
        <div>
          <label>Overlay Video Upload:</label><br />
          <input type="file" onChange={(e) => setOverlayVideo(e.target.files[0])} />
        </div>
        <div>
          <label>Or Overlay Video Drive ID:</label><br />
          <input type="text" value={overlayDriveId} onChange={(e) => setOverlayDriveId(e.target.value)} />
        </div>
        <div>
          <label>Position:</label><br />
          <select value={position} onChange={(e) => setPosition(e.target.value)}>
            <option value="top_left">Top Left</option>
            <option value="top_right">Top Right</option>
            <option value="bottom_left">Bottom Left</option>
            <option value="bottom_right">Bottom Right</option>
          </select>
        </div>
        <div>
          <label>Scale (0-1):</label><br />
          <input
            type="number"
            step="0.1"
            min="0"
            max="1"
            value={scale}
            onChange={(e) => setScale(e.target.value)}
          />
        </div>
        <div>
          <label>Main Volume (0-2):</label><br />
          <input
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={mainVolume}
            onChange={(e) => setMainVolume(e.target.value)}
          />
        </div>
        <div>
          <label>Overlay Volume (0-2):</label><br />
          <input
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={overlayVolume}
            onChange={(e) => setOverlayVolume(e.target.value)}
          />
        </div>
        <div>
          <label>Speed Factor (0.25-4):</label><br />
          <input
            type="number"
            step="0.25"
            min="0.25"
            max="4"
            value={speedFactor}
            onChange={(e) => setSpeedFactor(e.target.value)}
          />
        </div>
        <div>
          <label>Upload to Drive:</label>
          <input
            type="checkbox"
            checked={uploadToDrive}
            onChange={(e) => setUploadToDrive(e.target.checked)}
          />
        </div>
        <button type="submit" disabled={loading} style={{ marginTop: '10px' }}>
          {loading ? 'Processing...' : 'Process Video'}
        </button>
      </form>
      {result && (
        <div style={{ marginTop: '20px' }}>
          {result.driveFileId ? (
            <p>Processed video uploaded to Drive with ID: {result.driveFileId}</p>
          ) : result.error ? (
            <p>Error: {result.error}</p>
          ) : null}
        </div>
      )}
    </div>
  );
};

export default VideoOverlayForm;
