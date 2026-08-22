import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { Switch } from '@/components/ui/switch';
import { User, Sun, Moon, Globe, LogOut } from 'lucide-react';
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/hooks/useApiData';

export const TopBar = () => {
  const [isDarkMode, setIsDarkMode] = useState(false);
  const { i18n, t } = useTranslation('common');
  const { logout, user } = useAuth();

  useEffect(() => {
    const saved = localStorage.getItem('darkMode');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialDark = saved ? JSON.parse(saved) : prefersDark;
    setIsDarkMode(initialDark);
    if (initialDark) {
      document.documentElement.classList.add('dark');
    }
  }, []);

  const toggleDarkMode = () => {
    const newMode = !isDarkMode;
    setIsDarkMode(newMode);
    document.documentElement.classList.toggle('dark', newMode);
    localStorage.setItem('darkMode', JSON.stringify(newMode));
  };

  const changeLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
    localStorage.setItem('language', lng);
  };

  const handleLogout = () => {
    logout();
    window.location.href = '/login';
  };

  const languages = [
    { code: 'ru', name: t('russian'), nativeName: 'Русский' },
    { code: 'en', name: t('english'), nativeName: 'English' },
    { code: 'es', name: t('spanish'), nativeName: 'Español' },
  ];

  return (
    <header className="flex h-14 items-center justify-between px-4 bg-background border-b">
      <div className="flex items-center space-x-4">
        <h1 className="text-xl font-semibold text-foreground">SuperGuard Dashboard</h1>
      </div>
      <div className="flex items-center space-x-4">
        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center space-x-2">
            <Globe className="h-5 w-5" />
            <span className="hidden sm:inline-block w-20 truncate">{i18n.language.toUpperCase()}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-40" align="end">
            {languages.map((lang) => (
              <DropdownMenuItem
                key={lang.code}
                onClick={() => changeLanguage(lang.code)}
                className={i18n.language === lang.code ? 'bg-accent' : ''}
              >
                <div className="flex items-center justify-between">
                  <span>{lang.nativeName}</span>
                  {i18n.language === lang.code && (
                    <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger className="flex items-center space-x-2">
            <User className="h-6 w-6" />
            <span className="hidden md:inline">{user?.email || 'Admin'}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-48" align="end">
            <DropdownMenuItem>Profile</DropdownMenuItem>
            <DropdownMenuItem>Settings</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="destructive flex items-center gap-2" onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
              {t('logout')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <div className="flex items-center gap-2">
          <Switch
            checked={isDarkMode}
            onCheckedChange={toggleDarkMode}
            className="h-4 w-8"
            aria-label={t('darkMode')}
          />
          <div className="w-6 h-6 rounded-lg border flex items-center justify-center">
            {isDarkMode ? <Moon className="w-4 h-4" /> : <Sun className="w-4 h-4" />}
          </div>
        </div>
      </div>
    </header>
  );
};