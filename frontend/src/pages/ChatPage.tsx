import React, { useState, useEffect, useRef, useCallback } from 'react';
import toast from 'react-hot-toast';
import { ChatMessage, Profile } from '@/api/apiService';
import { api, isSimpleGreetingMessage } from '@/api/apiWrapper';
import { v4 as uuidv4 } from 'uuid';
import { useUser } from '@/context/UserContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { MessageSquare, Plus, Trash2, Edit, RefreshCw, Bot, Send, Copy, Check } from 'lucide-react';
import { createNotification } from '@/utils/notifications';
import { PageHeader } from '@/components/PageHeader';
import { MarkdownContent } from '@/components/MarkdownContent';
import { apiService } from '@/api/apiService';
import { Link } from 'react-router-dom';

// Define the session interface
interface ChatSession {
  id: string;
  name: string;
  createdAt: string;
  lastActivity: string;
}

// Update the ChatMessage interface to include context
interface Message extends ChatMessage {
  context?: string;
}

const CHAT_SESSIONS_KEY = 'chat_sessions';
const CURRENT_SESSION_ID_KEY = 'current_session_id';
const CHAT_INITIALIZED_KEY = 'chat_initialized';
const CHAT_HISTORY_CACHE_PREFIX = 'chat_history_cache:';

const chatInitializedKey = (sessionId: string) => `${CHAT_INITIALIZED_KEY}:${sessionId}`;
const chatHistoryCacheKey = (sessionId: string) => `${CHAT_HISTORY_CACHE_PREFIX}${sessionId}`;

const safeParseJson = <T,>(raw: string | null, fallback: T): T => {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
};

const loadCachedChatHistory = (sessionId: string): Message[] => {
  const cached = safeParseJson<{ messages?: Message[] } | Message[]>(
    localStorage.getItem(chatHistoryCacheKey(sessionId)),
    []
  );

  if (Array.isArray(cached)) {
    return cached;
  }

  return Array.isArray(cached.messages) ? cached.messages : [];
};

const saveCachedChatHistory = (sessionId: string, messages: Message[]) => {
  if (!messages.length) {
    localStorage.removeItem(chatHistoryCacheKey(sessionId));
    return;
  }

  localStorage.setItem(
    chatHistoryCacheKey(sessionId),
    JSON.stringify({
      version: 1,
      savedAt: new Date().toISOString(),
      messages,
    })
  );
};

const removeCachedChatHistory = (sessionId: string) => {
  localStorage.removeItem(chatHistoryCacheKey(sessionId));
};

const getStoredChatInitialized = (sessionId: string): boolean => {
  return (
    localStorage.getItem(chatInitializedKey(sessionId)) === 'true' ||
    localStorage.getItem(CHAT_INITIALIZED_KEY) === 'true'
  );
};

const setStoredChatInitialized = (sessionId: string, initialized: boolean) => {
  const value = initialized ? 'true' : 'false';
  localStorage.setItem(chatInitializedKey(sessionId), value);
  localStorage.setItem(CHAT_INITIALIZED_KEY, value);
};

