import { toast } from 'react-hot-toast';

// Notification event bus for components to subscribe to
type NotificationListener = (notification: Notification) => void;
const listeners: NotificationListener[] = [];

// Track last call time for each listener
const listenerLastCalls = new Map<
  NotificationListener, 
  { 
    timestamp: number; 
    notificationId: string;
    notificationType: string;
    notificationTitle: string;
  }
>();

// Mute notifications state
const MUTE_STORAGE_KEY = 'supa-crawl-chat-notifications-muted';
let notificationsMuted = localStorage.getItem(MUTE_STORAGE_KEY) === 'true';

// Functions to get and set mute state
export function isNotificationsMuted(): boolean {
  return notificationsMuted;
}

export function setNotificationsMuted(muted: boolean): void {
  notificationsMuted = muted;
  localStorage.setItem(MUTE_STORAGE_KEY, muted ? 'true' : 'false');
}

export function toggleNotificationsMuted(): boolean {
  const newState = !notificationsMuted;
  setNotificationsMuted(newState);
  return newState;
}

export interface Notification {
  id: string;
  title: string;
  message: string;
  type: 'pending' | 'success' | 'error' | 'info';
  timestamp: number;
  duration?: number;
}

export interface ApiNotificationOptions {
  pendingTitle: string;
  pendingMessage: string;
  successTitle: string;
  successMessage: string;
  errorTitle: string;
  errorMessage?: string;
  showToast?: boolean;
  showNotification?: boolean; // Option to disable notifications completely
}

// Add a listener to be notified of new notifications
export function addNotificationListener(listener: NotificationListener) {
  listeners.push(listener);
  return () => {
    const index = listeners.indexOf(listener);
    if (index > -1) {
      listeners.splice(index, 1);
    }
  };
}

// Function to set the addNotification function from NotificationCenter
let notificationCenterAddFn: ((notification: Notification) => void) | null = null;
export function setNotificationCenter(addFn: (notification: Notification) => void) {
  notificationCenterAddFn = addFn;
}

// Dispatch a notification to all listeners
export function dispatchNotification(notification: Notification) {
  // Check for duplicate notifications in the last 2 seconds
  const now = Date.now();
  const isDuplicate = listeners.some(listener => {
    // Check if this listener has been called with a similar notification recently
    const lastCall = listenerLastCalls.get(listener);
    if (lastCall) {
      const { timestamp, notificationId, notificationType, notificationTitle } = lastCall;
      return (
        now - timestamp < 2000 && 
        notificationType === notification.type && 
        notificationTitle === notification.title
      );
    }
    return false;
  });
  
  if (isDuplicate) {
    return;
  }
  
  // Update last call time for each listener
  listeners.forEach(listener => {
    listenerLastCalls.set(listener, {
      timestamp: now,
      notificationId: notification.id,
      notificationType: notification.type,
      notificationTitle: notification.title
    });
    
    listener(notification);
  });
  
  // Add to notification center if it exists
  if (notificationCenterAddFn) {
    notificationCenterAddFn(notification);
  }

  // Toasts are not shown here — trackApiCall and createNotification already emit toasts when
  // appropriate. Duplicating here caused double popups for the same event.
}

// Track an API call and dispatch notifications for its lifecycle
export async function trackApiCall<T>(
  promise: Promise<T>,
  options: ApiNotificationOptions
): Promise<T> {
  const id = `api-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  
  // Dispatch pending notification if not disabled
  if (options.showNotification !== false) {
    const pendingNotification: Notification = {
      id,
      title: options.pendingTitle,
      message: options.pendingMessage,
      type: 'pending',
      timestamp: Date.now()
    };
    
    dispatchNotification(pendingNotification);
  }
  
  try {
    // Wait for the promise to resolve
    const result = await promise;
    
    // Dispatch success notification if not disabled
    if (options.showNotification !== false) {
      const successNotification: Notification = {
        id,
        title: options.successTitle,
        message: options.successMessage,
        type: 'success',
        timestamp: Date.now(),
        duration: 3000
      };
      
      dispatchNotification(successNotification);
    }
    
    // Show toast if requested and not muted
    if (options.showToast && !notificationsMuted) {
      toast.success(`${options.successTitle}: ${options.successMessage}`, {
        id,
        duration: 3000
      });
    }
    
    return result;
  } catch (error) {
    // Determine error message
    const errorMessage = options.errorMessage || 
      (error instanceof Error ? error.message : 'An unknown error occurred');
    
    // Always show error notifications
    const errorNotification: Notification = {
      id,
      title: options.errorTitle,
      message: errorMessage,
      type: 'error',
      timestamp: Date.now(),
      duration: 5000
    };
    
    dispatchNotification(errorNotification);
    
    // Always show toast for errors unless muted
    if (!notificationsMuted) {
      toast.error(`${options.errorTitle}: ${errorMessage}`, {
        id,
        duration: 5000
      });
    }
    
    throw error;
  }
}

// Helper function to create a notification
export function createNotification(
  title: string,
  message: string,
  type: 'pending' | 'success' | 'error' | 'info',
  showToast: boolean = false
): Notification {
  const notification: Notification = {
    id: `notification-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
    title,
    message,
    type,
    timestamp: Date.now(),
    duration: type === 'error' ? 5000 : 3000
  };
  
  dispatchNotification(notification);
  
  if (showToast && !notificationsMuted) {
    if (type === 'error') {
      toast.error(`${title}: ${message}`, {
        id: notification.id,
        duration: notification.duration
      });
    } else if (type === 'success') {
      toast.success(`${title}: ${message}`, {
        id: notification.id,
        duration: notification.duration
      });
    }
  }
  
  return notification;
}

// For backward compatibility with existing code
export function notify({
  title,
  message,
  type = 'info',
  showToast = true
}: {
  title: string;
  message: string;
  type?: 'info' | 'success' | 'error' | 'warning';
  showToast?: boolean;
}) {
  return createNotification(title, message, type as any, showToast);
}

// Handle API errors
export function handleApiError(error: any, title = 'Error') {
  const message = error instanceof Error ? error.message : 'An unknown error occurred';
  createNotification(title, message, 'error', true);
  console.error(error);
  return message;
} 