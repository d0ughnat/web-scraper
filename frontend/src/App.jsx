import React, { useState } from 'react';
import WebScraping from './tools/WebScraping';
import GoogleDriveVideoPlayer from './tools/GoogleVideoPlayer';
import './App.css';

function App() {
  const [activeTab, setActiveTab] = useState('webscraping');

  // Sample array of Google Drive video IDs - replace with your actual IDs
  const videoIds = [
    'YOUR_VIDEO_ID_1',
    'YOUR_VIDEO_ID_2',
    'YOUR_VIDEO_ID_3'
  ];

  const handleTabChange = (tab) => {
    setActiveTab(tab);
  };

  return (
    <>
      <header className="app-header">
        <h1>Website Scraper</h1>
      </header>
      <div className="app">
        <main className="app-content">
          <div className="content-wrapper">
            {/* Tab Navigation */}
            <div className="tab-navigation">
              <button
                className={`tab-button ${activeTab === 'webscraping' ? 'active' : ''}`}
                onClick={() => handleTabChange('webscraping')}
              >
                Web Scraping
              </button>
              <button
                className={`tab-button ${activeTab === 'video' ? 'active' : ''}`}
                onClick={() => handleTabChange('video')}
              >
                Reaction Video
              </button>
            </div>

            {/* Tab Content */}
            <section className="tab-content">
              {activeTab === 'webscraping' && (
                <div className="web-scraping-section">
                  <h2>Web Scraping</h2>
                  <WebScraping />
                </div>
              )}
              {activeTab === 'video' && (
                <div className="video-section">
                  <h2>Reaction Video</h2>
                  <GoogleDriveVideoPlayer videoIds={videoIds} />
                </div>
              )}
            </section>
          </div>
        </main>
      </div>
      <footer className="app-footer">
        <p>© 2025 Social Media Scraper</p>
      </footer>
    </>
  );
}

export default App;
