import React, { useState } from 'react';
import axios from 'axios';
import './over.css';

function Over() {
  const [mainVideo, setMainVideo] = useState(null);
  const [overlayVideo, setOverlayVideo] = useState(null);
  const [position, setPosition] = useState('top_right');
  const [scale, setScale] = useState(0.3);
  const [mainVolume, setMainVolume] = useState(1.0);
  const [overlayVolume, setOverlayVolume] = useState(1.0);
  const [speedFactor, setSpeedFactor] = useState(1.0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [downloadUrl, setDownloadUrl] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!mainVideo || !overlayVideo) {
      setError('Please upload both main and overlay videos.');
      return;
    }

    setLoading(true);
    setError(null);
    setDownloadUrl(null);

    const formData = new FormData();
    formData.append('main_video', mainVideo);
    formData.append('overlay_video', overlayVideo);
    formData.append('position', position);
    formData.append('scale', scale);
    formData.append('main_volume', mainVolume);
    formData.append('overlay_volume', overlayVolume);
    formData.append('speed_factor', speedFactor);

    try {
      const response = await axios.post('http://localhost:8000/overlay-video/', formData, {
        responseType: 'blob', // Important for handling binary data (video file)
      });

      // Create a URL for the downloaded file
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'video/mp4' }));
      setDownloadUrl(url);
    } catch (err) {
      setError(err.response?.data?.detail || 'An error occurred while processing the video.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="App">
      <h1>Video Overlay Tool</h1>
      <form onSubmit={handleSubmit}>
        <div>
          <label>Main Video:</label>
          <input
            type="file"
            accept="video/*"
            onChange={(e) => setMainVideo(e.target.files[0])}
            disabled={loading}
          />
        </div>
        <div>
          <label>Overlay Video:</label>
          <input
            type="file"
            accept="video/*"
            onChange={(e) => setOverlayVideo(e.target.files[0])}
            disabled={loading}
          />
        </div>
        <div>
          <label>Position:</label>
          <select value={position} onChange={(e) => setPosition(e.target.value)} disabled={loading}>
            <option value="top_left">Top Left</option>
            <option value="top_right">Top Right</option>
            <option value="bottom_left">Bottom Left</option>
            <option value="bottom_right">Bottom Right</option>
          </select>
        </div>
        <div>
          <label>Scale (0.0-1.0):</label>
          <input
            type="number"
            step="0.1"
            min="0"
            max="1"
            value={scale}
            onChange={(e) => setScale(parseFloat(e.target.value))}
            disabled={loading}
          />
        </div>
        <div>
          <label>Main Volume:</label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={mainVolume}
            onChange={(e) => setMainVolume(parseFloat(e.target.value))}
            disabled={loading}
          />
        </div>
        <div>
          <label>Overlay Volume:</label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={overlayVolume}
            onChange={(e) => setOverlayVolume(parseFloat(e.target.value))}
            disabled={loading}
          />
        </div>
        <div>
          <label>Speed Factor:</label>
          <input
            type="number"
            step="0.1"
            min="0.1"
            value={speedFactor}
            onChange={(e) => setSpeedFactor(parseFloat(e.target.value))}
            disabled={loading}
          />
        </div>
        <button type="submit" disabled={loading}>
          {loading ? 'Processing...' : 'Process Video'}
        </button>
      </form>

      {error && <p style={{ color: 'red' }}>{error}</p>}
      {downloadUrl && (
        <div>
          <p>Processing complete! Download your video:</p>
          <a href={downloadUrl} download="output_video.mp4">
            <button>Download Video</button>
          </a>
        </div>
      )}
    </div>
  );
}

export default Over;
