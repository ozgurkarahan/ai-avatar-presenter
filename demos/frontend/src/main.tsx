import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import App from './App';
import PodcastPage from './pages/PodcastPage';
import PodcastLibraryPage from './pages/PodcastLibraryPage';
import StaticVideoPage from './pages/StaticVideoPage';
import StaticVideoLibraryPage from './pages/StaticVideoLibraryPage';
import Uc1HubPage from './pages/Uc1HubPage';
import Uc1LearnPage from './pages/Uc1LearnPage';
import Uc1DecksPage from './pages/Uc1DecksPage';
import Uc1PresentPage from './pages/Uc1PresentPage';
import TopNav from './components/TopNav';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <TopNav />
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/uc1" element={<Uc1HubPage />} />
        <Route path="/uc1/learn" element={<Uc1LearnPage />} />
        <Route path="/uc1/decks" element={<Uc1DecksPage />} />
        <Route path="/uc1/present/:deckId" element={<Uc1PresentPage />} />
        <Route path="/podcast" element={<PodcastPage />} />
        <Route path="/podcast/library" element={<PodcastLibraryPage />} />
        <Route path="/video" element={<StaticVideoPage />} />
        <Route path="/video/library" element={<StaticVideoLibraryPage />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
