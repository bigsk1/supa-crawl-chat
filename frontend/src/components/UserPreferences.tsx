import React, { useState, useEffect } from 'react';
import { apiService, UserPreference } from '../api/apiService';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { 
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  NativeSelect
} from '@/components/ui/select';
import { 
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import { createNotification } from '@/utils/notifications';

interface UserPreferencesProps {
  userId: string;
  sessionId?: string;
  onPreferenceChange?: () => void;
}

const UserPreferences: React.FC<UserPreferencesProps> = ({ userId: initialUserId, sessionId, onPreferenceChange }) => {
  const [preferences, setPreferences] = useState<UserPreference[]>([]);
  const [loading, setLoading] = useState(false);
  const [userId, setUserId] = useState(initialUserId || '');
  const [newPreference, setNewPreference] = useState({
    type: 'like',
    value: '',
    context: 'Manually added via UI',
    confidence: 0.9
  });
  const [minConfidence, setMinConfidence] = useState(0.7);
  const [showStatus, setShowStatus] = useState<'active' | 'inactive' | 'all'>('active');
  const [sortField, setSortField] = useState<string>('last_used');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [filteredPreferences, setFilteredPreferences] = useState<UserPreference[]>([]);

  const preferenceTypes = [
    { value: 'like', label: 'Like' },
    { value: 'dislike', label: 'Dislike' },
    { value: 'expertise', label: 'Expertise' },
    { value: 'interest', label: 'Interest' },
    { value: 'characteristic', label: 'Characteristic' },
    { value: 'opinion', label: 'Opinion' }
  ];

  const preferenceTypeExamples = {
    like: 'Python programming, coffee, hiking, sci-fi movies',
    dislike: 'long meetings, traffic, spam emails',
    expertise: 'JavaScript, React, machine learning, cooking',
    interest: 'blockchain technology, gardening, photography',
    characteristic: '5 years software engineering experience, detail-oriented',
    opinion: 'Docker is the best way to deploy applications'
  };

  const confidenceLabels = {
    0.0: 'All (0%)',
    0.5: '50% - Low confidence',
    0.7: '70% - Somewhat confident',
    0.8: '80% - Confident',
    0.9: '90% - Very confident',
    1.0: '100% - Absolutely certain'
  };

  // Custom notification function that uses the project's notification system
  const showNotification = (message: string, type: 'success' | 'error' | 'info' | 'pending') => {
    createNotification(
      type === 'error' ? 'Error' : type === 'success' ? 'Success' : 'Notification',
      message,
      type,
      false // Set to false to prevent double notifications
    );
  };

  // Apply local filtering based on minConfidence and showStatus
  useEffect(() => {
    // Filter preferences locally based on current settings
    let filtered = [...preferences];
    
    // Debug: Log all preferences with their is_active status and created_at
    console.log('All preferences with is_active status and created_at:');
    preferences.forEach(pref => {
      console.log(`ID: ${pref.id}, Value: ${pref.preference_value}, is_active: ${pref.is_active}, type: ${typeof pref.is_active}, created_at: ${pref.created_at}`);
    });
    
    console.log('Filtering preferences:', {
      total: preferences.length,
      minConfidence,
      showStatus,
      activeCount: preferences.filter(p => p.is_active === true).length,
      inactiveCount: preferences.filter(p => p.is_active === false).length,
      undefinedCount: preferences.filter(p => p.is_active === undefined).length,
      nullCount: preferences.filter(p => p.is_active === null).length
    });
    
    // Apply confidence filter
    if (minConfidence > 0) {
      filtered = filtered.filter(pref => pref.confidence >= minConfidence);
    }
    
    // Apply active/inactive filter - simplified logic
    if (showStatus === 'active') {
      // Only include preferences where is_active is strictly true (active)
      filtered = filtered.filter(pref => pref.is_active === true);
      console.log('Active preferences after filtering:', filtered.length);
    } else if (showStatus === 'inactive') {
      // Only include preferences where is_active is strictly false (inactive)
      filtered = filtered.filter(pref => pref.is_active === false);
      console.log('Inactive preferences after filtering:', filtered.length);
      
      // Debug: Log all inactive preferences
      console.log('Inactive preferences details:');
      filtered.forEach(pref => {
        console.log(`ID: ${pref.id}, Value: ${pref.preference_value}, is_active: ${pref.is_active}, type: ${typeof pref.is_active}`);
      });
    }
    // If showStatus is 'all', don't filter by active status
    
    setFilteredPreferences(filtered);
    
    console.log('Filtered results:', {
      filteredCount: filtered.length,
      showStatus
    });
  }, [preferences, minConfidence, showStatus]);

  // Sort preferences based on current sort settings
  const sortedPreferences = [...filteredPreferences].sort((a, b) => {
    let aValue: any = a[sortField as keyof UserPreference];
    let bValue: any = b[sortField as keyof UserPreference];
    
    // Handle null/undefined values
    if (aValue === null || aValue === undefined) aValue = '';
    if (bValue === null || bValue === undefined) bValue = '';
    
    // For dates, convert to timestamps for comparison
    if (sortField === 'created_at' || sortField === 'updated_at' || sortField === 'last_used') {
      aValue = aValue ? new Date(aValue).getTime() : 0;
      bValue = bValue ? new Date(bValue).getTime() : 0;
    }
    
    // For strings, convert to lowercase for case-insensitive comparison
    if (typeof aValue === 'string') aValue = aValue.toLowerCase();
    if (typeof bValue === 'string') bValue = bValue.toLowerCase();
    
    // Compare based on sort direction
    if (sortDirection === 'asc') {
      return aValue > bValue ? 1 : aValue < bValue ? -1 : 0;
    } else {
      return aValue < bValue ? 1 : aValue > bValue ? -1 : 0;
    }
  });

  const loadPreferences = async () => {
    if (!userId) {
      showNotification('Please enter a User ID', 'error');
      return;
    }
    
    setLoading(true);
    // Clear existing preferences to ensure we're showing fresh data
    setPreferences([]);
    
    try {
      console.log(`Loading preferences for user: ${userId}`);
      
      // First, load all active preferences
      const activePrefs = await apiService.getUserPreferences(userId, 0, true);
      console.log('Loaded active preferences:', activePrefs.length);
      
      // Then, load all inactive preferences
      const inactivePrefs = await apiService.getUserPreferences(userId, 0, false);
      console.log('Loaded all preferences:', inactivePrefs.length);
      
      // Filter out inactive preferences that are actually active
      // This is needed because the API returns all preferences when active_only=false
      const trulyInactivePrefs = inactivePrefs.filter(
        inactivePref => !activePrefs.some(activePref => activePref.id === inactivePref.id)
      );
      
      console.log('Truly inactive preferences:', trulyInactivePrefs.length);
      
      // Mark active preferences as active
      const markedActivePrefs = activePrefs.map(pref => ({
        ...pref,
        is_active: true
      }));
      
      // Mark inactive preferences as inactive
      const markedInactivePrefs = trulyInactivePrefs.map(pref => ({
        ...pref,
        is_active: false
      }));
      
      // Combine both sets
      const allPrefs = [...markedActivePrefs, ...markedInactivePrefs];
      console.log('Combined preferences:', allPrefs.length);
      
      setPreferences(allPrefs);
      showNotification(
        allPrefs.length > 0 
          ? `Loaded ${allPrefs.length} preferences for ${userId}` 
          : `No preferences found for ${userId}`,
        'success'
      );
    } catch (error) {
      console.error('Error loading preferences:', error);
      showNotification('Failed to load preferences', 'error');
    } finally {
      setLoading(false);
    }
  };

  // Only load preferences automatically when component mounts if userId is provided
  useEffect(() => {
    if (initialUserId) {
      loadPreferences();
    }
  }, []);

  // Apply filter changes when Refresh button is clicked
  const handleFilterChange = () => {
    // Force a reload of preferences from the API
    loadPreferences();
    
    // Notify the user that the refresh is happening
    showNotification('Refreshing preferences...', 'info');
  };

  // Debug function to check active/inactive status
  const debugActiveStatus = () => {
    console.log('=== DEBUG ACTIVE STATUS ===');
    console.log('Total preferences:', preferences.length);
    console.log('Active preferences:', preferences.filter(p => p.is_active === true).length);
    console.log('Inactive preferences:', preferences.filter(p => p.is_active === false).length);
    console.log('Undefined is_active:', preferences.filter(p => p.is_active === undefined).length);
    console.log('Null is_active:', preferences.filter(p => p.is_active === null).length);
    console.log('Current filter:', showStatus);
    console.log('Filtered preferences:', filteredPreferences.length);
    
    // Check specific preferences
    const pref12 = preferences.find(p => p.id === 12);
    const pref19 = preferences.find(p => p.id === 19);
    const pref24 = preferences.find(p => p.id === 24);
    
    console.log('Preference 12:', pref12 ? `is_active: ${pref12.is_active}, type: ${typeof pref12.is_active}` : 'not found');
    console.log('Preference 19:', pref19 ? `is_active: ${pref19.is_active}, type: ${typeof pref19.is_active}` : 'not found');
    console.log('Preference 24:', pref24 ? `is_active: ${pref24.is_active}, type: ${typeof pref24.is_active}` : 'not found');
    console.log('=========================');
  };

  // Handle sort column click
  const handleSortClick = (field: string) => {
    if (sortField === field) {
      // Toggle direction if same field
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      // Set new field and default to descending
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const handleAddPreference = async () => {
    if (!userId) {
      showNotification('Please enter a User ID', 'error');
      return;
    }
    
    if (!newPreference.value.trim()) {
      showNotification('Preference value cannot be empty', 'error');
      return;
    }

    setLoading(true);
    try {
      const result = await apiService.addUserPreference(
        userId,
        newPreference.type,
        newPreference.value,
        newPreference.context,
        newPreference.confidence,
        sessionId
      );

      if (result) {
        showNotification('Preference added successfully', 'success');
        setNewPreference({
          ...newPreference,
          value: ''
        });
        loadPreferences();
        if (onPreferenceChange) onPreferenceChange();
      } else {
        showNotification('Failed to add preference', 'error');
      }
    } catch (error) {
      console.error('Error adding preference:', error);
      showNotification('Failed to add preference', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeletePreference = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this preference? This will permanently remove it from the database.')) {
      return;
    }

    setLoading(true);
    try {
      const success = await apiService.deleteUserPreference(userId, id);
      if (success) {
        setPreferences(prevPrefs => prevPrefs.filter(pref => pref.id !== id));
        showNotification('Preference deleted successfully', 'success');
        loadPreferences();
        if (onPreferenceChange) onPreferenceChange();
      } else {
        showNotification('Failed to delete preference', 'error');
      }
    } catch (error) {
      console.error('Error deleting preference:', error);
      showNotification('Failed to delete preference', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeactivatePreference = async (id: number) => {
    setLoading(true);
    try {
      const success = await apiService.deactivateUserPreference(userId, id);
      if (success) {
        showNotification('Preference deactivated successfully', 'success');
        
        // Update the preference locally to avoid a full reload
        setPreferences(prevPrefs => 
          prevPrefs.map(pref => 
            pref.id === id ? { ...pref, is_active: false } : pref
          )
        );
        
        if (onPreferenceChange) onPreferenceChange();
      } else {
        showNotification('Failed to deactivate preference', 'error');
        loadPreferences(); // Fallback to full reload if the update failed
      }
    } catch (error) {
      console.error('Error deactivating preference:', error);
      showNotification('Failed to deactivate preference', 'error');
      loadPreferences(); // Fallback to full reload if there was an error
    } finally {
      setLoading(false);
    }
  };

  const handleActivatePreference = async (id: number) => {
    setLoading(true);
    try {
      const success = await apiService.activateUserPreference(userId, id);
      if (success) {
        showNotification('Preference activated successfully', 'success');
        
        // Update the preference locally to avoid a full reload
        setPreferences(prevPrefs => 
          prevPrefs.map(pref => 
            pref.id === id ? { ...pref, is_active: true } : pref
          )
        );
        
        if (onPreferenceChange) onPreferenceChange();
      } else {
        showNotification('Failed to activate preference', 'error');
        loadPreferences(); // Fallback to full reload if the update failed
      }
    } catch (error) {
      console.error('Error activating preference:', error);
      showNotification('Failed to activate preference', 'error');
      loadPreferences(); // Fallback to full reload if there was an error
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAllPreferences = async () => {
    if (!userId) {
      showNotification('Please enter a User ID', 'error');
      return;
    }
    
    if (!window.confirm('Are you sure you want to DELETE ALL preferences? This will permanently delete ALL preferences from the database and cannot be undone.')) {
      return;
    }

    setLoading(true);
    try {
      const success = await apiService.clearUserPreferences(userId);
      if (success) {
        showNotification('All preferences deleted successfully', 'success');
        loadPreferences();
        if (onPreferenceChange) onPreferenceChange();
      } else {
        showNotification('Failed to delete all preferences', 'error');
      }
    } catch (error) {
      console.error('Error deleting all preferences:', error);
      showNotification('Failed to delete all preferences', 'error');
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        return 'Invalid date';
      }
      return date.toLocaleString();
    } catch (e) {
      console.error('Error formatting date:', e, dateString);
      return 'N/A';
    }
  };

  // Get sort indicator
  const getSortIndicator = (field: string) => {
    if (sortField !== field) return null;
    return sortDirection === 'asc' ? '↑' : '↓';
  };

  return (
    <div className="user-preferences p-4">
      <div className="mb-6 p-4 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 shadow-sm">
        <h2 className="text-xl font-bold text-gray-800 dark:text-gray-200 mb-4">User ID</h2>
        <div className="flex flex-col md:flex-row gap-4">
          <Input
            type="text"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="Enter user ID (e.g., TestUser)"
            className="flex-grow bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-200"
          />
          <Button 
            onClick={loadPreferences} 
            disabled={loading || !userId.trim()}
            className="bg-blue-600 hover:bg-blue-700 text-white"
          >
            {loading ? <Spinner size="sm" className="mr-2" /> : null}
            Load Preferences
          </Button>
        </div>
        <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
          This should match your display name in your profile settings.
        </p>
      </div>

      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold text-gray-800 dark:text-gray-200">User Preferences</h2>
        <div className="flex space-x-2">
          <Button 
            onClick={handleFilterChange} 
            variant="outline"
            disabled={loading || !userId.trim()}
          >
            {loading ? <Spinner size="sm" className="mr-2" /> : null}
            Refresh
          </Button>
          <Button 
            onClick={handleDeleteAllPreferences} 
            variant="destructive"
            disabled={loading || preferences.length === 0 || !userId.trim()}
            title="Permanently delete ALL preferences from the database"
          >
            Delete All
          </Button>
        </div>
      </div>

      <div className="filter-controls mb-4 grid grid-cols-1 md:grid-cols-3 gap-2">
        <div className="flex items-center">
          <label className="mr-2 text-gray-800 dark:text-gray-200 whitespace-nowrap">Min Confidence:</label>
          <NativeSelect
            value={minConfidence.toString()}
            onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
            disabled={loading}
            className="w-full bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-200"
          >
            <option value="0">{confidenceLabels[0.0]}</option>
            <option value="0.5">{confidenceLabels[0.5]}</option>
            <option value="0.7">{confidenceLabels[0.7]}</option>
            <option value="0.8">{confidenceLabels[0.8]}</option>
            <option value="0.9">{confidenceLabels[0.9]}</option>
          </NativeSelect>
        </div>
        <div className="flex items-center">
          <label className="mr-2 text-gray-800 dark:text-gray-200 whitespace-nowrap">Show:</label>
          <NativeSelect
            value={showStatus}
            onChange={(e) => {
              const newStatus = e.target.value as 'active' | 'inactive' | 'all';
              console.log(`Changing status filter from ${showStatus} to ${newStatus}`);
              setShowStatus(newStatus);
            }}
            disabled={loading}
            className="w-full bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-200"
          >
            <option value="active">Active Only (Used by AI)</option>
            <option value="inactive">Inactive Only (Not Used by AI)</option>
            <option value="all">All Preferences</option>
          </NativeSelect>
        </div>
        <div className="flex items-center">
          <label className="mr-2 text-gray-800 dark:text-gray-200 whitespace-nowrap">Sort By:</label>
          <NativeSelect
            value={sortField + ":" + sortDirection}
            onChange={(e) => {
              const [field, direction] = e.target.value.split(":");
              setSortField(field);
              setSortDirection(direction as 'asc' | 'desc');
            }}
            disabled={loading}
            className="w-full bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-200"
          >
            <option value="preference_type:asc">Type (A-Z)</option>
            <option value="preference_type:desc">Type (Z-A)</option>
            <option value="preference_value:asc">Value (A-Z)</option>
            <option value="preference_value:desc">Value (Z-A)</option>
            <option value="confidence:desc">Confidence (High-Low)</option>
            <option value="confidence:asc">Confidence (Low-High)</option>
            <option value="last_used:desc">Last Used (Recent)</option>
            <option value="last_used:asc">Last Used (Oldest)</option>
          </NativeSelect>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center my-8">
          <Spinner size="lg" />
        </div>
      ) : sortedPreferences.length === 0 ? (
        <div className="text-center my-8 p-6 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 rounded-md border border-gray-300 dark:border-gray-700 shadow-sm">
          <p className="text-lg mb-2">No preferences found</p>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {showStatus === 'inactive' 
              ? "No inactive preferences found. Try selecting 'Active Only' or 'All Preferences'."
              : showStatus === 'active'
                ? "No active preferences found. Try selecting 'Inactive Only' or 'All Preferences', or add a new preference below."
                : "No preferences found. Add your first preference below to help the AI understand your interests and preferences."}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead 
                  className="cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-200"
                  onClick={() => handleSortClick('preference_type')}
                >
                  Type {getSortIndicator('preference_type')}
                </TableHead>
                <TableHead 
                  className="cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-200"
                  onClick={() => handleSortClick('preference_value')}
                >
                  Value {getSortIndicator('preference_value')}
                </TableHead>
                <TableHead 
                  className="cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-200"
                  onClick={() => handleSortClick('confidence')}
                >
                  Confidence {getSortIndicator('confidence')}
                </TableHead>
                <TableHead className="w-1/3 text-gray-900 dark:text-gray-200">Context</TableHead>
                <TableHead 
                  className="cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-900 dark:text-gray-200"
                  onClick={() => handleSortClick('last_used')}
                >
                  Last Used {getSortIndicator('last_used')}
                </TableHead>
                <TableHead className="text-gray-900 dark:text-gray-200">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedPreferences.map((pref) => (
                <TableRow 
                  key={pref.id} 
                  className={`${pref.is_active ? '' : 'bg-gray-50 dark:bg-gray-800'}`}
                >
                  <TableCell className="text-gray-900 dark:text-gray-200">
                    <Badge variant={pref.preference_type === 'like' ? 'default' : 
                                    pref.preference_type === 'dislike' ? 'destructive' : 
                                    'secondary'}
                           className="text-white dark:text-white">
                      {pref.preference_type}
                    </Badge>
                    {pref.is_active === false && (
                      <Badge variant="outline" className="ml-1 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600">
                        Inactive
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-gray-900 dark:text-gray-200">{pref.preference_value}</TableCell>
                  <TableCell className="text-gray-900 dark:text-gray-200">{(pref.confidence * 100).toFixed(0)}%</TableCell>
                  <TableCell className="whitespace-normal break-words max-w-xs text-gray-900 dark:text-gray-200" title={pref.context}>
                    <div className="line-clamp-2">
                      {pref.context || 'N/A'}
                    </div>
                  </TableCell>
                  <TableCell className="text-gray-900 dark:text-gray-200">{formatDate(pref.last_used)}</TableCell>
                  <TableCell>
                    <div className="flex flex-col space-y-2">
                      {pref.is_active ? (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDeactivatePreference(pref.id!)}
                          disabled={loading}
                          title="Mark as inactive (will not be used by AI but remains in database)"
                          className="w-full"
                        >
                          Deactivate
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleActivatePreference(pref.id!)}
                          disabled={loading}
                          title="Mark as active (will be used by AI)"
                          className="w-full"
                        >
                          Activate
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleDeletePreference(pref.id!)}
                        disabled={loading}
                        title="Permanently delete this preference from the database"
                        className="w-full"
                      >
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            Showing {sortedPreferences.length} of {preferences.length} preferences
            {showStatus !== 'all' && (
              <span> ({showStatus === 'active' ? 'active only' : 'inactive only'})</span>
            )}
          </div>
        </div>
      )}

      <div className="add-preference-form mt-8 mb-4 p-6 border border-gray-300 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 shadow-sm">
        <h3 className="text-xl font-semibold mb-4 text-gray-800 dark:text-gray-200">Add New Preference</h3>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
          <div>
            <label className="block mb-2 font-medium text-gray-800 dark:text-gray-200">Preference Type</label>
            <NativeSelect
              value={newPreference.type}
              onChange={(e) => setNewPreference({
                ...newPreference,
                type: e.target.value
              })}
              disabled={loading}
              className="w-full bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-200"
            >
              {preferenceTypes.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </NativeSelect>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
              Choose what kind of preference you want to add
            </p>
          </div>
          
          <div>
            <label className="block mb-2 font-medium text-gray-800 dark:text-gray-200">Summary/Value</label>
            <Input
              type="text"
              value={newPreference.value}
              onChange={(e) => setNewPreference({
                ...newPreference,
                value: e.target.value
              })}
              placeholder={`What you ${newPreference.type === 'like' ? 'like' : 
                            newPreference.type === 'dislike' ? 'dislike' : 
                            newPreference.type === 'expertise' ? 'are skilled in' : 
                            newPreference.type === 'interest' ? 'are interested in' : 
                            newPreference.type === 'characteristic' ? 'are characterized by' : 
                            'have an opinion about'}`}
              disabled={loading}
              className="w-full bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-200"
            />
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
              Examples: {preferenceTypeExamples[newPreference.type as keyof typeof preferenceTypeExamples]}
            </p>
          </div>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
          <div>
            <label className="block mb-2 font-medium text-gray-800 dark:text-gray-200">Confidence Level</label>
            <NativeSelect
              value={newPreference.confidence.toString()}
              onChange={(e) => setNewPreference({
                ...newPreference,
                confidence: parseFloat(e.target.value)
              })}
              disabled={loading}
              className="w-full bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-200"
            >
              <option value="0.7">{confidenceLabels[0.7]}</option>
              <option value="0.8">{confidenceLabels[0.8]}</option>
              <option value="0.9">{confidenceLabels[0.9]}</option>
              <option value="1.0">{confidenceLabels[1.0]}</option>
            </NativeSelect>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
              Higher confidence means the AI will prioritize this preference more strongly
            </p>
          </div>
          
          <div>
            <label className="block mb-2 font-medium text-gray-800 dark:text-gray-200">Additional Context</label>
            <Input
              type="text"
              value={newPreference.context}
              onChange={(e) => setNewPreference({
                ...newPreference,
                context: e.target.value
              })}
              placeholder="Information to help AI understand this preference"
              disabled={loading}
              className="w-full bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-800 dark:text-gray-200"
            />
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
              Explain when/why this preference applies or provide more details
            </p>
          </div>
        </div>
        
        <Button
          onClick={handleAddPreference}
          disabled={loading || !newPreference.value.trim() || !userId.trim()}
          className="mt-4 px-6 bg-blue-600 hover:bg-blue-700 text-white"
          size="lg"
        >
          Add Preference
        </Button>
      </div>
    </div>
  );
};

export default UserPreferences;
