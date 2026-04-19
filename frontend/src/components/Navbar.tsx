import React, { useState } from 'react';
import { useUser } from '@/context/UserContext';
import UserProfileModal from './UserProfileModal';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { 
  Menu, 
  User,
  MessageSquare,
  Home,
  Search,
  Globe,
  Database,
  Bell,
  BookOpen,
  LogOut
} from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ModeToggle } from '@/components/ui/mode-toggle';
import { NotificationBell } from './NotificationCenter';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useMediaQuery } from '@/hooks/use-media-query';
import { createNotification } from '@/utils/notifications';
import { useAuth } from '@/context/AuthContext';

interface NavbarProps {
  toggleSidebar: () => void;
}

const Navbar: React.FC<NavbarProps> = ({ toggleSidebar }) => {
  const { userProfile } = useUser();
  const { needsLogin, token, logout } = useAuth();
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const location = useLocation();
  const pathname = location.pathname;
  const isDesktop = useMediaQuery("(min-width: 1024px)");
  const isMobile = useMediaQuery('(max-width: 768px)');

  const navItems = [
    { name: 'Home', href: '/', icon: Home },
    { name: 'Chat', href: '/chat', icon: MessageSquare },
    { name: 'Crawl', href: '/crawl', icon: Globe },
    { name: 'Search', href: '/search', icon: Search },
    { name: 'Sites', href: '/sites', icon: Database }
  ];

  return (
    <header className="sticky top-0 z-40 flex h-16 items-center gap-4 border-b border-border bg-background px-6">
      <Button
        variant="ghost"
        size="icon"
        onClick={toggleSidebar}
        className={cn("hover:bg-accent", isDesktop && "lg:hidden")}
        aria-label="Toggle sidebar"
      >
        <Menu className="h-5 w-5" />
      </Button>
      
      {/* Logo and title for all screen sizes */}
      <div className="flex items-center">
        <Link to="/" className="flex items-center gap-3 text-xl font-semibold">
          <div className="h-8 w-8 overflow-hidden rounded-full">
            <img 
              src="https://imagedelivery.net/WfhVb8dSNAAvdXUdMfBuPQ/92227574-9331-49d0-535f-1f21c9b14f00/public" 
              alt="SupaChat Logo" 
              className="h-full w-full object-cover"
            />
          </div>
          <span>SupaChat</span>
        </Link>
      </div>
      
      {/* Only show navigation items on mobile/tablet screens */}
      {!isDesktop && (
        <div className="hidden md:flex items-center ml-6 space-x-6 text-sm font-medium">
          {navItems.map((item) => (
            <Link
              key={item.name}
              to={item.href}
              className={cn(
                "transition-colors hover:text-foreground/80 flex items-center gap-2",
                pathname === item.href ? "text-foreground" : "text-foreground/60"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.name}
            </Link>
          ))}
        </div>
      )}
      
      <div className="flex-1" />
      
      <div className="flex items-center gap-2">
        <NotificationBell />
        <ModeToggle />
        
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="relative h-9 w-9 rounded-full hover:bg-accent">
              <Avatar className="h-9 w-9">
                {userProfile.avatar ? (
                  <AvatarImage src={userProfile.avatar} alt={userProfile.name} />
                ) : (
                  <AvatarFallback className="bg-primary text-primary-foreground">
                    {userProfile.name.charAt(0).toUpperCase()}
                  </AvatarFallback>
                )}
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-56 bg-popover border-border" align="end" forceMount>
            <DropdownMenuLabel className="font-normal">
              <div className="flex flex-col space-y-1">
                <p className="text-sm font-medium leading-none">{userProfile.name}</p>
                <p className="text-xs leading-none text-muted-foreground">
                  User Profile
                </p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-border" />
            <DropdownMenuItem 
              onClick={() => setIsProfileModalOpen(true)}
              className="hover:bg-accent focus:bg-accent"
            >
              <User className="mr-2 h-4 w-4" />
              <span>Profile</span>
            </DropdownMenuItem>
            <DropdownMenuItem 
              asChild
              className="hover:bg-accent focus:bg-accent"
            >
              <Link to="/notifications">
                <Bell className="mr-2 h-4 w-4" />
                <span>Notification Info</span>
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem 
              asChild
              className="hover:bg-accent focus:bg-accent"
            >
              <Link to="/preferences">
                <User className="mr-2 h-4 w-4" />
                <span>User Preferences</span>
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem 
              asChild
              className="hover:bg-accent focus:bg-accent"
            >
              <Link to="/guide">
                <BookOpen className="mr-2 h-4 w-4" />
                <span>User Guide</span>
              </Link>
            </DropdownMenuItem>
            {needsLogin && token ? (
              <>
                <DropdownMenuSeparator className="bg-border" />
                <DropdownMenuItem
                  onClick={() => {
                    logout();
                    window.location.assign('/login');
                  }}
                  className="hover:bg-accent focus:bg-accent"
                >
                  <LogOut className="mr-2 h-4 w-4" />
                  <span>Sign out</span>
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      
      <UserProfileModal 
        isOpen={isProfileModalOpen} 
        onClose={() => setIsProfileModalOpen(false)} 
      />
    </header>
  );
};

export default Navbar; 