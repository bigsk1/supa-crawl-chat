import React, { useState, useEffect, useRef, useCallback } from 'react';
import toast from 'react-hot-toast';
import { ChatMessage, Profile } from '@/api/apiService';
import { api } from '@/api/apiWrapper';
import { v4 as uuidv4 } from 'uuid';
import { useUser } from '@/context/UserContext';
import remarkGfm from 'remark-gfm';
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
import ReactMarkdown from 'react-markdown';

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

  // Initialize sessions and session ID when component mounts
  useEffect(() => {
    // Load saved sessions from localStorage
    const storedSessions = localStorage.getItem('chat_sessions');
    const parsedSessions = storedSessions ? JSON.parse(storedSessions) : [];
    setSessions(parsedSessions);
    
    // Get current session ID from localStorage or create a new one
    const storedSessionId = localStorage.getItem('current_session_id');
    const storedChatInitialized = localStorage.getItem('chat_initialized') === 'true';
    
    if (storedSessionId && parsedSessions.some((s: ChatSession) => s.id === storedSessionId)) {
      // Use existing session
      setSessionId(storedSessionId);
      setChatInitialized(storedChatInitialized);
      
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
      localStorage.setItem('chat_sessions', JSON.stringify(sessions));
    }
  }, [sessions]);

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
    localStorage.setItem('current_session_id', newSession.id);
    localStorage.setItem('chat_initialized', 'false');
    
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
    
    setSessionId(id);
    setChatHistory([]);
    setIsLoading(true);
    
    // Check if this session has been initialized
    const session = sessions.find(s => s.id === id);
    if (session) {
      updateSessionActivity(id);
      localStorage.setItem('current_session_id', id);
      
      // Load chat history for this session
      api.getChatHistory(id)
        .then(history => {
          setChatHistory(history);
          setChatInitialized(history.length > 0);
          localStorage.setItem('chat_initialized', history.length > 0 ? 'true' : 'false');
        })
        .catch(error => {
          console.error('Error loading session history:', error);
          setChatInitialized(false);
          localStorage.setItem('chat_initialized', 'false');
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
            setChatHistory(history);
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

  // Scroll to bottom when chat history changes
  useEffect(() => {
    scrollToBottom();
  }, [chatHistory]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSendMessage = async () => {
    if (!message.trim()) return;
    
    // Check if this is a simple greeting
    const greeting_patterns = [
      "hi", "hello", "hey", "greetings", "howdy", "hola", 
      "how are you", "how's it going", "what's up", "sup", 
      "good morning", "good afternoon", "good evening"
    ];
    
    const clean_message = message.trim().toLowerCase();
    const is_greeting = greeting_patterns.some(greeting => clean_message.includes(greeting));
    
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
    
    try {
      // Send message to API
      const response = await api.sendMessage(
        message,
        activeProfile?.name || undefined,
        sessionId || undefined,
        userProfile?.name
      );
      
      // Add assistant response to chat history
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.response,
        created_at: new Date().toISOString()
      };
      
      setChatHistory(prev => [...prev, assistantMessage]);
      
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
      localStorage.setItem('chat_initialized', 'false');
      
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
      message.content.includes("===== ")
    ))
  );

  // Render system messages with context differently
  const renderMessage = (message: Message) => {
    if (message.role === 'system' && message.content) {
      // Check if this is a search results message
      const isSearchResults = 
        message.content.includes("DATABASE SEARCH RESULTS") || 
        message.content.includes("RELEVANT INFORMATION") ||
        message.content.includes("EXACT KEYWORD MATCHES") ||
        message.content.includes("VERIFIED DATABASE SEARCH RESULTS") ||
        message.content.includes("RELEVANT URLS") ||
        message.content.includes("===== ");
      
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
          <div className="prose dark:prose-invert prose-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
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
        setChatHistory(history);
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
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-2xl font-bold">Chat</h1>
          <div className="flex space-x-2">
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
            {filteredChatHistory.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <Bot className="mx-auto h-12 w-12 text-muted-foreground" />
                  <h3 className="mt-2 text-lg font-medium">Start a conversation</h3>
                  <p className="text-sm text-muted-foreground">
                    Ask questions about your crawled sites or any topic you'd like to discuss
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
            <div ref={messagesEndRef} />
          </div>

          <div className="border-t border-white/[0.05] p-4">
            <form onSubmit={handleSendMessage} className="flex space-x-2">
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