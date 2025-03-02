import React, { useState } from 'react';
import './web.css';

function WebScraper() {
  const [formData, setFormData] = useState({
    subreddit: '',
    media_types: [],
    keywords: '',
    sort_by: 'hot',
    limit: 25,
    date_after: '',
    min_upvotes: 0,
    download_limit: '',
    save_to_drive: false,
    drive_folder_url: '',
    save_locally: false,
    local_folder: ''
  });
  
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);

  const handleInputChange = (e) => {
    const { name, value, type, checked } = e.target;
    if (type === 'checkbox') {
      if (name === 'save_to_drive' || name === 'save_locally') {
        setFormData({ ...formData, [name]: checked });
      } else if (name === 'media_types') {
        // Handle media type checkboxes
        const updatedMediaTypes = checked 
          ? [...formData.media_types, value]
          : formData.media_types.filter(type => type !== value);
        setFormData({ ...formData, media_types: updatedMediaTypes });
      }
    } else {
      setFormData({ ...formData, [name]: value });
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setResults(null);
    
    try {
      // Create FormData object for API call
      const apiFormData = new FormData();
      apiFormData.append('subreddit', formData.subreddit);
      
      // Handle media_types as array
      formData.media_types.forEach(type => {
        apiFormData.append('media_types', type);
      });
      
      apiFormData.append('keywords', formData.keywords);
      apiFormData.append('sort_by', formData.sort_by);
      apiFormData.append('limit', formData.limit.toString());
      
      if (formData.date_after) {
        apiFormData.append('date_after', formData.date_after);
      }
      
      apiFormData.append('min_upvotes', formData.min_upvotes.toString());
      
      if (formData.download_limit) {
        apiFormData.append('download_limit', formData.download_limit.toString());
      }
      
      apiFormData.append('save_to_drive', formData.save_to_drive.toString());
      
      if (formData.save_to_drive && formData.drive_folder_url) {
        apiFormData.append('drive_folder_url', formData.drive_folder_url);
      }
      
      apiFormData.append('save_locally', formData.save_locally.toString());
      
      if (formData.save_locally && formData.local_folder) {
        apiFormData.append('local_folder', formData.local_folder);
      }
      
      // Log the FormData for debugging
      for (let pair of apiFormData.entries()) {
        console.log(pair[0] + ': ' + pair[1]);
      }
      
      const response = await fetch('https://web-scraper-dl2q.onrender.com/scrape', {
        method: 'POST',
        body: apiFormData,
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        try {
          // Try to parse as JSON
          const errorData = JSON.parse(errorText);
          throw new Error(errorData.detail || 'Failed to scrape data');
        } catch (jsonError) {
          // If not JSON, use the raw text
          throw new Error(errorText || 'Failed to scrape data');
        }
      }
      
      const data = await response.json();
      setResults(data);
    } catch (err) {
      console.error("Error details:", err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header>
        <h1>Reddit Media Scraper</h1>
      </header>
      
      <main>
        <form onSubmit={handleSubmit} className="scraper-form">
          <div className="form-group">
            <label htmlFor="subreddit">Subreddit:</label>
            <input
              type="text"
              id="subreddit"
              name="subreddit"
              value={formData.subreddit}
              onChange={handleInputChange}
              required
              placeholder="e.g. pics, videos, aww"
            />
          </div>
          
          <div className="form-group">
            <label>Media Types (select at least one):</label>
            <div className="checkbox-group">
              <label>
                <input
                  type="checkbox"
                  name="media_types"
                  value="images"
                  checked={formData.media_types.includes('images')}
                  onChange={handleInputChange}
                />
                Images
              </label>
              <label>
                <input
                  type="checkbox"
                  name="media_types"
                  value="videos"
                  checked={formData.media_types.includes('videos')}
                  onChange={handleInputChange}
                />
                Videos
              </label>
            </div>
            {formData.media_types.length === 0 && (
              <p className="error-text">Please select at least one media type</p>
            )}
          </div>
          
          <div className="form-group">
            <label htmlFor="keywords">Keywords (comma separated):</label>
            <input
              type="text"
              id="keywords"
              name="keywords"
              value={formData.keywords}
              onChange={handleInputChange}
              placeholder="Optional: cat, dog, cute"
            />
          </div>
          
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="sort_by">Sort By:</label>
              <select
                id="sort_by"
                name="sort_by"
                value={formData.sort_by}
                onChange={handleInputChange}
              >
                <option value="hot">Hot</option>
                <option value="new">New</option>
                <option value="top">Top</option>
                <option value="rising">Rising</option>
              </select>
            </div>
            
            <div className="form-group">
              <label htmlFor="limit">Post Limit:</label>
              <input
                type="number"
                id="limit"
                name="limit"
                value={formData.limit}
                onChange={handleInputChange}
                min="1"
                max="100"
              />
            </div>
          </div>
          
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="date_after">Date After:</label>
              <input
                type="date"
                id="date_after"
                name="date_after"
                value={formData.date_after}
                onChange={handleInputChange}
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="min_upvotes">Min Upvotes:</label>
              <input
                type="number"
                id="min_upvotes"
                name="min_upvotes"
                value={formData.min_upvotes}
                onChange={handleInputChange}
                min="0"
              />
            </div>
          </div>
          
          <div className="form-group">
            <label htmlFor="download_limit">Download Limit:</label>
            <input
              type="number"
              id="download_limit"
              name="download_limit"
              value={formData.download_limit}
              onChange={handleInputChange}
              min="1"
              placeholder="Optional"
            />
          </div>
          
          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                name="save_to_drive"
                checked={formData.save_to_drive}
                onChange={handleInputChange}
              />
              Save to Google Drive
            </label>
            
            {formData.save_to_drive && (
              <input
                type="text"
                name="drive_folder_url"
                value={formData.drive_folder_url}
                onChange={handleInputChange}
                placeholder="Google Drive folder URL"
                className="conditional-input"
              />
            )}
          </div>
          
          <div className="form-group">
            <label className="checkbox-label">
              <input
                type="checkbox"
                name="save_locally"
                checked={formData.save_locally}
                onChange={handleInputChange}
              />
              Save Locally
            </label>
            
            {formData.save_locally && (
              <input
                type="text"
                name="local_folder"
                value={formData.local_folder}
                onChange={handleInputChange}
                placeholder="Local folder path"
                className="conditional-input"
                required={formData.save_locally}
              />
            )}
          </div>
          
          <button 
            type="submit" 
            className="submit-button" 
            disabled={isLoading || formData.media_types.length === 0}
          >
            {isLoading ? 'Scraping...' : 'Start Scraping'}
          </button>
        </form>
        
        {error && (
          <div className="error-message">
            <h3>Error:</h3>
            <p>{error}</p>
          </div>
        )}
        
        {results && (
          <div className="results-container">
            <h2>Scrape Results</h2>
            {results.media && results.media.length > 0 ? (
              <>
                <p>Found {results.media.length} media files</p>
                
                <div className="media-grid">
                  {results.media.map((item, index) => (
                    <div key={index} className="media-card">
                      <h3 title={item.title}>{item.title}</h3>
                      <p>Type: {item.type}</p>
                      <p>Filename: {item.filename}</p>
                      <div className="media-links">
                        <a href={item.url} target="_blank" rel="noopener noreferrer">
                          Original Link
                        </a>
                        {item.drive_link && (
                          <a href={item.drive_link} target="_blank" rel="noopener noreferrer">
                            Drive Link
                          </a>
                        )}
                        {!item.drive_link && item.filename && (
                          <a href={`https://web-scraper-dl2q.onrender.com/download/${item.filename}`} target="_blank" rel="noopener noreferrer">
                            Download
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p>No media files found matching your criteria.</p>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default WebScraper;
