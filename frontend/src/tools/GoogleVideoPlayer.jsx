import { useState } from 'react';
import Cam from './Cam';

const GoogleDriveFolderVideoPlayer = () => {
  const [error, setError] = useState(false);
  const [videoList, setVideoList] = useState([]); // Array of { id, name } objects
  const [selectedVideoId, setSelectedVideoId] = useState('');
  const [folderId, setFolderId] = useState('');
  const [inputError, setInputError] = useState('');

  const videoUrl = selectedVideoId 
    ? `https://drive.google.com/file/d/${selectedVideoId}/preview`
    : '';

  const handleError = () => {
    setError(true);
  };

  const handleVideoSelect = (id) => {
    setSelectedVideoId(id);
    setError(false);
  };

  const addVideoId = (newId, name = `Video ${videoList.length + 1}`) => {
    // Basic ID validation (Google Drive IDs are ~33 chars, alphanumeric with hyphens)
    if (!newId || !/^[A-Za-z0-9_-]{25,40}$/.test(newId)) {
      setInputError('Invalid video ID. It should be a valid Google Drive file ID.');
      return;
    }
    if (!videoList.some(video => video.id === newId)) {
      setVideoList([...videoList, { id: newId, name }]);
      setInputError('');
      if (!selectedVideoId) setSelectedVideoId(newId); // Auto-select first video
    } else {
      setInputError('Video ID already exists.');
    }
  };

  const removeVideoId = (idToRemove) => {
    setVideoList(videoList.filter(video => video.id !== idToRemove));
    if (selectedVideoId === idToRemove) {
      setSelectedVideoId(videoList[0]?.id || '');
    }
  };

  // Fetch videos from a Google Drive folder (requires API setup)
  const fetchVideosFromFolder = async (folderId) => {
    try {
      // Placeholder for Google Drive API call
      // Replace with actual API endpoint and authentication
      const response = await fetch(
        `https://www.googleapis.com/drive/v3/files?q='${folderId}'+in+parents&fields=files(id,name,mimeType)&key=YOUR_API_KEY`,
        {
          headers: {
            Authorization: 'Bearer YOUR_ACCESS_TOKEN', // Add OAuth token here
          },
        }
      );
      if (!response.ok) throw new Error('Failed to fetch folder contents');
      const data = await response.json();
      const videoFiles = data.files.filter(file => file.mimeType.includes('video'));
      const newVideoList = videoFiles.map(file => ({ id: file.id, name: file.name }));
      
      setVideoList(newVideoList);
      if (newVideoList.length > 0 && !selectedVideoId) {
        setSelectedVideoId(newVideoList[0].id);
      }
      setInputError('');
    } catch (err) {
      console.error('Error fetching folder videos:', err);
      setInputError('Failed to load videos from folder. Check the folder ID and try again.');
    }
  };

  const handleFolderSubmit = () => {
    if (folderId) fetchVideosFromFolder(folderId);
  };

  return (
    <div className="w-full">
     

      {/* Manual Video ID Input */}
      <div className="mb-4">
        <h3 className="text-lg font-semibold mb-2">Add Video ID Manually:</h3>
        <input
          type="text"
          placeholder="Add Video ID from folder"
          onKeyPress={(e) => {
            if (e.key === 'Enter' && e.target.value) {
              addVideoId(e.target.value);
              e.target.value = '';
            }
          }}
          className="p-2 border rounded w-full max-w-md"
        />
        {inputError && <p className="text-red-500 mt-1">{inputError}</p>}
      </div>

      {/* Video Selection */}
      {videoList.length > 0 && (
        <div className="mb-4">
          <h3 className="text-lg font-semibold mb-2">Select a Video:</h3>
          <div className="flex flex-wrap gap-2">
            {videoList.map((video) => (
              <div key={video.id} className="flex items-center gap-2">
                <button
                  onClick={() => handleVideoSelect(video.id)}
                  className={`px-4 py-2 rounded ${
                    selectedVideoId === video.id 
                      ? 'bg-blue-500 text-white' 
                      : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                  }`}
                >
                  {video.name}
                </button>
                <button
                  onClick={() => removeVideoId(video.id)}
                  className="px-2 py-1 bg-red-500 text-white rounded hover:bg-red-600"
                >
                  X
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Video Player */}
      <div className="aspect-w-16 aspect-h-9 w-full rounded-lg overflow-hidden border border-gray-200">
        {error || !selectedVideoId ? (
          <div className="flex items-center justify-center h-full text-red-500">
            {error 
              ? 'Unable to load video. Please check the ID and try again.' 
              : 'Please add and select a video to play.'}
          </div>
        ) : (
          <iframe
            src={videoUrl}
            className="w-full h-full"
            allow="autoplay"
            allowFullScreen
            frameBorder="0"
            onError={handleError}
          />
        )}
      </div>

      <Cam />
    </div>
  );
};

export default GoogleDriveFolderVideoPlayer;
