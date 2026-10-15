import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import LivePage from './pages/LivePage';
import PodcastPage from './pages/PodcastPage';
import PodcastLibraryPage from './pages/PodcastLibraryPage';
import VideoPage from './pages/VideoPage';
import VideoLibraryPage from './pages/VideoLibraryPage';
import HomePage from './pages/HomePage';
import SearchPage from './pages/SearchPage';
import DecksPage from './pages/DecksPage';
import DeckPresentPage from './pages/DeckPresentPage';
import PlaylistsPage from './pages/PlaylistsPage';
import PlaylistPlayerPage from './pages/PlaylistPlayerPage';
import TopNav from './components/TopNav';
import AuthToast from './components/AuthToast';
import ErrorBoundary from './components/ErrorBoundary';
import { AuthProvider, installAuthErrorInterceptor } from './services/auth';
import './styles/index.css';

installAuthErrorInterceptor();

function RoutedContent({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  return <ErrorBoundary resetKey={pathname}>{children}</ErrorBoundary>;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthProvider>
    <BrowserRouter>
      <TopNav />
      <AuthToast />
      <RoutedContent>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/live" element={<LivePage />} />
        <Route path="/decks" element={<DecksPage />} />
        <Route path="/decks/:deckId/present" element={<DeckPresentPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/playlists" element={<PlaylistsPage />} />
        <Route path="/playlists/:playlistId" element={<PlaylistPlayerPage />} />
        <Route path="/podcast" element={<PodcastPage />} />
        <Route path="/podcast/library" element={<PodcastLibraryPage />} />
        <Route path="/video" element={<VideoPage />} />
        <Route path="/video/library" element={<VideoLibraryPage />} />
      </Routes>
      </RoutedContent>
    </BrowserRouter>
    </AuthProvider>
  </React.StrictMode>
);
