import React, { useRef, useState, useCallback } from 'react';
import Webcam from 'react-webcam';

const Cam = () => {
  const webcamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const [recording, setRecording] = useState(false);
  const [videoBlob, setVideoBlob] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [driveLinks, setDriveLinks] = useState(null);
  const [folderId, setFolderId] = useState('');
  const [error, setError] = useState(null);

  const getSupportedMimeType = () => {
    const types = [
      'video/webm',
      'video/webm;codecs=vp9',
      'video/webm;codecs=vp8',
      'video/webm;codecs=h264',
      'video/mp4',
    ];
    for (const type of types) {
      if (MediaRecorder.isTypeSupported(type)) {
        return type;
      }
    }
    return '';
  };

  const handleStartRecording = useCallback(() => {
    if (!webcamRef.current) return;

    const stream = webcamRef.current.video.srcObject;
    if (!stream) {
      console.error('No stream available');
      return;
    }

    try {
      setError(null);
      const mimeType = getSupportedMimeType();
      if (!mimeType) {
        setError('No supported MIME type found for MediaRecorder');
        return;
      }

      setRecording(true);
      mediaRecorderRef.current = new MediaRecorder(stream, { mimeType });
      const recordedChunks = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordedChunks.push(event.data);
        }
      };

      mediaRecorderRef.current.onstop = async () => {
        const blob = new Blob(recordedChunks, { type: mimeType });
        setVideoBlob(blob);

        // Upload to FastAPI server for conversion and Google Drive upload
        await uploadToDrive(blob);
      };

      mediaRecorderRef.current.start(1000);
    } catch (error) {
      console.error('Error starting recording:', error);
      setError(`Recording error: ${error.message}`);
      setRecording(false);
    }
  }, []);

  const handleStopRecording = useCallback(() => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  }, [recording]);

  // Handle folder ID input change
  const handleFolderIdChange = (event) => {
    setFolderId(event.target.value);
  };

  // Upload WebM to FastAPI for conversion and Google Drive upload
  const uploadToDrive = async (webmBlob) => {
    setIsUploading(true);
    setError(null);
    
    try {
      const formData = new FormData();
      const filename = `recording-${new Date().toISOString()}.webm`;
      formData.append('file', webmBlob, filename);
      formData.append('folder_id', folderId || '');

      const response = await fetch('http://localhost:8000/convert-to-mp4', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Server error: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      // Store the links from Google Drive
      setDriveLinks({
        downloadUrl: data.download_url,
        viewUrl: data.view_url,
        fileId: data.file_id
      });
      
      console.log('Upload successful:', data.message);
    } catch (error) {
      console.error('Error uploading video:', error.message);
      setError(`Upload error: ${error.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div style={{ textAlign: 'center', padding: '20px' }}>
      <h2>WebM Recorder with Google Drive Upload</h2>
      
      <Webcam
        audio={true}
        ref={webcamRef}
        videoConstraints={{
          width: 500,
          height: 500,
          facingMode: 'user',
        }}
        style={{ marginBottom: '20px', borderRadius: '8px' }}
      />
      
      <div style={{ marginBottom: '15px' }}>
        <input
          type="text"
          value={folderId}
          onChange={handleFolderIdChange}
          placeholder="Enter Google Drive Folder ID (optional)"
          style={{ 
            padding: '10px', 
            marginBottom: '10px', 
            width: '300px',
            borderRadius: '4px',
            border: '1px solid #ccc'
          }}
        />
      </div>
      
      <div style={{ marginBottom: '15px' }}>
        {!recording ? (
          <button
            onClick={handleStartRecording}
            disabled={isUploading}
            style={{ 
              padding: '10px 20px', 
              marginRight: '10px',
              backgroundColor: '#4CAF50',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: isUploading ? 'not-allowed' : 'pointer'
            }}
          >
            Start Recording
          </button>
        ) : (
          <button
            onClick={handleStopRecording}
            disabled={isUploading}
            style={{ 
              padding: '10px 20px', 
              marginRight: '10px',
              backgroundColor: '#f44336',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: isUploading ? 'not-allowed' : 'pointer'
            }}
          >
            Stop Recording
          </button>
        )}
      </div>
      
      {isUploading && (
        <div style={{ marginTop: '15px' }}>
          <p>Uploading and converting your video...</p>
          {/* You could add a progress indicator here */}
        </div>
      )}
      
      {error && (
        <div style={{ 
          marginTop: '15px', 
          color: 'red', 
          padding: '10px',
          backgroundColor: '#ffebee',
          borderRadius: '4px' 
        }}>
          <p>{error}</p>
        </div>
      )}
      
      {driveLinks && (
        <div style={{ 
          marginTop: '20px',
          border: '1px solid #ddd',
          borderRadius: '8px',
          padding: '15px',
          backgroundColor: '#f9f9f9'
        }}>
          <h3>Video Successfully Uploaded to Google Drive</h3>
          <div style={{ margin: '15px 0' }}>
            <a 
              href={driveLinks.downloadUrl} 
              target="_blank" 
              rel="noopener noreferrer"
              style={{
                display: 'inline-block',
                padding: '8px 16px',
                backgroundColor: '#2196F3',
                color: 'white',
                textDecoration: 'none',
                borderRadius: '4px',
                margin: '0 10px'
              }}
            >
              Download Video
            </a>
            <a 
              href={driveLinks.viewUrl} 
              target="_blank" 
              rel="noopener noreferrer"
              style={{
                display: 'inline-block',
                padding: '8px 16px',
                backgroundColor: '#FF9800',
                color: 'white',
                textDecoration: 'none',
                borderRadius: '4px',
                margin: '0 10px'
              }}
            >
              View in Google Drive
            </a>
          </div>
          <div style={{ fontSize: '12px', color: '#666' }}>
            <p>File ID: {driveLinks.fileId}</p>
          </div>
        </div>
      )}
      
      {videoBlob && !driveLinks && !isUploading && (
        <div style={{ marginTop: '20px' }}>
          <h3>Recording Preview:</h3>
          <video
            src={URL.createObjectURL(videoBlob)}
            controls
            style={{ maxWidth: '100%', borderRadius: '8px' }}
          />
        </div>
      )}
    </div>
  );
};

export default Cam;
