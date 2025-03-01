import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './App.css';

function App() {
  // API URL - change this to your deployed API URL
  const API_URL = "https://webscraper-i3yv.onrender.com"; // Update with your actual Render URL

  // State for form inputs
  const [subreddit, setSubreddit] = useState('');
  const [mediaTypes, setMediaTypes] = useState(['images', 'videos']);
  const [keywords, setKeywords] = useState('');
  const [sortBy, setSortBy] = useState('hot');
  const [limit, setLimit] = useState(25);
  const [dateAfter, setDateAfter] = useState('');
  const [minUpvotes, setMinUpvotes] = useState(0);
  const [downloadLimit, setDownloadLimit] = useState(null);
  const [saveToDrive, setSaveToDrive] = useState(false);
  const [driveFolderUrl, setDriveFolderUrl] = useState('');
  const [saveLocally, setSaveLocally] = useState(false);
  const [localFolder, setLocalFolder] = useState('');

  // State for results
  const [media, setMedia] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');

  // State for file conversion
  const [file, setFile] = useState(null);
  const [convertedUrl, setConvertedUrl] = useState('');
  const [convertLoading, setConvertLoading] = useState(false);
  const [convertError, setConvertError] = useState(null);
  const [convertSuccess, setConvertSuccess] = useState('');
  const [driveFolderId, setDriveFolderId] = useState('');

  // State for tab navigation
  const [activeTab, setActiveTab] = useState('scraper');

  // Handle media type selection
  const handleMediaTypeChange = (type) => {
    if (mediaTypes.includes(type)) {
      setMediaTypes(mediaTypes.filter(t => t !== type));
    } else {
      setMediaTypes([...mediaTypes, type]);
    }
  };

  // Handle form submission for scraping
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccessMessage('');
    setMedia([]);

    // Validate form
    if (!subreddit) {
      setError('Please enter a subreddit name');
      setLoading(false);
      return;
    }

    if (mediaTypes.length === 0) {
      setError('Please select at least one media type');
      setLoading(false);
      return;
    }

    if (saveLocally && !localFolder) {
      setError('Please enter a local folder path');
      setLoading(false);
      return;
    }

    // Create form data
    const formData = new FormData();
    formData.append('subreddit', subreddit);
    mediaTypes.forEach(type => {
      formData.append('media_types', type);
    });
    formData.append('keywords', keywords);
    formData.append('sort_by', sortBy);
    formData.append('limit', limit);
    if (dateAfter) formData.append('date_after', dateAfter);
    formData.append('min_upvotes', minUpvotes);
    if (downloadLimit) formData.append('download_limit', downloadLimit);
    formData.append('save_to_drive', saveToDrive);
    if (driveFolderUrl) formData.append('drive_folder_url', driveFolderUrl);
    formData.append('save_locally', saveLocally);
    if (localFolder) formData.append('local_folder', localFolder);

    try {
      const response = await axios.post(`${API_URL}/scrape`, formData);
      setMedia(response.data.media || []);
      setSuccessMessage(`Successfully scraped ${response.data.media.length} media files`);
    } catch (error) {
      setError(error.response?.data?.detail || 'Failed to scrape media');
      console.error("Error:", error);
    } finally {
      setLoading(false);
    }
  };

  // Handle file upload for conversion
  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setConvertedUrl('');
    setConvertError(null);
    setConvertSuccess('');
  };

  // Handle file conversion
  const handleConvert = async (e) => {
    e.preventDefault();
    if (!file) {
      setConvertError('Please select a file to convert');
      return;
    }

    setConvertLoading(true);
    setConvertError(null);
    setConvertSuccess('');

    const formData = new FormData();
    formData.append('file', file);
    if (driveFolderId) formData.append('folder_id', driveFolderId);

    try {
      const response = await axios.post(`${API_URL}/convert-to-mp4`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });
      setConvertedUrl(response.data.view_url);
      setConvertSuccess('File successfully converted and uploaded to Google Drive');
    } catch (error) {
      setConvertError(error.response?.data?.detail || 'Failed to convert file');
      console.error("Error:", error);
    } finally {
      setConvertLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header>
        <h1>Reddit Media Scraper</h1>
        <nav>
          <button 
            className={activeTab === 'scraper' ? 'active' : ''} 
            onClick={() => setActiveTab('scraper')}
          >
            Scraper
          </button>
          <button 
            className={activeTab === 'converter' ? 'active' : ''} 
            onClick={() => setActiveTab('converter')}
          >
            Converter
          </button>
        </nav>
      </header>

      {activeTab === 'scraper' && (
        <div className="scraper-container">
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <h2>Reddit Scraper</h2>
              <p>Scrape images and videos from Reddit subreddits</p>
            </div>

            <div className="form-group">
              <label>Subreddit:</label>
              <input 
                type="text" 
                value={subreddit} 
                onChange={(e) => setSubreddit(e.target.value)}
                placeholder="e.g., EarthPorn, MemeEconomy"
              />
            </div>

            <div className="form-group">
              <label>Media Types:</label>
              <div className="checkbox-group">
                <label>
                  <input 
                    type="checkbox" 
                    checked={mediaTypes.includes('images')} 
                    onChange={() => handleMediaTypeChange('images')} 
                  />
                  Images
                </label>
                <label>
                  <input 
                    type="checkbox" 
                    checked={mediaTypes.includes('videos')} 
                    onChange={() => handleMediaTypeChange('videos')} 
                  />
                  Videos
                </label>
              </div>
            </div>

            <div className="form-group">
              <label>Keywords (comma separated):</label>
              <input 
                type="text" 
                value={keywords} 
                onChange={(e) => setKeywords(e.target.value)}
                placeholder="e.g., sunset, mountains"
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Sort By:</label>
                <select value={sortBy} onChange={(e) => setSortBy(e.target.value)}>
                  <option value="hot">Hot</option>
                  <option value="new">New</option>
                  <option value="top">Top</option>
                  <option value="rising">Rising</option>
                </select>
              </div>

              <div className="form-group">
                <label>Post Limit:</label>
                <input 
                  type="number" 
                  value={limit} 
                  onChange={(e) => setLimit(e.target.value)}
                  min="1"
                />
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Date After:</label>
                <input 
                  type="date" 
                  value={dateAfter} 
                  onChange={(e) => setDateAfter(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label>Min Upvotes:</label>
                <input 
                  type="number" 
                  value={minUpvotes} 
                  onChange={(e) => setMinUpvotes(e.target.value)}
                  min="0"
                />
              </div>
            </div>

            <div className="form-group">
              <label>Download Limit:</label>
              <input 
                type="number" 
                value={downloadLimit || ''} 
                onChange={(e) => setDownloadLimit(e.target.value ? parseInt(e.target.value) : null)}
                min="1"
                placeholder="No limit"
              />
            </div>

            <div className="form-group">
              <label>
                <input 
                  type="checkbox" 
                  checked={saveToDrive} 
                  onChange={(e) => setSaveToDrive(e.target.checked)} 
                />
                Save to Google Drive
              </label>
              {saveToDrive && (
                <input 
                  type="text" 
                  value={driveFolderUrl} 
                  onChange={(e) => setDriveFolderUrl(e.target.value)}
                  placeholder="Google Drive folder URL"
                  className="mt-2"
                />
              )}
            </div>

            <div className="form-group">
              <label>
                <input 
                  type="checkbox" 
                  checked={saveLocally} 
                  onChange={(e) => setSaveLocally(e.target.checked)} 
                />
                Save Locally
              </label>
              {saveLocally && (
                <input 
                  type="text" 
                  value={localFolder} 
                  onChange={(e) => setLocalFolder(e.target.value)}
                  placeholder="Local folder path"
                  className="mt-2"
                />
              )}
            </div>

            <button type="submit" disabled={loading} className="primary-button">
              {loading ? 'Scraping...' : 'Start Scraping'}
            </button>
          </form>

          {error && <div className="error-message">{error}</div>}
          {successMessage && <div className="success-message">{successMessage}</div>}

          {media.length > 0 && (
            <div className="results-container">
              <h2>Results</h2>
              <p>Found {media.length} media files</p>
              
              <div className="media-grid">
                {media.map((item, index) => (
                  <div key={index} className="media-card">
                    <h3>{item.title || 'Untitled'}</h3>
                    <p>Type: {item.type}</p>
                    <p>Filename: {item.filename}</p>
                    
                    {item.type === 'image' && (
                      <a href={`${API_URL}/download/${item.filename}`} target="_blank" rel="noreferrer">
                        <img 
                          src={`${API_URL}/download/${item.filename}`} 
                          alt={item.title || 'Reddit media'} 
                          className="thumbnail"
                        />
                      </a>
                    )}
                    
                    {item.type === 'video' && (
                      <a href={`${API_URL}/download/${item.filename}`} target="_blank" rel="noreferrer">
                        <div className="video-thumbnail">
                          <span>🎬 Video</span>
                        </div>
                      </a>
                    )}
                    
                    <div className="media-links">
                      <a href={item.url} target="_blank" rel="noreferrer">Original</a>
                      <a href={`${API_URL}/download/${item.filename}`} target="_blank" rel="noreferrer">Download</a>
                      {item.drive_link && (
                        <a href={item.drive_link} target="_blank" rel="noreferrer">Google Drive</a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'converter' && (
        <div className="converter-container">
          <form onSubmit={handleConvert}>
            <div className="form-group">
              <h2>WebM to MP4 Converter</h2>
              <p>Convert WebM videos to MP4 and upload to Google Drive</p>
            </div>

            <div className="form-group">
              <label>Select WebM File:</label>
              <input 
                type="file" 
                onChange={handleFileChange} 
                accept=".webm"
              />
            </div>

            <div className="form-group">
              <label>Google Drive Folder ID (optional):</label>
              <input 
                type="text" 
                value={driveFolderId} 
                onChange={(e) => setDriveFolderId(e.target.value)}
                placeholder="Google Drive folder ID"
              />
            </div>

            <button type="submit" disabled={convertLoading || !file} className="primary-button">
              {convertLoading ? 'Converting...' : 'Convert to MP4'}
            </button>
          </form>

          {convertError && <div className="error-message">{convertError}</div>}
          {convertSuccess && <div className="success-message">{convertSuccess}</div>}

          {convertedUrl && (
            <div className="conversion-result">
              <h3>Conversion Result</h3>
              <p>Your file has been converted and uploaded to Google Drive.</p>
              <a href={convertedUrl} target="_blank" rel="noreferrer" className="primary-button">
                View on Google Drive
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default App;
