import React, { useEffect, useState, useRef } from 'react';
import { useUser } from '@/context/UserContext';
import { useNavigate } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Upload, Settings } from 'lucide-react';

interface UserProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const UserProfileModal: React.FC<UserProfileModalProps> = ({ isOpen, onClose }) => {
  const { userProfile, updateName, updateAvatar } = useUser();
  const [name, setName] = useState(userProfile.name);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (isOpen) {
      setName(userProfile.name);
    }
  }, [isOpen, userProfile.name]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateName(name);
    onClose();
  };

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        const base64String = reader.result as string;
        updateAvatar(base64String);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleManagePreferences = () => {
    onClose();
    navigate(`/preferences/${encodeURIComponent(userProfile.name)}`);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md bg-[#171923] border-white/[0.05] text-gray-200">
        <DialogHeader>
          <DialogTitle className="text-gray-200">Edit Profile</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="flex flex-col items-center">
            <div
              className="cursor-pointer"
              onClick={() => fileInputRef.current?.click()}
            >
              <Avatar className="h-24 w-24">
                {userProfile.avatar ? (
                  <AvatarImage src={userProfile.avatar} alt={userProfile.name} />
                ) : (
                  <AvatarFallback className="bg-primary text-primary-foreground text-4xl">
                    {userProfile.name.charAt(0).toUpperCase()}
                  </AvatarFallback>
                )}
              </Avatar>
            </div>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleAvatarChange}
              accept="image/*"
              className="hidden"
            />
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => fileInputRef.current?.click()}
              className="mt-2 text-gray-300 hover:text-white hover:bg-white/[0.06]"
            >
              <Upload className="h-4 w-4 mr-2" />
              Change Avatar
            </Button>
          </div>

          <div className="space-y-2">
            <Label htmlFor="name" className="text-gray-300">Display Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              required
              className="bg-[#0f1117] border-white/[0.05] text-gray-200 placeholder:text-gray-500"
            />
            <p className="text-sm text-gray-500 mt-1">
              This name will be used as your user ID for preferences and chat history.
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-gray-300">Preferences</Label>
            <div className="bg-[#0f1117] border border-white/[0.05] rounded-md p-4">
              <p className="text-sm text-gray-300 mb-3">
                Manage your preferences to help the AI understand your interests, expertise, and preferences.
              </p>
              <Button
                type="button"
                onClick={handleManagePreferences}
                className="w-full bg-primary hover:bg-primary/90"
              >
                <Settings className="h-4 w-4 mr-2" />
                Manage Preferences
              </Button>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              className="border-white/[0.05] bg-[#0f1117] hover:bg-white/[0.06] text-gray-300"
            >
              Cancel
            </Button>
            <Button type="submit" className="bg-primary hover:bg-primary/90">
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default UserProfileModal;
