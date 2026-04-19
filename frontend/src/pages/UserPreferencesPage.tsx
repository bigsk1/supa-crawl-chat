import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import UserPreferences from '../components/UserPreferences';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from 'react-hot-toast';
import { useUser } from '@/context/UserContext';
import { PageHeader } from '@/components/PageHeader';

const UserPreferencesPage: React.FC = () => {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const { userProfile } = useUser();
  const [currentUserId, setCurrentUserId] = useState<string>(userId || userProfile.name || '');
  const [sessionId, setSessionId] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);

  // Get the session ID from local storage if available
  useEffect(() => {
    const storedSessionId = localStorage.getItem('chatSessionId');
    if (storedSessionId) {
      setSessionId(storedSessionId);
    }
    
    // If no userId is provided but we have a user profile name, navigate to that user's preferences
    if (!userId && userProfile.name && userProfile.name.trim() !== '') {
      navigate(`/preferences/${userProfile.name}`);
    }
  }, [userId, userProfile.name, navigate]);

  // Update currentUserId when userId changes
  useEffect(() => {
    if (userId) {
      setCurrentUserId(userId);
    }
  }, [userId]);

  const handleUserIdChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setCurrentUserId(e.target.value);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentUserId.trim()) {
      toast.error('Please enter a user ID');
      return;
    }
    
    setIsLoading(true);
    
    // Navigate to the preferences page for the entered user ID
    navigate(`/preferences/${currentUserId}`);
    
    // Reset loading state after navigation
    setTimeout(() => setIsLoading(false), 500);
  };

  const handlePreferenceChange = () => {
    // This function will be called when preferences are changed
    toast.success('Preferences updated');
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <PageHeader
        title="User preferences"
        subtitle="Manage long-term memory used by chat (API: GET /api/chat/preferences)"
        backTo="/"
      />
      
      {!userId && (
        <Card className="mb-6 p-6 border border-gray-700 bg-gray-800">
          <form onSubmit={handleSubmit} className="flex flex-col md:flex-row gap-4">
            <div className="flex-grow">
              <label htmlFor="userId" className="block mb-2 font-medium text-gray-200">
                User ID
              </label>
              <Input
                id="userId"
                type="text"
                value={currentUserId}
                onChange={handleUserIdChange}
                placeholder="Enter your display name or user ID"
                className="w-full bg-gray-700 border-gray-600 text-gray-200"
                required
              />
              <p className="text-sm text-gray-400 mt-2">
                This should match your display name in your profile settings.
              </p>
            </div>
            <div className="flex items-end">
              <Button 
                type="submit" 
                disabled={isLoading || !currentUserId.trim()}
                className="px-6 bg-blue-600 hover:bg-blue-700 text-white"
                size="lg"
              >
                {isLoading ? 'Loading...' : 'Load Preferences'}
              </Button>
            </div>
          </form>
        </Card>
      )}

      {userId ? (
        <UserPreferences 
          userId={userId} 
          sessionId={sessionId}
          onPreferenceChange={handlePreferenceChange}
        />
      ) : (
        <Card className="p-8 text-center border border-gray-700 bg-gray-800">
          <p className="text-lg mb-4 text-gray-200">Enter your display name to view and manage preferences.</p>
          <p className="text-sm text-gray-400 mb-4">
            Preferences are tied to your user ID and persist across chat sessions.
          </p>
          <p className="text-sm text-gray-400">
            Your preferences help the AI understand your interests, expertise, and preferences
            to provide more personalized responses.
          </p>
        </Card>
      )}
    </div>
  );
};

export default UserPreferencesPage; 