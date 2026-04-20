import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { apiService } from '@/api/apiService';
import { useAuth } from '@/context/AuthContext';

interface UserProfile {
  id: string;
  name: string;
  avatar?: string;
  preferences: string[];
}

interface UserContextType {
  userProfile: UserProfile;
  updateName: (name: string) => void;
  updateAvatar: (avatar: string) => void;
  addPreference: (preference: string) => void;
  removePreference: (preference: string) => void;
  clearPreferences: () => void;
  extractPreferencesFromText: (text: string) => string[];
}

const defaultUserProfile: UserProfile = {
  id: '',
  name: 'User',
  preferences: [],
};

const UserContext = createContext<UserContextType | undefined>(undefined);

// Common keywords that might indicate preferences
const PREFERENCE_KEYWORDS = [
  'like', 'love', 'enjoy', 'prefer', 'favorite', 'interested in',
  'passionate about', 'hate', 'dislike', 'don\'t like'
];

// Create a new profile with a unique ID
const createNewProfile = (): UserProfile => {
  return {
    ...defaultUserProfile,
    id: uuidv4(),
  };
};

export const UserProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { ready, token } = useAuth();
  const [userProfile, setUserProfile] = useState<UserProfile>(() => {
    // Try to load from localStorage
    const savedProfile = localStorage.getItem('userProfile');
    if (savedProfile) {
      try {
        return JSON.parse(savedProfile);
      } catch (e) {
        console.error('Failed to parse user profile from localStorage:', e);
      }
    }

    // If no saved profile or parsing failed, create a new one
    return createNewProfile();
  });

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;

    (async () => {
      const defaults = await apiService.getChatDefaults();
      const defaultUserId =
        (defaults?.user_id || import.meta.env.VITE_DEFAULT_USER_ID || '').trim();
      if (!defaultUserId || cancelled) return;

      setUserProfile(prev => {
        const currentName = (prev.name || '').trim();
        const shouldUseServerDefault =
          !currentName ||
          currentName === defaultUserProfile.name;

        if (!shouldUseServerDefault || currentName === defaultUserId) {
          return prev;
        }

        return {
          ...prev,
          name: defaultUserId,
          id: prev.id || uuidv4(),
        };
      });
    })();

    return () => {
      cancelled = true;
    };
  }, [ready, token]);

  // Save to localStorage whenever profile changes
  useEffect(() => {
    localStorage.setItem('userProfile', JSON.stringify(userProfile));
  }, [userProfile]);

  const updateName = (name: string) => {
    setUserProfile(prev => ({ ...prev, name }));
  };

  const updateAvatar = (avatar: string) => {
    setUserProfile(prev => ({ ...prev, avatar }));
  };

  const addPreference = (preference: string) => {
    // Don't add empty preferences or duplicates
    if (!preference.trim() || userProfile.preferences.includes(preference.trim())) {
      return;
    }

    setUserProfile(prev => ({
      ...prev,
      preferences: [...prev.preferences, preference.trim()]
    }));
  };

  const removePreference = (preference: string) => {
    setUserProfile(prev => ({
      ...prev,
      preferences: prev.preferences.filter(p => p !== preference)
    }));
  };

  const clearPreferences = () => {
    setUserProfile(prev => ({ ...prev, preferences: [] }));
  };

  // Extract potential preferences from text
  const extractPreferencesFromText = (text: string): string[] => {
    const foundPreferences: string[] = [];

    // Check for preference keywords
    PREFERENCE_KEYWORDS.forEach(keyword => {
      const regex = new RegExp(`${keyword}\\s+([\\w\\s]+?)(?:\\.|,|;|:|!|\\?|$)`, 'gi');
      let match;

      while ((match = regex.exec(text)) !== null) {
        if (match[1] && match[1].trim()) {
          const preference = match[1].trim();
          // Only add if not already in preferences and not already found
          if (!userProfile.preferences.includes(preference) && !foundPreferences.includes(preference)) {
            foundPreferences.push(preference);
          }
        }
      }
    });

    return foundPreferences;
  };

  return (
    <UserContext.Provider
      value={{
        userProfile,
        updateName,
        updateAvatar,
        addPreference,
        removePreference,
        clearPreferences,
        extractPreferencesFromText
      }}
    >
      {children}
    </UserContext.Provider>
  );
};

export const useUser = (): UserContextType => {
  const context = useContext(UserContext);
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};

export default UserContext;
