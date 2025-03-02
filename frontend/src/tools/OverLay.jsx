import React, { useState } from 'react';
import axios from 'axios';
import { 
  Container, Typography, TextField, Button, FormControl, InputLabel, Select, MenuItem, 
  Checkbox, FormControlLabel, Box, CircularProgress, Alert 
} from '@mui/material';
import './over.css';

const API_BASE_URL = 'http://localhost:8001';

function Over() {
  const [mainVideo, setMainVideo] = useState(null);
  const [overlayVideo, setOverlayVideo] = useState(null);
  const [mainVideoUrl, setMainVideoUrl] = useState('');
  const [overlayVideoUrl, setOverlayVideoUrl] = useState('');
  const [position, setPosition] = useState('bottom_right');
  const [scale, setScale] = useState(0.3);
  const [mainVolume, setMainVolume] = useState(1.0);
  const [overlayVolume, setOverlayVolume] = useState(1.0);
  const [speedFactor, setSpeedFactor] = useState(1.0);
  const [x, setX] = useState('');
  const [y, setY] = useState('');
  const [opacity, setOpacity] = useState(1.0);
  const [customLayout, setCustomLayout] = useState(false);
  const [uploadToDrive, setUploadToDrive] = useState(false);
  const [driveFolderId, setDriveFolderId] = useState('');
  const [processing, setProcessing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setProcessing(true);
    setResult(null);
    setError('');

    const formData = new FormData();
    if (mainVideo) formData.append('main_video', mainVideo);
    if (overlayVideo) formData.append('overlay_video', overlayVideo);
    if (mainVideoUrl) formData.append('main_video_url', mainVideoUrl);
    if (overlayVideoUrl) formData.append('overlay_video_url', overlayVideoUrl);
    formData.append('position', position);
    formData.append('scale', scale);
    formData.append('main_volume', mainVolume);
    formData.append('overlay_volume', overlayVolume);
    formData.append('speed_factor', speedFactor);
    if (x) formData.append('x', x);
    if (y) formData.append('y', y);
    formData.append('opacity', opacity);
    formData.append('custom_layout', customLayout);
    formData.append('upload_to_drive', uploadToDrive);
    if (uploadToDrive && driveFolderId) formData.append('drive_folder_id', driveFolderId);

    try {
      const response = await axios.post(`${API_BASE_URL}/process-video/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(response.data);
    } catch (err) {
      setError('Processing failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setProcessing(false);
    }
  };

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>Video Overlay Processor</Typography>
      
      <form onSubmit={handleSubmit}>
        <Box sx={{ mb: 2 }}>
          <Typography variant="h6">Input Videos</Typography>
          <input type="file" accept="video/*" onChange={(e) => setMainVideo(e.target.files[0])} />
          <TextField
            label="Main Video Google Drive URL"
            value={mainVideoUrl}
            onChange={(e) => setMainVideoUrl(e.target.value)}
            fullWidth
            margin="normal"
          />
          <input type="file" accept="video/*" onChange={(e) => setOverlayVideo(e.target.files[0])} />
          <TextField
            label="Overlay Video Google Drive URL"
            value={overlayVideoUrl}
            onChange={(e) => setOverlayVideoUrl(e.target.value)}
            fullWidth
            margin="normal"
          />
        </Box>

        <Box sx={{ mb: 2 }}>
          <Typography variant="h6">Overlay Settings</Typography>
          <FormControl fullWidth margin="normal">
            <InputLabel>Position</InputLabel>
            <Select value={position} onChange={(e) => setPosition(e.target.value)}>
              <MenuItem value="top_left">Top Left</MenuItem>
              <MenuItem value="top_right">Top Right</MenuItem>
              <MenuItem value="bottom_left">Bottom Left</MenuItem>
              <MenuItem value="bottom_right">Bottom Right</MenuItem>
              <MenuItem value="center">Center</MenuItem>
              <MenuItem value="custom">Custom</MenuItem>
            </Select>
          </FormControl>
          {position === 'custom' && (
            <>
              <TextField
                label="X Position"
                type="number"
                value={x}
                onChange={(e) => setX(e.target.value)}
                fullWidth
                margin="normal"
              />
              <TextField
                label="Y Position"
                type="number"
                value={y}
                onChange={(e) => setY(e.target.value)}
                fullWidth
                margin="normal"
              />
              <FormControlLabel
                control={<Checkbox checked={customLayout} onChange={(e) => setCustomLayout(e.target.checked)} />}
                label="Use Custom Layout"
              />
            </>
          )}
          <TextField
            label="Scale (0.1-2.0)"
            type="number"
            value={scale}
            onChange={(e) => setScale(Math.max(0.1, Math.min(2.0, e.target.value)))}
            fullWidth
            margin="normal"
            inputProps={{ step: 0.1 }}
          />
          <TextField
            label="Opacity (0.0-1.0)"
            type="number"
            value={opacity}
            onChange={(e) => setOpacity(Math.max(0.0, Math.min(1.0, e.target.value)))}
            fullWidth
            margin="normal"
            inputProps={{ step: 0.1 }}
          />
          <TextField
            label="Main Volume (0.0-2.0)"
            type="number"
            value={mainVolume}
            onChange={(e) => setMainVolume(Math.max(0.0, Math.min(2.0, e.target.value)))}
            fullWidth
            margin="normal"
            inputProps={{ step: 0.1 }}
          />
          <TextField
            label="Overlay Volume (0.0-2.0)"
            type="number"
            value={overlayVolume}
            onChange={(e) => setOverlayVolume(Math.max(0.0, Math.min(2.0, e.target.value)))}
            fullWidth
            margin="normal"
            inputProps={{ step: 0.1 }}
          />
          <TextField
            label="Speed Factor (0.5-2.0)"
            type="number"
            value={speedFactor}
            onChange={(e) => setSpeedFactor(Math.max(0.5, Math.min(2.0, e.target.value)))}
            fullWidth
            margin="normal"
            inputProps={{ step: 0.1 }}
          />
        </Box>

        <Box sx={{ mb: 2 }}>
          <Typography variant="h6">Google Drive Options</Typography>
          <FormControlLabel
            control={<Checkbox checked={uploadToDrive} onChange={(e) => setUploadToDrive(e.target.checked)} />}
            label="Upload to Google Drive"
          />
          {uploadToDrive && (
            <TextField
              label="Google Drive Folder ID (optional)"
              value={driveFolderId}
              onChange={(e) => setDriveFolderId(e.target.value)}
              fullWidth
              margin="normal"
            />
          )}
        </Box>

        <Button type="submit" variant="contained" color="primary" disabled={processing}>
          {processing ? <CircularProgress size={24} /> : 'Process Video'}
        </Button>
      </form>

      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      {result && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="h6">Result</Typography>
          {result.output_path && (
            <Button
              variant="contained"
              href={`${API_BASE_URL}/download/${result.output_path}`}
              download
            >
              Download Processed Video
            </Button>
          )}
          {result.drive_upload && (
            <>
              <Typography>Uploaded to Google Drive:</Typography>
              <a href={result.drive_upload.webViewLink} target="_blank" rel="noopener noreferrer">
                View on Google Drive
              </a>
              <br />
              <a href={result.drive_upload.downloadLink}>Download from Google Drive</a>
            </>
          )}
        </Box>
      )}
    </Container>
  );
}

export default Over;
