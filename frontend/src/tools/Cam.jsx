import React, { useRef, useState, useCallback } from 'react';
import Webcam from 'react-webcam';

const Cam = () => {
  const webcamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const [recording, setRecording] = useState(false);
  const [videoBlob, setVideoBlob] = useState(null);

  // Function to get supported MIME type
  const getSupportedMimeType = () => {
    const types = [
      'video/webm',
      'video/webm;codecs=vp9',
      'video/webm;codecs=vp8',
      'video/webm;codecs=h264',
      'video/mp4'
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
      const mimeType = getSupportedMimeType();
      if (!mimeType) {
        console.error('No supported MIME type found for MediaRecorder');
        return;
      }
      
      setRecording(true);
      mediaRecorderRef.current = new MediaRecorder(stream, {
        mimeType: mimeType
      });
      
      const recordedChunks = [];
      
      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordedChunks.push(event.data);
        }
      };
      
      mediaRecorderRef.current.onstop = () => {
        // Use the same MIME type for the Blob
        const blob = new Blob(recordedChunks, { type: mimeType });
        setVideoBlob(blob);
        
        // Create filename extension based on MIME type
        const fileExtension = mimeType.includes('mp4') ? 'mp4' : 'webm';
        
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `recording-${new Date().toISOString()}.${fileExtension}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      };
      
      // Request data every second and when stopped
      mediaRecorderRef.current.start(1000);
    } catch (error) {
      console.error('Error starting recording:', error);
      setRecording(false);
    }
  }, []);

  const handleStopRecording = useCallback(() => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  }, [recording]);

  return (
    <div style={{ textAlign: 'center', padding: '20px' }}>
      <Webcam
        audio={true}
        ref={webcamRef}
        videoConstraints={{
          width: 500,
          height: 500,
          facingMode: 'user'
        }}
        style={{ marginBottom: '20px' }}
      />
      <div>
        {!recording ? (
          <button
            onClick={handleStartRecording}
            style={{ padding: '10px 20px', marginRight: '10px' }}
          >
            Start Recording
          </button>
        ) : (
          <button
            onClick={handleStopRecording}
            style={{ padding: '10px 20px', marginRight: '10px' }}
          >
            Stop Recording
          </button>
        )}
      </div>
      {videoBlob && (
        <div style={{ marginTop: '20px' }}>
          <h3>Recorded Video:</h3>
          <video
            src={URL.createObjectURL(videoBlob)}
            controls
            style={{ maxWidth: '100%' }}
          />
        </div>
      )}
    </div>
  );
};

export default Cam;