const ChatPage = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [activeProfile, setActiveProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { userProfile } = useUser();
  const [chatHistory, setChatHistory] = useState<Message[]>([]);
  const [isLoadingProfiles, setIsLoadingProfiles] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [chatInitialized, setChatInitialized] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [showSessionManager, setShowSessionManager] = useState(false);
  const [newSessionName, setNewSessionName] = useState('');
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const { extractPreferencesFromText, addPreference } = useUser();
  const [preferenceCount, setPreferenceCount] = useState<number | null>(null);

  // Initialize sessions and session ID when component mounts
  useEffect(() => {
    // Load saved sessions from localStorage
    const parsedSessions = safeParseJson<ChatSession[]>(
      localStorage.getItem(CHAT_SESSIONS_KEY),
      []
    );
    setSessions(parsedSessions);

    // Get current session ID from localStorage or create a new one
    const storedSessionId = localStorage.getItem(CURRENT_SESSION_ID_KEY);

    if (storedSessionId && parsedSessions.some((s: ChatSession) => s.id === storedSessionId)) {
      // Use existing session
      const cachedHistory = loadCachedChatHistory(storedSessionId);
      if (cachedHistory.length) {
        setChatHistory(cachedHistory);
      }

      setSessionId(storedSessionId);
      setChatInitialized(getStoredChatInitialized(storedSessionId) || cachedHistory.length > 0);

      // Update last activity
      updateSessionActivity(storedSessionId);
    } else {
      // Create a new session
      createNewSession('Default Session');
    }
  }, []); // Empty dependency array - run only once on mount

  // Save sessions to localStorage whenever they change
  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem(CHAT_SESSIONS_KEY, JSON.stringify(sessions));
    }
  }, [sessions]);

  // Persist the current visible chat so it survives route changes immediately.
  useEffect(() => {
    if (!sessionId) return;
    saveCachedChatHistory(sessionId, chatHistory);
  }, [sessionId, chatHistory]);

  // Create a new session
  const createNewSession = (name: string) => {
    const newSession: ChatSession = {
      id: uuidv4(),
      name: name || `Session ${sessions.length + 1}`,
      createdAt: new Date().toISOString(),
      lastActivity: new Date().toISOString()
    };
    
    setSessions(prev => [...prev, newSession]);
    setSessionId(newSession.id);
    setChatInitialized(false);
    setChatHistory([]);
    localStorage.setItem(CURRENT_SESSION_ID_KEY, newSession.id);
    setStoredChatInitialized(newSession.id, false);
    removeCachedChatHistory(newSession.id);
    
    return newSession.id;
  };

  // Update session activity timestamp
  const updateSessionActivity = (id: string) => {
    setSessions(prev => 
      prev.map(session => 
        session.id === id 
          ? { ...session, lastActivity: new Date().toISOString() } 
          : session
      )
    );
  };

  // Switch to a different session
  const switchSession = (id: string) => {
    if (id === sessionId) return; // Already on this session

    const cachedHistory = loadCachedChatHistory(id);
    setSessionId(id);
    setChatHistory(cachedHistory);
    setChatInitialized(getStoredChatInitialized(id) || cachedHistory.length > 0);
    setIsLoading(true);

    // Check if this session has been initialized
    const session = sessions.find(s => s.id === id);
    if (session) {
      updateSessionActivity(id);
      localStorage.setItem(CURRENT_SESSION_ID_KEY, id);

      // Load chat history for this session
      api.getChatHistory(id)
        .then(history => {
          if (history.length > 0) {
            setChatHistory(history);
            setChatInitialized(true);
            setStoredChatInitialized(id, true);
          } else if (!cachedHistory.length) {
            setChatInitialized(false);
            setStoredChatInitialized(id, false);
          }
        })
        .catch(error => {
          console.error('Error loading session history:', error);
          if (!cachedHistory.length) {
            setChatInitialized(false);
            setStoredChatInitialized(id, false);
          }
        })
        .finally(() => {
          setIsLoading(false);
        });
    }
  };

  // Rename a session
  const renameSession = (id: string, newName: string) => {
    if (!newName.trim()) return;
    
    setSessions(prev => 
      prev.map(session => 
        session.id === id 
          ? { ...session, name: newName.trim() } 
          : session
      )
    );
    setEditingSessionId(null);
  };

  // Delete a session
  const deleteSession = async (id: string) => {
    if (sessions.length === 1) {
      toast.error('Cannot delete the only session');
      return;
    }
    
    if (window.confirm('Are you sure you want to delete this session? This will clear all chat history for this session.')) {
      try {
        // Clear chat history on the server
        await api.clearChatHistory(id);
        
        // Remove from local state
        setSessions(prev => prev.filter(session => session.id !== id));
        
        // If we're deleting the current session, switch to another one
        if (id === sessionId) {
          const remainingSessions = sessions.filter(session => session.id !== id);
          if (remainingSessions.length > 0) {
            switchSession(remainingSessions[0].id);
          } else {
            createNewSession('Default Session');
          }
        }
        
        createNotification('Success', 'Session deleted', 'success', true);
      } catch (error) {
        console.error('Error deleting session:', error);
        toast.error('Failed to delete session');
      }
    }
  };

  useEffect(() => {
    if (!userProfile?.name?.trim()) {
      setPreferenceCount(null);
      return;
    }
    let cancelled = false;
    apiService
      .getUserPreferences(userProfile.name.trim(), 0.7, true)
      .then((prefs) => {
        if (!cancelled) setPreferenceCount(prefs.length);
      })
      .catch(() => {
        if (!cancelled) setPreferenceCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [userProfile?.name]);

  // Load profiles and chat history only once when sessionId is available
  useEffect(() => {
    // Only run this effect if sessionId is available and not empty
    if (sessionId && !isLoadingProfiles) {
      // Load profiles first
      const fetchProfiles = async () => {
        setIsLoadingProfiles(true);
        try {
          const profilesData = await api.getProfiles();
          if (Array.isArray(profilesData)) {
            setProfiles(profilesData);
            if (profilesData.length > 0 && !activeProfile) {
              setActiveProfile(profilesData[0]);
            }
          }
        } catch (error) {
          console.error('Error loading profiles:', error);
          toast.error('Failed to load profiles');
        } finally {
          setIsLoadingProfiles(false);
        }
      };

      // Load chat history if chat is initialized
      const fetchChatHistory = async () => {
        if (chatInitialized && !isLoadingHistory) {
          setIsLoadingHistory(true);
          try {
            const history = await api.getChatHistory(sessionId);
            if (history.length > 0) {
              setChatHistory(history);
              setStoredChatInitialized(sessionId, true);
            } else if (!loadCachedChatHistory(sessionId).length) {
              setChatInitialized(false);
              setStoredChatInitialized(sessionId, false);
            }
            // Update session activity
            updateSessionActivity(sessionId);
          } catch (error) {
            console.error('Error loading chat history:', error);
          } finally {
            setIsLoadingHistory(false);
          }
        }
      };

      // Execute the fetch functions
      fetchProfiles();
      if (chatInitialized) {
        fetchChatHistory();
      }
    }
  }, [sessionId, chatInitialized, activeProfile]); // Remove isLoadingProfiles and isLoadingHistory from dependencies

  // Scroll to bottom when chat history changes or when waiting for the assistant
  useEffect(() => {
    scrollToBottom();
  }, [chatHistory, isLoading]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSendMessage = async () => {
    if (!message.trim()) return;
    
    const is_greeting = isSimpleGreetingMessage(message);
    
    setIsLoading(true);
    
    // Add user message to chat history
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: message,
      created_at: new Date().toISOString()
    };
    
    setChatHistory(prev => [...prev, userMessage]);
    setMessage('');
    if (sessionId) {
      setChatInitialized(true);
      setStoredChatInitialized(sessionId, true);
      updateSessionActivity(sessionId);
    }
    
    try {
      // Send message to API
      // Order must match apiWrapper: (message, profile?, user_id?, session_id?)
      const response = await api.sendMessage(
        message,
        activeProfile?.name || undefined,
        userProfile?.name || undefined,
        sessionId || undefined
      );
      
      // Add assistant response to chat history
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.response,
        created_at: new Date().toISOString()
      };
      
      setChatHistory(prev => [...prev, assistantMessage]);
      if (sessionId) {
        setChatInitialized(true);
        setStoredChatInitialized(sessionId, true);
        updateSessionActivity(sessionId);
      }

      // Show Brave web retrieval in UI (API returns brave_preview; LLM also received this as inject)
      const rw = response as {
        brave_used?: boolean;
        brave_preview?: string;
        brave_sources?: { url?: string; title?: string }[];
      };
      if (
        rw.brave_used &&
        (rw.brave_preview?.trim() ||
          (Array.isArray(rw.brave_sources) && rw.brave_sources.length > 0))
      ) {
        let braveText =
          '===== BRAVE WEB CONTEXT (Brave Search LLM API) =====\n\n';
        if (rw.brave_preview?.trim()) {
          braveText += rw.brave_preview;
        } else if (rw.brave_sources?.length) {
          braveText += rw.brave_sources
            .map(
              (s) =>
                `TITLE: ${s.title || 'Untitled'}\nURL: ${s.url || ''}\n`
            )
            .join('\n');
        }
        const braveMessage: Message = {
          id: (Date.now() + 3).toString(),
          role: 'system',
          content: braveText,
          created_at: new Date().toISOString(),
        };
        setChatHistory((prev) => [...prev, braveMessage]);
      }

      if (userProfile?.name?.trim()) {
        apiService
          .getUserPreferences(userProfile.name.trim(), 0.7, true)
          .then((prefs) => setPreferenceCount(prefs.length))
          .catch(() => {});
      }

      // If there's context in the response and it's not a greeting, add it as a system message
      if (!is_greeting && response.context && Array.isArray(response.context) && response.context.length > 0) {
        // The context is already formatted in the apiWrapper
        // Just check if it's in the conversation_history
        if (!response.conversation_history) {
          // If not in conversation_history, create a system message
          const contextMessage: Message = {
            id: (Date.now() + 2).toString(),
            role: 'system',
            content: "===== INFORMATION FROM YOUR CRAWLED SITES =====\n\n" + 
              response.context.map((item: any) => 
                `SOURCE: ${item.site_name || 'Unknown'}\n` +
                `TITLE: ${item.title || 'Untitled'}\n` +
                `URL: ${item.url || ''}\n` +
                `${item.summary ? `SUMMARY: ${item.summary}\n\n` : 
                  item.content ? `CONTENT: ${item.content.substring(0, 300)}...\n\n` : '\n'}`
              ).join(''),
            created_at: new Date().toISOString()
          };
          
          setChatHistory(prev => [...prev, contextMessage]);
        }
      }
      
      // Scroll to bottom after response is added
      setTimeout(() => {
        if (chatContainerRef.current) {
          chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
        }
      }, 100);
      
    } catch (error) {
      console.error('Error sending message:', error);
      toast.error('Failed to send message. Please try again.');
      
      // Add error message to chat
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'system',
        content: 'Failed to send message. Please try again.',
        created_at: new Date().toISOString()
      };
      
      setChatHistory(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // Function to clear chat history
  const handleClearChat = async () => {
    if (!sessionId) return;
    
    try {
      setIsLoading(true);
      await api.clearChatHistory(sessionId);
      setChatHistory([]);
      setChatInitialized(false);
      setStoredChatInitialized(sessionId, false);
      removeCachedChatHistory(sessionId);
      createNotification('Success', 'Chat history cleared', 'success', true);
    } catch (error) {
      console.error('Error clearing chat history:', error);
      setError('Failed to clear chat history');
      toast.error('Failed to clear chat history');
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewChat = () => {
    if (window.confirm('Start a new chat? This will keep your current session but clear the current conversation.')) {
      setChatHistory([]);
      setChatInitialized(false);
      if (sessionId) {
        setStoredChatInitialized(sessionId, false);
        removeCachedChatHistory(sessionId);
      }
      
      // Update session activity
      if (sessionId) {
        updateSessionActivity(sessionId);
      }
      
      createNotification('Success', 'Started new chat', 'success', true);
    }
  };

  const handleProfileChange = async (profileId: string) => {
    if (!sessionId) {
      toast.error('No session ID available');
      return;
    }
    
    setActiveProfile(profiles.find(p => p.name === profileId) || null);
    setError(null);
    
    // Optionally set the profile in the backend
    try {
      await api.setProfile(
        profileId, 
        sessionId,
        userProfile?.name // Pass the user's name as the user_id
      );
      createNotification('Success', 'Profile updated', 'success', true);
    } catch (error) {
      console.error('Error setting profile:', error);
      setError('Failed to update profile. Please try again.');
      toast.error('Failed to update profile');
    }
  };

  const formatTimestamp = (timestamp: string | undefined): string => {
    try {
      // Check if timestamp is valid
      if (!timestamp || timestamp === 'undefined' || timestamp === 'null') {
        return 'Just now';
      }
      
      const date = new Date(timestamp);
      
      // Check if date is valid
      if (isNaN(date.getTime())) {
        return 'Just now';
      }
      
      // Format the date
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (error) {
      console.error('Error formatting timestamp:', error);
      return 'Just now';
    }
  };

  // Filter chat history to show system messages with context
  const filteredChatHistory = chatHistory.filter(message => 
    message.role !== 'system' || 
    (message.content && (
      message.content.includes("DATABASE SEARCH RESULTS") || 
      message.content.includes("RELEVANT INFORMATION") ||
      message.content.includes("EXACT KEYWORD MATCHES") ||
      message.content.includes("VERIFIED DATABASE SEARCH RESULTS") ||
      message.content.includes("RELEVANT URLS") ||
      message.content.includes("===== BRAVE WEB") ||
      message.content.includes("===== ")
    ))
  );

  // Render system messages with context differently
  const renderMessage = (message: Message) => {
    if (message.role === 'system' && message.content) {
      const isBraveWeb = message.content.includes("===== BRAVE WEB");
      // Check if this is a search results message
      const isSearchResults = 
        message.content.includes("DATABASE SEARCH RESULTS") || 
        message.content.includes("RELEVANT INFORMATION") ||
        message.content.includes("EXACT KEYWORD MATCHES") ||
        message.content.includes("VERIFIED DATABASE SEARCH RESULTS") ||
        message.content.includes("RELEVANT URLS") ||
        message.content.includes("===== ");

      if (isBraveWeb) {
        const urlMatch = message.content.match(/https?:\/\/[^\s)]+/);
        const mainUrl = urlMatch ? urlMatch[0] : '';
        return (
          <div className="mb-4 px-4">
            <details className="bg-blue-950/20 border border-blue-500/30 rounded-lg p-2">
              <summary className="cursor-pointer font-medium text-sm text-blue-200 flex items-center">
                <MessageSquare className="inline-block mr-2 h-4 w-4" />
                <span>Brave Search — web context</span>
                {mainUrl && (
                  <span className="ml-2 text-xs opacity-80 truncate max-w-[200px]">
                    {mainUrl}
                  </span>
                )}
                <span className="ml-2 text-xs opacity-70">(expand)</span>
              </summary>
              <div className="mt-2 text-xs whitespace-pre-wrap overflow-auto max-h-96 p-2">
                {message.content}
              </div>
            </details>
          </div>
        );
      }
      
      if (isSearchResults) {
        // Extract the first URL from the message to highlight as the main source
        let mainUrl = "";
        let mainTitle = "";
        const urlMatch = message.content.match(/URL: (https?:\/\/[^\s]+)/);
        if (urlMatch && urlMatch[1]) {
          mainUrl = urlMatch[1];
          
          // Try to find the title for this URL
          const titleRegex = new RegExp(`TITLE: ([^\\n]+)(?:\\n|\\r\\n)URL: ${mainUrl.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`);
          const titleMatch = message.content.match(titleRegex);
          if (titleMatch && titleMatch[1]) {
            mainTitle = titleMatch[1];
          }
        }
        
        // Render system message with context in a collapsible panel
        return (
          <div className="mb-4 px-4">
            <details className="bg-muted/50 rounded-lg p-2">
              <summary className="cursor-pointer font-medium text-sm text-muted-foreground flex items-center">
                <MessageSquare className="inline-block mr-2 h-4 w-4" />
                <span>Information from Crawled Sites</span>
                {mainUrl && (
                  <span className="ml-2 text-xs opacity-70">
                    (Main source: {mainTitle || mainUrl})
                  </span>
                )}
                <span className="ml-2 text-xs opacity-70">(Click to expand)</span>
              </summary>
              <div className="mt-2 text-xs whitespace-pre-wrap overflow-auto max-h-96 p-2">
                {message.content}
              </div>
            </details>
          </div>
        );
      }
    }
    
    // Regular user or assistant message
    return (
      <div className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
        {message.role !== 'user' && (
          <Avatar className="h-8 w-8">
            <AvatarFallback><Bot size={16} /></AvatarFallback>
          </Avatar>
        )}
        <div className={`rounded-lg p-3 max-w-[80%] ${
          message.role === 'user' 
            ? 'bg-primary text-primary-foreground' 
            : 'bg-muted'
        }`}>
          <MarkdownContent className="prose dark:prose-invert prose-sm max-w-none">
            {message.content}
          </MarkdownContent>
          <div className="text-xs mt-1 opacity-70">
            {formatTimestamp(message.created_at)}
          </div>
        </div>
        {message.role === 'user' && (
          <Avatar className="h-8 w-8">
            {userProfile?.avatar ? (
              <AvatarImage src={userProfile.avatar} alt="User" />
            ) : (
              <AvatarFallback>{userProfile?.name?.[0] || 'U'}</AvatarFallback>
            )}
          </Avatar>
        )}
      </div>
    );
  };

  // Define the refresh functions at the component level
  const refreshProfiles = async () => {
    setIsLoadingProfiles(true);
    try {
      const profilesData = await api.getProfiles();
      if (Array.isArray(profilesData)) {
        setProfiles(profilesData);
        if (profilesData.length > 0 && !activeProfile) {
          setActiveProfile(profilesData[0]);
        }
      }
    } catch (error) {
      console.error('Error loading profiles:', error);
      toast.error('Failed to load profiles');
    } finally {
      setIsLoadingProfiles(false);
    }
  };

  const refreshChatHistory = async () => {
    if (chatInitialized && !isLoadingHistory && sessionId) {
      setIsLoadingHistory(true);
      try {
        const history = await api.getChatHistory(sessionId);
        if (history.length > 0) {
          setChatHistory(history);
          setChatInitialized(true);
          setStoredChatInitialized(sessionId, true);
        } else if (!loadCachedChatHistory(sessionId).length) {
          setChatHistory([]);
          setChatInitialized(false);
          setStoredChatInitialized(sessionId, false);
        }
      } catch (error) {
        console.error('Error loading chat history:', error);
      } finally {
        setIsLoadingHistory(false);
      }
    }
  };

  // Add a function to copy text to clipboard
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
      .then(() => {
        createNotification('Success', 'Session ID copied to clipboard', 'success', true);
      })
      .catch(err => {
        console.error('Failed to copy text: ', err);
        createNotification('Error', 'Failed to copy to clipboard', 'error', true);
      });
  };

  // If there's a critical error, show a recovery UI
  if (error && !chatHistory.length && !profiles.length) {
    return (
      <div className="container mx-auto px-4 py-8">
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive">Something went wrong</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-destructive mb-6">{error}</p>
            <div className="flex justify-center space-x-4">
              <Button 
                onClick={() => window.location.reload()} 
                variant="destructive"
              >
                Refresh Page
              </Button>
              <Button 
                onClick={() => {
                  setError(null);
                  refreshProfiles();
                  refreshChatHistory();
                }} 
                variant="outline"
              >
                Try Again
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Add this useEffect to handle the copy button functionality
  useEffect(() => {
    // Function to handle copy button clicks
    const handleCopyButtonClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (target.classList.contains('code-block-button') || target.closest('.code-block-button')) {
        const button = target.classList.contains('code-block-button') ? target : target.closest('.code-block-button');
        if (!button) return;
        
        const targetId = button.getAttribute('data-clipboard-target');
        if (!targetId) return;
        
        const codeElement = document.getElementById(targetId);
        if (!codeElement) return;
        
        // Copy the text content to clipboard
        navigator.clipboard.writeText(codeElement.textContent || '')
          .then(() => {
            // Change button text temporarily
            const originalText = button.textContent;
            button.textContent = 'Copied!';
            
            // Reset button text after 2 seconds
            setTimeout(() => {
              button.textContent = originalText;
            }, 2000);
            
            createNotification('Success', 'Code copied to clipboard', 'success', true);
          })
          .catch(err => {
            console.error('Failed to copy code: ', err);
            createNotification('Error', 'Failed to copy code', 'error', true);
          });
      }
    };
    
    // Add event listener to the chat container
    const chatContainer = chatContainerRef.current;
    if (chatContainer) {
      chatContainer.addEventListener('click', handleCopyButtonClick);
    }
    
    // Clean up event listener
    return () => {
      if (chatContainer) {
        chatContainer.removeEventListener('click', handleCopyButtonClick);
      }
    };
  }, [chatContainerRef.current]); // Only re-run if the chat container changes

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="flex flex-col h-[calc(100vh-10rem)]">
        <PageHeader title="Chat" subtitle="RAG-aware assistant using your crawled content" backTo="/" />
        <div className="flex items-center justify-end mb-4 -mt-2">
          <div className="flex flex-wrap gap-2 justify-end">
            {/* Session dropdown */}
            <DropdownMenu>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" className="flex items-center gap-2 border-white/[0.05] bg-[#171923] hover:bg-white/[0.06] text-gray-300">
                        <MessageSquare className="h-4 w-4" />
                        <span>{sessions.find(s => s.id === sessionId)?.name || 'Default Session'}</span>
                      </Button>
                    </DropdownMenuTrigger>
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="bg-[#171923] border-white/[0.05] max-w-xs">
                    <div className="flex flex-col">
                      <div className="flex items-center justify-between">
                        <p className="text-xs mb-1">Session ID:</p>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 p-0 hover:bg-white/[0.06] ml-2 transition-none"
                          onClick={() => sessionId && copyToClipboard(sessionId)}
                        >
                          <Copy className="h-3 w-3" />
                        </Button>
                      </div>
                      <code className="text-xs bg-black/30 p-1 rounded font-mono truncate">{sessionId}</code>
                    </div>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <DropdownMenuContent className="w-56 bg-[#171923] border-white/[0.05]">
                <div className="p-2">
                  <div className="mb-2">
                    <Input
                      value={newSessionName}
                      onChange={(e) => setNewSessionName(e.target.value)}
                      placeholder="New session name"
                      className="mb-2 bg-[#0f1117] border-white/[0.05]"
                    />
                    <Button
                      onClick={() => {
                        if (newSessionName.trim()) {
                          createNewSession(newSessionName);
                          setNewSessionName('');
                        }
                      }}
                      className="w-full"
                      size="sm"
                    >
                      <Plus className="h-4 w-4 mr-2" /> Create Session
                    </Button>
                  </div>
                  
                  <Separator className="my-2 bg-white/[0.05]" />
                  
                  <div className="max-h-[300px] overflow-y-auto">
                    {sessions.map(session => (
                      <div key={session.id} className="mb-2 last:mb-0">
                        <div className={`p-2 rounded-md ${
                          session.id === sessionId 
                            ? 'bg-white/[0.08]' 
                            : 'hover:bg-white/[0.06]'
                        }`}>
                          <div className="flex justify-between items-center">
                            <div className="flex-grow">
                              {editingSessionId === session.id ? (
                                <Input
                                  defaultValue={session.name}
                                  autoFocus
                                  onBlur={(e) => renameSession(session.id, e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                      renameSession(session.id, e.currentTarget.value);
                                    } else if (e.key === 'Escape') {
                                      setEditingSessionId(null);
                                    }
                                  }}
                                  className="text-sm bg-[#0f1117] border-white/[0.05]"
                                />
                              ) : (
                                <div>
                                  <div 
                                    className="font-medium cursor-pointer text-gray-200" 
                                    onClick={() => {
                                      switchSession(session.id);
                                    }}
                                  >
                                    {session.name}
                                  </div>
                                  <div className="text-xs text-gray-400 flex items-center gap-1">
                                    <span>{new Date(session.createdAt).toLocaleDateString()}</span>
                                    <TooltipProvider>
                                      <Tooltip>
                                        <TooltipTrigger asChild>
                                          <Button
                                            variant="ghost"
                                            size="icon"
                                            className="h-5 w-5 p-0 hover:bg-white/[0.06] transition-none"
                                            onClick={(e) => {
                                              e.stopPropagation();
                                              copyToClipboard(session.id);
                                            }}
                                          >
                                            <Copy className="h-3 w-3" />
                                          </Button>
                                        </TooltipTrigger>
                                        <TooltipContent side="bottom" className="bg-[#171923] border-white/[0.05] max-w-xs">
                                          <div className="flex flex-col">
                                            <p className="text-xs mb-1">Session ID (click to copy):</p>
                                            <code className="text-xs bg-black/30 p-1 rounded font-mono truncate">{session.id}</code>
                                          </div>
                                        </TooltipContent>
                                      </Tooltip>
                                    </TooltipProvider>
                                  </div>
                                </div>
                              )}
                            </div>
                            
                            <div className="flex gap-1">
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="h-7 w-7 hover:bg-white/[0.06]"
                                      onClick={() => setEditingSessionId(session.id)}
                                    >
                                      <Edit className="h-3.5 w-3.5" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent className="bg-[#171923] border-white/[0.05]">
                                    <p>Rename session</p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                              
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="h-7 w-7 text-destructive hover:bg-white/[0.06]"
                                      onClick={() => deleteSession(session.id)}
                                    >
                                      <Trash2 className="h-3.5 w-3.5" />
                                    </Button>
                                  </TooltipTrigger>
                                  <TooltipContent className="bg-[#171923] border-white/[0.05]">
                                    <p>Delete session</p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </DropdownMenuContent>
            </DropdownMenu>
            
            <div>
              <Select
                value={activeProfile?.name}
                onValueChange={handleProfileChange}
                disabled={isLoading}
              >
                <SelectTrigger className="w-[180px] border-white/[0.05] bg-[#171923] text-gray-300">
                  <SelectValue placeholder="Select a profile" />
                </SelectTrigger>
                <SelectContent className="bg-[#171923] border-white/[0.05]">
                  {profiles.map((profile) => (
                    <SelectItem key={profile.name} value={profile.name} className="hover:bg-white/[0.06] focus:bg-white/[0.06]">
                      {profile.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {userProfile?.name && preferenceCount !== null && preferenceCount > 0 && (
              <Link
                to={`/preferences/${encodeURIComponent(userProfile.name)}`}
                className="text-xs text-muted-foreground hover:text-foreground whitespace-nowrap self-center px-2 py-1 rounded-md border border-white/[0.08] bg-[#171923]"
              >
                {preferenceCount} saved preference{preferenceCount === 1 ? '' : 's'}
              </Link>
            )}
            
            <Button
              variant="outline"
              onClick={handleNewChat}
              disabled={isLoading}
              className="border-white/[0.05] bg-[#171923] hover:bg-white/[0.06] text-gray-300"
            >
              <Plus className="h-4 w-4 mr-2" /> New Chat
            </Button>
            
            <Button
              variant="outline"
              onClick={handleClearChat}
              disabled={isLoading}
              className="border-white/[0.05] bg-[#171923] hover:bg-white/[0.06] text-gray-300"
            >
              <Trash2 className="h-4 w-4 mr-2" /> Clear Chat
            </Button>
          </div>
        </div>
        
        <div className="flex-1 flex flex-col bg-[#0f1117] rounded-lg border border-white/[0.05] overflow-hidden">
          <div className="flex-1 overflow-y-auto p-4" ref={chatContainerRef}>
            {filteredChatHistory.length === 0 && !isLoading ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <Bot className="mx-auto h-12 w-12 text-muted-foreground" />
                  <h3 className="mt-2 text-lg font-medium">Start a conversation</h3>
                  <p className="text-sm text-muted-foreground">
                    Ask questions about your crawled sites or say hi — your session stays in sync with the server.
                  </p>
                </div>
              </div>
            ) : (
              filteredChatHistory.map((msg) => (
                <div key={msg.id} className="mb-4">
                  {renderMessage(msg)}
                </div>
              ))
            )}
            {isLoading && (
              <div className="flex gap-3 justify-start mb-4" aria-live="polite" aria-busy="true">
                <Avatar className="h-8 w-8">
                  <AvatarFallback>
                    <Bot size={16} />
                  </AvatarFallback>
                </Avatar>
                <div className="rounded-lg p-3 max-w-[80%] bg-muted border border-white/[0.06]">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <RefreshCw className="h-4 w-4 animate-spin shrink-0" />
                    <span>Thinking…</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="border-t border-white/[0.05] p-4">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleSendMessage();
              }}
              className="flex space-x-2"
            >
              <Textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Type your message..."
                className="flex-1 min-h-[60px] max-h-[200px] bg-[#171923] border-white/[0.05] focus-visible:ring-primary"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
              />
              <Button 
                type="submit" 
                disabled={isLoading || message.trim() === ''}
                className="self-end"
              >
                {isLoading ? (
                  <RefreshCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                <span className="sr-only">Send</span>
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPage;
