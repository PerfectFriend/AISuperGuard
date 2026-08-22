import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { MapPin, Shield, AlertTriangle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useSites, useAlarms } from '@/hooks/useApiData';

interface Site {
  id: string;
  name: string;
  latitude: number | null;
  longitude: number | null;
  is_active: boolean;
  camera_count: number;
  active_alarms: number;
}

interface MapProps {
  sites: Site[];
  onSiteClick?: (site: Site) => void;
}

export const SiteMap = ({ sites, onSiteClick }: MapProps) => {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersRef = useRef<L.Marker[]>([]);
  const [selectedSite, setSelectedSite] = useState<Site | null>(null);
  const { t } = useTranslation('oxrana');

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = L.map(mapRef.current, {
      center: [55.7558, 37.6173],
      zoom: 10,
      zoomControl: false,
    });

    mapInstanceRef.current = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
    }).addTo(map);

    map.on('click', () => {
      setSelectedSite(null);
    });

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapInstanceRef.current) return;

    const map = mapInstanceRef.current;

    markersRef.current.forEach(marker => map.removeLayer(marker));
    markersRef.current = [];

    const validSites = sites.filter(s => s.latitude != null && s.longitude != null);

    if (validSites.length > 0) {
      const bounds = L.latLngBounds(
        validSites.map(s => [s.latitude!, s.longitude!] as [number, number])
      );
      map.fitBounds(bounds, { padding: [50, 50] });
    }

    validSites.forEach(site => {
      const isActive = site.is_active;
      const hasAlarms = site.active_alarms > 0;

      const iconColor = hasAlarms ? '#ef4444' : isActive ? '#22c55e' : '#6b7280';
      const iconSvg = `
        <div style="
          background: ${iconColor};
          width: 24px;
          height: 24px;
          border-radius: 50%;
          border: 3px solid white;
          box-shadow: 0 2px 8px rgba(0,0,0,0.3);
          display: flex;
          align-items: center;
          justify-content: center;
        ">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
            <circle cx="12" cy="10" r="3"/>
          </svg>
        </div>
      `;

      const icon = L.divIcon({
        html: iconSvg,
        className: 'custom-site-marker',
        iconSize: [30, 30],
        iconAnchor: [15, 30],
        popupAnchor: [0, -30],
      });

      const marker = L.marker([site.latitude!, site.longitude!], { icon })
        .addTo(map)
        .bindPopup(`
          <div style="min-width: 180px; padding: 8px;">
            <h4 style="margin: 0 0 8px; font-size: 14px; font-weight: 600;">${site.name}</h4>
            <div style="font-size: 12px; color: #666; display: grid; gap: 4px;">
              <div><strong>${t('cameras')}:</strong> ${site.camera_count}</div>
              <div><strong>${t('alarms')}:</strong> <span style="color: ${site.active_alarms > 0 ? '#ef4444' : '#22c55e'}">${site.active_alarms}</span></div>
              <div><strong>${t('status')}:</strong> <span style="color: ${isActive ? '#22c55e' : '#6b7280'}">${isActive ? t('active') : t('inactive')}</span></div>
            </div>
          </div>
        `, {
          closeButton: false,
          autoClose: false,
        });

      marker.on('click', () => {
        setSelectedSite(site);
        onSiteClick?.(site);
      });

      markersRef.current.push(marker);
    });
  }, [sites, onSiteClick, t]);

  if (!mapRef.current) return null;

  return (
    <div className="relative">
      <div ref={mapRef} className="w-full h-[500px] rounded-lg border" />
      
      {selectedSite && (
        <div className="absolute bottom-4 right-4 z-10 bg-card border rounded-lg shadow-lg p-4 w-72 animate-slide-in">
          <div className="flex items-start justify-between mb-3">
            <h4 className="font-semibold text-sm">{selectedSite.name}</h4>
            <button 
              onClick={() => setSelectedSite(null)}
              className="text-muted-foreground hover:text-foreground"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
          <div className="space-y-2 text-sm text-muted-foreground border-t pt-3">
            <div className="flex justify-between">
              <span>{t('cameras')}:</span>
              <span className="font-medium text-foreground">{selectedSite.camera_count}</span>
            </div>
            <div className="flex justify-between">
              <span>{t('activeAlarms')}:</span>
              <span className="font-medium" style={{ color: selectedSite.active_alarms > 0 ? '#ef4444' : '#22c55e' }}>
                {selectedSite.active_alarms}
              </span>
            </div>
            <div className="flex justify-between">
              <span>{t('status')}:</span>
              <Badge variant={selectedSite.is_active ? 'secondary' : 'outline'}>
                {selectedSite.is_active ? t('active') : t('inactive')}
              </Badge>
            </div>
          </div>
          <Button 
            variant="outline" 
            size="sm" 
            className="w-full mt-3"
            onClick={() => onSiteClick?.(selectedSite)}
          >
            {t('viewDetails') || t('view')}
          </Button>
        </div>
      )}

      <div className="absolute top-4 left-4 z-10 flex gap-2">
        <Button variant="outline" size="icon" onClick={() => mapInstanceRef.current?.zoomIn()} title={t('zoomIn')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14"/>
          </svg>
        </Button>
        <Button variant="outline" size="icon" onClick={() => mapInstanceRef.current?.zoomOut()} title={t('zoomOut')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 12h14"/>
          </svg>
        </Button>
        <Button variant="outline" size="icon" onClick={() => {
          if (markersRef.current.length > 0 && mapInstanceRef.current) {
            const bounds = L.latLngBounds(markersRef.current.map(m => m.getLatLng()));
            mapInstanceRef.current.fitBounds(bounds, { padding: [50, 50] });
          }
        }} title={t('fitAll')}>
          <MapPin className="w-4 h-4" />
        </Button>
      </div>

      <div className="absolute bottom-4 left-4 z-10 bg-card/90 border rounded-lg p-2 text-xs text-muted-foreground">
        <div className="flex items-center gap-1">
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }}></span>
          <span>{t('alert')}</span>
        </div>
        <div className="flex items-center gap-1">
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#22c55e', display: 'inline-block' }}></span>
          <span>{t('active')}</span>
        </div>
        <div className="flex items-center gap-1">
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#6b7280', display: 'inline-block' }}></span>
          <span>{t('inactive')}</span>
        </div>
      </div>
    </div>
  );
};

