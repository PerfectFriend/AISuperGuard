import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import { Maximize, Volume2, VolumeX, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

interface VideoPlayerProps {
  src: string;
  type?: 'hls' | 'rtsp' | 'mp4' | 'webm';
  width?: number;
  height?: number;
  autoplay?: boolean;
  muted?: boolean;
  controls?: boolean;
  className?: string;
  onError?: (error: Error) => void;
  onLoad?: () => void;
}

export const VideoPlayer = ({
  src,
  type = 'hls',
  width = 640,
  height = 360,
  autoplay = false,
  muted = true,
  controls = true,
  className = '',
  onError,
  onLoad,
}: VideoPlayerProps) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(muted);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  const cleanupHls = () => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;

    setHasError(false);
    setIsLoading(true);
    cleanupHls();

    const handleLoadStart = () => setIsLoading(true);
    const handleLoadedData = () => {
      setIsLoading(false);
      setDuration(video.duration);
      onLoad?.();
    };
    const handleError = () => {
      setHasError(true);
      setIsLoading(false);
      const error = new Error(`Video error: ${video.error?.message || 'Unknown'}`);
      onError?.(error);
    };
    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);
    const handleTimeUpdate = () => setCurrentTime(video.currentTime);
    const handleEnded = () => setIsPlaying(false);

    video.addEventListener('loadstart', handleLoadStart);
    video.addEventListener('loadeddata', handleLoadedData);
    video.addEventListener('error', handleError);
    video.addEventListener('play', handlePlay);
    video.addEventListener('pause', handlePause);
    video.addEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('ended', handleEnded);

    if (type === 'hls' && Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
        lowLatencyMode: true,
      });
      hlsRef.current = hls;
      
      hls.loadSource(src);
      hls.attachMedia(video);
      
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (autoplay) video.play().catch(() => {});
      });
      
      hls.on(Hls.Events.ERROR, (_, data) => {
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              hls.destroy();
              setHasError(true);
              break;
          }
        }
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Native HLS support (Safari)
      video.src = src;
      if (autoplay) video.play().catch(() => {});
    } else {
      // MP4, WebM, etc.
      video.src = src;
      if (autoplay) video.play().catch(() => {});
    }

    return () => {
      video.removeEventListener('loadstart', handleLoadStart);
      video.removeEventListener('loadeddata', handleLoadedData);
      video.removeEventListener('error', handleError);
      video.removeEventListener('play', handlePlay);
      video.removeEventListener('pause', handlePause);
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('ended', handleEnded);
      cleanupHls();
      video.pause();
      video.src = '';
    };
  }, [src, type, autoplay, onError, onLoad]);

  const togglePlay = () => {
    const video = videoRef.current;
    if (!video) return;
    
    if (isPlaying) {
      video.pause();
    } else {
      video.play().catch(() => {});
    }
  };

  const toggleMute = () => {
    const video = videoRef.current;
    if (!video) return;
    
    video.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  const toggleFullscreen = async () => {
    const container = videoRef.current?.parentElement;
    if (!container) return;

    if (!isFullscreen) {
      try {
        await container.requestFullscreen();
        setIsFullscreen(true);
      } catch (err) {
        console.error('Fullscreen error:', err);
      }
    } else {
      try {
        await document.exitFullscreen();
        setIsFullscreen(false);
      } catch (err) {
        console.error('Exit fullscreen error:', err);
      }
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (hasError) {
    return (
      <Card className={className} style={{ width, height }}>
        <CardContent className="flex items-center justify-center h-full bg-gray-900">
          <div className="text-center text-white">
            <Loader2 className="w-12 h-12 mx-auto mb-4 animate-spin text-gray-600" />
            <p>Failed to load stream</p>
            <p className="text-sm text-gray-400">{src}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className={`relative ${className}`} style={{ width, height }}>
      <video
        ref={videoRef}
        width={width}
        height={height}
        muted={isMuted}
        playsInline
        style={{ width: '100%', height: '100%', background: '#000' }}
      />
      
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/50 z-10">
          <Loader2 className="w-10 h-10 animate-spin text-white" />
        </div>
      )}

      {controls && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-3 z-20">
          <div className="flex items-center gap-2 mb-2">
            <input
              type="range"
              min={0}
              max={duration || 100}
              value={currentTime}
              onChange={(e) => {
                const video = videoRef.current;
                if (video) video.currentTime = parseFloat(e.target.value);
              }}
              className="flex-1 h-1 appearance-none bg-gray-600 rounded-full accent-primary cursor-pointer"
            />
            <span className="text-white text-xs font-mono w-20 text-right">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon" onClick={togglePlay} aria-label={isPlaying ? 'Pause' : 'Play'}>
                {isPlaying ? (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>
                ) : (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                )}
              </Button>
              <Button variant="ghost" size="icon" onClick={toggleMute} aria-label={isMuted ? 'Unmute' : 'Mute'}>
                {isMuted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
              </Button>
              <input
                type="range"
                min={0}
                max={1}
                step={0.1}
                value={isMuted ? 0 : 1}
                onChange={(e) => {
                  const video = videoRef.current;
                  if (video) {
                    video.volume = parseFloat(e.target.value);
                    video.muted = video.volume === 0;
                    setIsMuted(video.volume === 0);
                  }
                }}
                className="w-20 h-1 appearance-none bg-gray-600 rounded-full accent-primary cursor-pointer"
              />
            </div>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon" onClick={toggleFullscreen} aria-label={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}>
                {isFullscreen ? (
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/></svg>
                ) : (
                  <Maximize className="w-5 h-5" />
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// Multi-camera grid view
export const CameraGrid = ({ 
  cameras, 
  onCameraClick,
  cols = 2 
}: { 
  cameras: Array<{ id: string; name: string; stream_url: string; type: string; is_online: boolean }>;
  onCameraClick?: (camera: any) => void;
  cols?: number;
}) => {
  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
      {cameras.map((camera) => (
        <Card key={camera.id} className="overflow-hidden h-64" onClick={() => onCameraClick?.(camera)}>
          <CardContent className="p-0 h-full relative">
            <VideoPlayer
              src={camera.stream_url}
              type={camera.type as any}
              width={320}
              height={180}
              muted={true}
              controls={false}
            />
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
              <div className="flex items-center justify-between text-white text-sm">
                <span className="truncate pr-2">{camera.name}</span>
                <span className={`flex items-center gap-1 ${camera.is_online ? 'text-green-400' : 'text-red-400'}`}>
                  <span className="w-2 h-2 rounded-full bg-current" />
                  {camera.is_online ? 'Online' : 'Offline'}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
};