import React, { useState } from 'react';
import axios from 'axios';
import './web.css';

const WebScraping = () => {
  const [formData, setFormData] = useState({
    subreddit: '',
    mediaTypes: { images: true, videos: true },
    keywords: '',
    sortBy: 'hot',
    limit: 25,
    dateAfter: '',
    minUpvotes: 0,
    downloadLimit: '',
    saveToDrive: false,
    driveFolderUrl: '',
    saveLocally: false,
    localFolder: '',
  });
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [localFiles, setLocalFiles] = useState(null);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    if (type === 'checkbox' && name in formData.mediaTypes) {
      setFormData({
        ...formData,
        mediaTypes: { ...formData.mediaTypes, [name]: checked },
      });
    } else if (type === 'checkbox') {
      setFormData({ ...formData, [name]: checked });
    } else {
      setFormData({ ...formData, [name]: value });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResults(null);
    setLocalFiles(null);

    const mediaTypes = Object.keys(formData.mediaTypes).filter(
      (key) => formData.mediaTypes[key]
    );
    if (mediaTypes.length === 0) {
      setError('Please select at least one media type to scrape');
      setLoading(false);
      return;
    }

    const data = new FormData();
    data.append('subreddit', formData.subreddit);
    mediaTypes.forEach((type) => data.append('media_types', type));
    data.append('keywords', formData.keywords);
    data.append('sort_by', formData.sortBy);
    data.append('limit', formData.limit);
    if (formData.dateAfter) data.append('date_after', formData.dateAfter);
    data.append('min_upvotes', formData.minUpvotes);
    if (formData.downloadLimit) data.append('download_limit', formData.downloadLimit);
    data.append('save_to_drive', formData.saveToDrive);
    if (formData.driveFolderUrl) data.append('drive_folder_url', formData.driveFolderUrl);
    data.append('save_locally', formData.saveLocally);
    if (formData.localFolder) data.append('local_folder', formData.localFolder);

    try {
      const response = await axios.post('https://webscraper-i3yv.onrender.com/scrape', data, {
        headers: {
          'Client-ID': process.env.REACT_APP_CLIENT_ID,
          'Client-Secret': process.env.REACT_APP_CLIENT_SECRET,
          'User-Agent': process.env.REACT_APP_USER_AGENT,
        },
      });
      setResults(response.data);

      // If local saving was enabled, fetch the list of local files
      if (formData.saveLocally && formData.localFolder) {
        try {
          const localFilesResponse = await axios.get(
            `https://web-scraper-fxf1.onrender.com/local-downloads?folder_path=${encodeURIComponent(formData.localFolder)}`,
            {
              headers: {
                'Client-ID': process.env.REACT_APP_CLIENT_ID,
                'User-Agent': process.env.REACT_APP_USER_AGENT,
              },
            }
          );
          setLocalFiles(localFilesResponse.data);
        } catch (localErr) {
          console.error("Error fetching local files:", localErr);
        }
      }
    } catch (err) {
      setError(err.response?.data?.error || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <h1>Reddit Media Scraper</h1>
      <form onSubmit={handleSubmit} className="form">
        <div className="form-group">
          <label>Subreddit name:</label>
          <input
            type="text"
            name="subreddit"
            value={formData.subreddit}
            onChange={handleChange}
            placeholder="Enter subreddit"
            required
          />
        </div>

        <div className="form-group">
          <label>Media types to scrape:</label>
          <div className="checkbox-group">
            <label>
              <input
                type="checkbox"
                name="images"
                checked={formData.mediaTypes.images}
                onChange={handleChange}
              /> Images
            </label>
            <label>
              <input
                type="checkbox"
                name="videos"
                checked={formData.mediaTypes.videos}
                onChange={handleChange}
              /> Videos
            </label>
          </div>
        </div>

        <div className="form-group">
          <label>Keywords (optional):</label>
          <textarea
            name="keywords"
            value={formData.keywords}
            onChange={handleChange}
            placeholder="Enter keywords separated by commas"
          />
          <div className="hint">Posts will be filtered to include only those with these keywords.</div>
        </div>

        <div className="form-group">
          <label>Sort by:</label>
          <select name="sortBy" value={formData.sortBy} onChange={handleChange}>
            <option value="hot">Hot</option>
            <option value="new">New</option>
            <option value="top">Top</option>
            <option value="rising">Rising</option>
          </select>
        </div>

        <div className="form-group">
          <label>Number of posts to check:</label>
          <input
            type="number"
            name="limit"
            value={formData.limit}
            onChange={handleChange}
            min="1"
            max="100"
          />
        </div>

        <div className="form-group">
          <label>Posts after date (optional):</label>
          <input
            type="date"
            name="dateAfter"
            value={formData.dateAfter}
            onChange={handleChange}
          />
          <div className="hint">Only include posts created after this date.</div>
        </div>

        <div className="form-group">
          <label>Minimum upvotes (optional):</label>
          <input
            type="number"
            name="minUpvotes"
            value={formData.minUpvotes}
            onChange={handleChange}
            min="0"
          />
          <div className="hint">Only include posts with at least this many upvotes.</div>
        </div>

        <div className="form-group">
          <label>Number of files to download (optional):</label>
          <input
            type="number"
            name="downloadLimit"
            value={formData.downloadLimit}
            onChange={handleChange}
            min="1"
          />
          <div className="hint">Limit the number of media files to download.</div>
        </div>

        <div className="form-group">
          <label>
            <input
              type="checkbox"
              name="saveToDrive"
              checked={formData.saveToDrive}
              onChange={handleChange}
            /> Save to Google Drive
          </label>
          <div className="hint">If checked, files will be uploaded to your Google Drive.</div>
        </div>

        <div className="form-group">
          <label>Google Drive Folder URL (optional):</label>
          <input
            type="text"
            name="driveFolderUrl"
            value={formData.driveFolderUrl}
            onChange={handleChange}
            placeholder="e.g., https://drive.google.com/drive/folders/abc123"
            disabled={!formData.saveToDrive}
          />
          <div className="hint">Paste a Google Drive folder URL to save files there.</div>
        </div>

        {/* New local download options */}
        <div className="section-divider"></div>
        <h3>Local Download Options</h3>

        <div className="form-group">
          <label>
            <input
              type="checkbox"
              name="saveLocally"
              checked={formData.saveLocally}
              onChange={handleChange}
            /> Save files to local folder
          </label>
          <div className="hint">If checked, files will be saved to the specified folder on your machine.</div>
        </div>

        <div className="form-group">
          <label>Local folder path:</label>
          <input
            type="text"
            name="localFolder"
            value={formData.localFolder}
            onChange={handleChange}
            placeholder="e.g., C:/Users/YourName/Downloads/RedditMedia"
            disabled={!formData.saveLocally}
          />
          <div className="hint">Provide the full path to the folder where you want to save the files.</div>
        </div>

        <button type="submit" disabled={loading}>
          {loading ? 'Scraping...' : 'Scrape Media'}
        </button>
      </form>

      {error && <div className="error">{error}</div>}

      {results && (
        <div className="results">
          <h2>Scraped Media from r/{results.subreddit}</h2>
          <div className="summary">
            <p><strong>Search Summary:</strong></p>
            <ul>
              <li>Subreddit: r/{results.subreddit}</li>
              <li>Sort: {results.sort_by}</li>
              <li>Media types: {results.media_types.join(', ')}</li>
              <li>Keywords: {results.keywords || 'None'}</li>
              <li>Date filter: {results.date_after || 'None'}</li>
              <li>Minimum upvotes: {results.min_upvotes}</li>
              <li>Download limit: {results.download_limit || 'All'}</li>
              <li>Save to Drive: {results.save_to_drive ? 'Yes' : 'No'}</li>
              <li>Drive Folder: {results.drive_folder_url ? <a href={results.drive_folder_url} target="_blank" rel="noopener noreferrer">Link</a> : 'None'}</li>
              <li>Save Locally: {results.save_locally ? 'Yes' : 'No'}</li>
              <li>Local Folder: {results.local_folder || 'None'}</li>
              <li>Total media found: {results.media.length} (
                {results.media.filter(m => m.type === 'image').length} images, 
                {results.media.filter(m => m.type === 'video').length} videos)
              </li>
            </ul>
          </div>

          {results.media.length === 0 ? (
            <p>No matching media found.</p>
          ) : (
            results.media.map((item, index) => (
              <div key={index} className="media-item">
                <h3>{item.type === 'image' ? '🖼️' : '🎬'} {item.title}</h3>
                <div className="details">
                  Score: {item.score} | Posted: {item.created}
                </div>
                <div className="media-links">
                  <a href={`https://web-scraper-fxf1.onrender.com/download/${item.filename}`} download>
                    Download {item.type}
                  </a>
                  <a href={item.url} target="_blank" rel="noopener noreferrer">
                    View original post
                  </a>
                  {item.drive_link && (
                    <a href={item.drive_link} target="_blank" rel="noopener noreferrer">
                      View on Google Drive
                    </a>
                  )}
                  {item.local_path && (
                    <span className="local-path">
                      Saved to: {item.local_path}
                    </span>
                  )}
                </div>
              </div>
            ))
          )}

          {/* Display local folder contents if available */}
          {localFiles && localFiles.files && (
            <div className="local-files">
              <h3>Files in local folder: {localFiles.folder}</h3>
              <div className="files-grid">
                {localFiles.files.map((file, index) => (
                  <div key={index} className="local-file-item">
                    <div>{file.name}</div>
                    <div className="file-details">
                      Size: {(file.size / 1024).toFixed(2)} KB | 
                      Created: {file.created}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default WebScraping;