export default function Oxrana() {
  const { t } = useTranslation('oxrana');
  const { sites, loading: sitesLoading, error: sitesError, refetch: refetchSites } = useSites();
  const { alarms } = useAlarms('');
  const [isArmed, setIsArmed] = useState(true);
  const [entryDelay, setEntryDelay] = useState(30);
  const [exitDelay, setExitDelay] = useState(60);

  // Filter alarms for active sites
  const activeAlarms = alarms.filter(a => a.state === 'triggered');
  const siteAlarms = sites.reduce((acc, site) => {
    const count = activeAlarms.filter(a => a.site_id === site.id).length;
    acc[site.id] = count;
    return acc;
  }, {} as Record<string, number>);

  // Merge alarm counts into sites
  const sitesWithAlarms = sites.map(site => ({
    ...site,
    active_alarms: siteAlarms[site.id] || 0,
  }));

  const handleSiteClick = (site: Site) => {
    console.log('Site clicked:', site);
  };

  if (sitesLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (sitesError) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <AlertTriangle className="w-12 h-12 mx-auto text-destructive mb-4" />
          <p className="text-destructive">{t('errorLoading') || 'Error loading sites'}: {sitesError}</p>
          <Button variant="outline" onClick={refetchSites} className="mt-4">
            <RefreshCw className="w-4 h-4 mr-2" />
            {t('retry') || 'Retry'}
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Map Section */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <MapPin className="w-5 h-5" />
              {t('mapTitle')}
            </CardTitle>
            <CardDescription>{t('mapDescription')}</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant={isArmed ? 'secondary' : 'outline'} className="flex items-center gap-1">
              <Shield className="w-3 h-3" />
              {isArmed ? t('systemArmed') : t('systemDisarmed')}
            </Badge>
            <Switch 
              checked={isArmed} 
              onCheckedChange={setIsArmed} 
              className="h-4 w-8"
              aria-label={t('armedStatus')}
            />
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <SiteMap sites={sitesWithAlarms} onSiteClick={handleSiteClick} />
        </CardContent>
      </Card>

      {/* Status & Zones Section */}
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2">
              <Shield className="w-5 h-5" />
              {t('armedStatus')}
            </CardTitle>
            <CardDescription>{t('armedDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground">
                {t('systemArmed')}
              </span>
              <Badge variant={isArmed ? 'secondary' : 'outline'} className="text-lg px-3 py-1">
                {isArmed ? t('systemArmed') : t('systemDisarmed')}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground">
                {t('entryDelay')}
              </span>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={entryDelay}
                  onChange={e => setEntryDelay(Number(e.target.value))}
                  min={0}
                  max={300}
                  className="w-20 px-2 py-1 border rounded bg-background text-center"
                />
                <span className="text-sm text-muted-foreground">{t('seconds')}</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground">
                {t('exitDelay')}
              </span>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={exitDelay}
                  onChange={e => setExitDelay(Number(e.target.value))}
                  min={0}
                  max={300}
                  className="w-20 px-2 py-1 border rounded bg-background text-center"
                />
                <span className="text-sm text-muted-foreground">{t('seconds')}</span>
              </div>
            </div>
            <div className="pt-2 border-t">
              <Button 
                variant={isArmed ? 'destructive' : 'default'} 
                className="w-full"
                onClick={() => setIsArmed(!isArmed)}
              >
                {isArmed ? t('disarmSystem') : t('armSystem')}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              {t('activeAlarms')}
            </CardTitle>
            <CardDescription>{t('activeAlarmsDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {sitesWithAlarms.filter(s => s.active_alarms > 0).map(site => (
              <div key={site.id} className="flex items-center justify-between p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
                <div>
                  <p className="font-medium text-sm">{site.name}</p>
                  <p className="text-xs text-muted-foreground">{site.active_alarms} {t('activeAlarms').toLowerCase()}</p>
                </div>
                <Badge variant="destructive">{site.active_alarms}</Badge>
              </div>
            ))}
            {sitesWithAlarms.filter(s => s.active_alarms === 0).length === sitesWithAlarms.length && (
              <div className="text-center py-6 text-muted-foreground">
                <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>{t('noActiveAlarms')}</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-4">
            <CardTitle className="flex items-center gap-2">
              <MapPin className="w-5 h-5" />
              {t('accessZones')}
            </CardTitle>
            <CardDescription>{t('zonesDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {sitesWithAlarms.filter(s => s.is_active).flatMap(site => [
              { name: `${site.name} - ${t('closed')}`, status: 'Closed' as const },
              { name: `${site.name} - Windows`, status: 'Closed' as const },
              { name: `${site.name} - Perimeter`, status: site.active_alarms > 0 ? 'Alert' as const : 'Closed' as const },
            ]).slice(0, 6).map((zone, i) => (
              <div key={i} className="flex items-center justify-between text-sm">
                <span className="truncate pr-2">{zone.name}</span>
                <Badge variant={zone.status === 'Alert' ? 'destructive' : zone.status === 'Closed' ? 'secondary' : 'outline'}>
                  {zone.status === 'Alert' ? t('alert') : zone.status === 'Closed' ? t('closed') : t('open')}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Sites Summary */}
      <Card>
        <CardHeader>
          <CardTitle>{t('allSites')}</CardTitle>
          <CardDescription>{t('sitesDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="pb-3 font-medium">{t('siteName')}</th>
                  <th className="pb-3 font-medium">{t('coordinates')}</th>
                  <th className="pb-3 font-medium">{t('cameras')}</th>
                  <th className="pb-3 font-medium">{t('alarms')}</th>
                  <th className="pb-3 font-medium">{t('status')}</th>
                  <th className="pb-3 font-medium">{t('actions')}</th>
                </tr>
              </thead>
              <tbody>
                {sitesWithAlarms.map(site => (
                  <tr key={site.id} className="border-b hover:bg-accent">
                    <td className="py-3 font-medium">{site.name}</td>
                    <td className="py-3 text-muted-foreground">
                      {site.latitude && site.longitude 
                        ? `${site.latitude.toFixed(4)}, ${site.longitude.toFixed(4)}`
                        : t('notSet') || 'Not set'}
                    </td>
                    <td className="py-3">{site.camera_count}</td>
                    <td className="py-3">
                      <Badge variant={site.active_alarms > 0 ? 'destructive' : 'secondary'}>
                        {site.active_alarms}
                      </Badge>
                    </td>
                    <td className="py-3">
                      <Badge variant={site.is_active ? 'secondary' : 'outline'}>
                        {site.is_active ? t('active') : t('inactive')}
                      </Badge>
                    </td>
                    <td className="py-3">
                      <Button variant="ghost" size="icon" onClick={() => handleSiteClick(site)}>
                        <MapPin className="w-4 h-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};