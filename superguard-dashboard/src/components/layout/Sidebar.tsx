import { clsx } from 'clsx';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { 
  Monitor, Shield, Folder, Video, Zap, Power, 
  Bell, MessageSquare, Settings, ChevronRight, ChevronDown
} from 'lucide-react';
import { useSites } from '@/hooks/useApiData';
import { useState } from 'react';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  Monitor,
  Shield,
  Folder,
  Video,
  Zap,
  Power,
  Bell,
  MessageSquare,
  Settings,
};

export const Sidebar = () => {
  const { t } = useTranslation('sidebar');
  const location = useLocation();
  const navigate = useNavigate();
  const { sites } = useSites();
  const [activeSiteId, setActiveSiteId] = useState<string | null>(sites.length > 0 ? sites[0].id : null);
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const activeSite = sites.find(s => s.id === activeSiteId);

  const menuItems = [
    { label: t('dashboard'), href: '/', icon: 'Monitor', global: true },
    { label: t('oxrana'), href: '/oxrana', icon: 'Shield', global: true },
    { label: t('sites'), href: '/sites', icon: 'Folder', global: true },
    { label: t('cameras'), href: activeSiteId ? `/sites/${activeSiteId}/cameras` : '/sites', icon: 'Video', global: false },
    { label: t('detectors'), href: activeSiteId ? `/sites/${activeSiteId}/detectors` : '/sites', icon: 'Zap', global: false },
    { label: t('actuators'), href: activeSiteId ? `/sites/${activeSiteId}/actuators` : '/sites', icon: 'Power', global: false },
    { label: t('alarms'), href: activeSiteId ? `/sites/${activeSiteId}/alarms` : '/sites', icon: 'Bell', global: false },
    { label: t('notifiers'), href: activeSiteId ? `/sites/${activeSiteId}/notifiers` : '/sites', icon: 'MessageSquare', global: false },
    { label: t('system'), href: '/system', icon: 'Settings', global: true },
  ];

  const handleSiteChange = (siteId: string) => {
    setActiveSiteId(siteId);
    setDropdownOpen(false);
    // If currently on a site-specific page, navigate to the new site's equivalent page
    const currentPath = location.pathname;
    if (!currentPath.startsWith('/sites') || currentPath === '/sites') return;
    
    // Extract the page type from current path
    const parts = currentPath.split('/');
    if (parts.length >= 3) {
      const pageType = parts[parts.length - 1];
      navigate(`/sites/${siteId}/${pageType}`);
    }
  };

  return (
    <aside className="w-64 bg-card border-r border-border">
      <div className="p-4">
        <h1 className="text-xl font-bold mb-6 text-card-foreground">SuperGuard</h1>
        
        {/* Site Selector Dropdown */}
        <DropdownMenu open={dropdownOpen} onOpenChange={setDropdownOpen}>
          <DropdownMenuTrigger asChild>
            <button className="w-full flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium transition-colors bg-primary/10 hover:bg-primary/20 text-blue-600 dark:text-yellow-400">
              <span className="flex items-center gap-2">
                <Folder className="h-4 w-4" />
                {activeSite ? activeSite.name : t('selectSite')}
              </span>
              <ChevronDown className="h-4 w-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-full" align="start">
            {sites.length === 0 ? (
              <DropdownMenuItem className="text-muted-foreground" onClick={() => navigate('/sites')}>
                {t('noSitesAvailable')}
              </DropdownMenuItem>
            ) : (
              sites.map((site) => (
                <DropdownMenuItem
                  key={site.id}
                  onClick={() => handleSiteChange(site.id)}
                  className={activeSiteId === site.id ? 'bg-primary text-primary-foreground' : ''}
                >
                  <span className="flex items-center gap-2">
                    {activeSiteId === site.id && <ChevronRight className="h-4 w-4" />}
                    {site.name}
                  </span>
                </DropdownMenuItem>
              ))
            )}
            <DropdownMenuItem className="border-t pt-2" onClick={() => navigate('/sites')}>
              <span className="flex items-center gap-2">
                <span className="h-4 w-4" />
                {t('manageSites')}
              </span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <nav className="space-y-1 mt-4">
          {menuItems.map((item, index) => {
            const Icon = iconMap[item.icon];
            const isActive = location.pathname === item.href || 
              (!item.global && location.pathname.startsWith(`/sites/${activeSiteId}/`) && location.pathname.endsWith(item.href.split('/').pop() || ''));
            return (
              <Link
                key={index}
                to={item.href}
                className={clsx(
                  'flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors',
                  !activeSiteId && !item.global
                    ? 'text-muted-foreground/50 pointer-events-none'
                    : isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                )}
                onClick={(e) => {!activeSiteId && !item.global && e.preventDefault();}}
              >
                <Icon className="h-5 w-5 shrink-0" />
                <span className="ml-3">{item.label}</span>
                {!activeSiteId && !item.global && (
                  <ChevronRight className="ml-auto h-4 w-4 text-muted-foreground" />
                )}
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
};