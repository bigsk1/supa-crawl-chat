import React, { useEffect } from 'react';
import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import ChatPage from './pages/ChatPage';
import CrawlPage from './pages/CrawlPage';
import SearchPage from './pages/SearchPage';
import SitesPage from './pages/SitesPage';
import SiteDetailPage from './pages/SiteDetailPage';
import NotFoundPage from './pages/NotFoundPage';
import NotificationInfo from './pages/NotificationInfo';
import UserPreferencesPage from './pages/UserPreferencesPage';
import UserGuidePage from './pages/UserGuidePage';
import LoginPage from './pages/LoginPage';
import { useTheme } from './context/ThemeContext';
import { useAuth } from './context/AuthContext';

function AuthGate() {
  const { ready, needsLogin, token } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }
  if (!needsLogin && location.pathname === '/login') {
    return <Navigate to="/" replace />;
  }
  if (needsLogin && token && location.pathname === '/login') {
    return <Navigate to="/" replace />;
  }
  if (needsLogin && !token && location.pathname !== '/login') {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <Outlet />;
}

// Custom toast container that respects the current theme
const ToastContainer = () => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  
  return (
    <Toaster
      position="top-right"
      toastOptions={{
        duration: 4000,
        className: `toast-notification ${isDark ? 'dark' : 'light'}`,
        style: {}, // Remove inline styles to use CSS classes
        success: {
          iconTheme: {
            primary: isDark ? '#10b981' : '#059669',
            secondary: isDark ? '#ecfdf5' : '#ffffff',
          },
          className: 'toast-notification toast-success',
        },
        error: {
          iconTheme: {
            primary: isDark ? '#ef4444' : '#dc2626',
            secondary: isDark ? '#fef2f2' : '#ffffff',
          },
          className: 'toast-notification toast-error',
        },
      }}
    />
  );
};

function App() {
  // Add a flag to disable automatic API calls in development mode
  const isDevelopment = process.env.NODE_ENV === 'development';
  const { theme } = useTheme();
  
  // Log once on initial render to help with debugging
  useEffect(() => {
    if (isDevelopment) {
      console.log('App running in development mode - some background API calls may occur due to hot reloading');
    }
    
    // Add theme class to body
    document.body.classList.toggle('theme-dark', theme === 'dark');
    document.body.classList.toggle('theme-light', theme === 'light');
    
    return () => {
      document.body.classList.remove('theme-dark', 'theme-light');
    };
  }, [isDevelopment, theme]);

  return (
    <>
      <Routes>
        <Route element={<AuthGate />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<Layout />}>
            <Route index element={<HomePage />} />
            <Route path="chat" element={<ChatPage />} />
            <Route path="crawl" element={<CrawlPage />} />
            <Route path="search" element={<SearchPage />} />
            <Route path="sites" element={<SitesPage />} />
            <Route path="sites/:siteId" element={<SiteDetailPage />} />
            <Route path="notifications" element={<NotificationInfo />} />
            <Route path="preferences" element={<UserPreferencesPage />} />
            <Route path="preferences/:userId" element={<UserPreferencesPage />} />
            <Route path="guide" element={<UserGuidePage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Routes>
      <ToastContainer />
    </>
  );
}

export default App; 