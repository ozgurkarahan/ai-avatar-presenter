import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from './App';
import PodcastPage from './pages/PodcastPage';
import PodcastLibraryPage from './pages/PodcastLibraryPage';
import TopNav from './components/TopNav';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <TopNav />
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/podcast" element={<PodcastPage />} />
        <Route path="/podcast/library" element={<PodcastLibraryPage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
