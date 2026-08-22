import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Edit, Save, X, Trash2, Maximize2, Minimize2, Undo2, RotateCcw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { VideoPlayer } from '@/components/VideoPlayer';

interface Point {
  x: number;
  y: number;
}

interface ZoneEditorProps {
  src: string;
  type?: 'hls' | 'rtsp' | 'mp4' | 'webm';
  width?: number;
  height?: number;
  initialZone?: Point[][]; // Array of polygons (each polygon is array of points)
  onZoneChange: (zone: Point[][]) => void;
  readOnly?: boolean;
  className?: string;
}

export const ZoneEditor = ({
  src,
  type = 'hls',
  width = 640,
  height = 360,
  initialZone = [],
  onZoneChange,
  readOnly = false,
  className = '',
}: ZoneEditorProps) => {
  const { t } = useTranslation('cameras');
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
    const [zone, setZone] = useState<Point[][]>(initialZone);
  const [currentPolygon, setCurrentPolygon] = useState<Point[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [selectedPolygonIndex, setSelectedPolygonIndex] = useState<number | null>(null);
  const [selectedPointIndex, setSelectedPointIndex] = useState<number | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [history, setHistory] = useState<Point[][][]>([initialZone]);
  const [historyIndex, setHistoryIndex] = useState(0);
  const [videoLoaded, setVideoLoaded] = useState(false);

  // Sync zone state to parent
  useEffect(() => {
    onZoneChange(zone);
    // Update history
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push(zone.map(p => [...p]));
    setHistory(newHistory);
    setHistoryIndex(newHistory.length - 1);
  }, [zone, onZoneChange, history, historyIndex]);

  // Load initial zone
  useEffect(() => {
    if (initialZone.length > 0 && zone.length === 0) {
      setZone(initialZone);
    }
  }, [initialZone, zone.length]);

  // Get video element from VideoPlayer
  useEffect(() => {
    const video = document.querySelector('video');
    if (video) {
      video.addEventListener('loadeddata', () => setVideoLoaded(true));
    }
  }, []);

  const getCanvasCoords = (e: React.MouseEvent<HTMLCanvasElement> | MouseEvent) => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return { x: 0, y: 0 };

    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY,
    };
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (readOnly) return;
    if (e.key === 'Escape') {
      if (isDrawing) {
        if (currentPolygon.length >= 3) {
          // Close polygon
          finishPolygon();
        } else {
          // Cancel drawing
          setCurrentPolygon([]);
          setIsDrawing(false);
        }
      } else if (selectedPolygonIndex !== null) {
        setSelectedPolygonIndex(null);
        setSelectedPointIndex(null);
      }
    } else if (e.key === 'Enter' && isDrawing && currentPolygon.length >= 3) {
      finishPolygon();
    } else if (e.key === 'Delete' || e.key === 'Backspace') {
      if (selectedPolygonIndex !== null && selectedPointIndex !== null) {
        // Delete point
        removePoint(selectedPolygonIndex, selectedPointIndex);
      } else if (selectedPolygonIndex !== null) {
        // Delete entire polygon
        removePolygon(selectedPolygonIndex);
      }
    } else if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
      e.preventDefault();
      if (e.shiftKey) {
        redo();
      } else {
        undo();
      }
    }
  };

  const finishPolygon = () => {
    if (currentPolygon.length >= 3) {
      // Close the polygon by adding first point at end (for rendering)
      const closedPolygon = [...currentPolygon, currentPolygon[0]];
      setZone(prev => [...prev, closedPolygon]);
    }
    setCurrentPolygon([]);
    setIsDrawing(false);
  };

  const removePoint = (polygonIndex: number, pointIndex: number) => {
    setZone(prev => {
      const newZone = prev.map((polygon, i) => {
        if (i === polygonIndex) {
          const newPolygon = polygon.filter((_, idx) => idx !== pointIndex);
          // Keep polygon closed if it has enough points
          if (newPolygon.length > 3 && newPolygon[0].x === newPolygon[newPolygon.length - 1].x && newPolygon[0].y === newPolygon[newPolygon.length - 1].y) {
            // Already closed
          } else if (newPolygon.length >= 3) {
            newPolygon.push({ ...newPolygon[0] });
          }
          return newPolygon;
        }
        return polygon;
      }).filter(p => p.length >= 4); // At least 3 unique points + closing point
      return newZone;
    });
    setSelectedPointIndex(null);
  };

  const removePolygon = (polygonIndex: number) => {
    setZone(prev => prev.filter((_, i) => i !== polygonIndex));
    setSelectedPolygonIndex(null);
  };

  const updatePoint = (polygonIndex: number, pointIndex: number, x: number, y: number) => {
    setZone(prev => {
      const newZone = prev.map((polygon, i) => {
        if (i === polygonIndex) {
          const newPolygon = [...polygon];
          newPolygon[pointIndex] = { x, y };
          // Also update closing point if it's the last point
          if (pointIndex === 0 && newPolygon.length > 0) {
            newPolygon[newPolygon.length - 1] = { x, y };
          } else if (pointIndex === newPolygon.length - 1 && newPolygon.length > 0) {
            newPolygon[0] = { x, y };
          }
          return newPolygon;
        }
        return polygon;
      });
      return newZone;
    });
  };

  const undo = () => {
    if (historyIndex > 0) {
      const newIndex = historyIndex - 1;
      setZone(history[newIndex].map(p => [...p]));
      setHistoryIndex(newIndex);
    }
  };

  const redo = () => {
    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1;
      setZone(history[newIndex].map(p => [...p]));
      setHistoryIndex(newIndex);
    }
  };

  const clearAll = () => {
    setZone([]);
    setCurrentPolygon([]);
    setIsDrawing(false);
    setSelectedPolygonIndex(null);
    setSelectedPointIndex(null);
  };

  const toggleFullscreen = async () => {
    const container = containerRef.current;
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

  // Draw on canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    const video = document.querySelector('video');
    if (!canvas || !video) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const draw = () => {
      // Clear canvas
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw video frame as background (optional, for reference)
      // ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Draw existing polygons
      zone.forEach((polygon, polyIndex) => {
        if (polygon.length < 3) return;

        const isSelected = polyIndex === selectedPolygonIndex;
        ctx.beginPath();
        ctx.moveTo(polygon[0].x, polygon[0].y);
        for (let i = 1; i < polygon.length; i++) {
          ctx.lineTo(polygon[i].x, polygon[i].y);
        }
        ctx.closePath();

        // Fill
        ctx.fillStyle = isSelected ? 'rgba(59, 130, 246, 0.3)' : 'rgba(34, 197, 94, 0.2)';
        ctx.fill();

        // Stroke
        ctx.strokeStyle = isSelected ? 'rgb(59, 130, 246)' : 'rgb(34, 197, 94)';
        ctx.lineWidth = isSelected ? 3 : 2;
        ctx.stroke();

        // Draw points
        polygon.slice(0, -1).forEach((point, pointIndex) => {
          const isPointSelected = polyIndex === selectedPolygonIndex && pointIndex === selectedPointIndex;
          ctx.beginPath();
          ctx.arc(point.x, point.y, isPointSelected ? 8 : 6, 0, Math.PI * 2);
          ctx.fillStyle = isPointSelected ? 'rgb(239, 68, 68)' : isSelected ? 'rgb(59, 130, 246)' : 'rgb(34, 197, 94)';
          ctx.fill();
          ctx.strokeStyle = 'white';
          ctx.lineWidth = 2;
          ctx.stroke();

          // Point number
          ctx.fillStyle = 'white';
          ctx.font = '12px monospace';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(`${pointIndex + 1}`, point.x, point.y);
        });
      });

      // Draw current polygon being drawn
      if (isDrawing && currentPolygon.length > 0) {
        ctx.beginPath();
        ctx.moveTo(currentPolygon[0].x, currentPolygon[0].y);
        for (let i = 1; i < currentPolygon.length; i++) {
          ctx.lineTo(currentPolygon[i].x, currentPolygon[i].y);
        }
        // Line to mouse cursor (handled by mousemove)
        ctx.strokeStyle = 'rgb(239, 68, 68)';
        ctx.lineWidth = 2;
        ctx.setLineDash([5, 5]);
        ctx.stroke();
        ctx.setLineDash([]);

        // Draw points
        currentPolygon.forEach((point) => {
          ctx.beginPath();
          ctx.arc(point.x, point.y, 6, 0, Math.PI * 2);
          ctx.fillStyle = 'rgb(239, 68, 68)';
          ctx.fill();
          ctx.strokeStyle = 'white';
          ctx.lineWidth = 2;
          ctx.stroke();
        });
      }

      requestAnimationFrame(draw);
    };

    // Set canvas size to match video
    const resizeCanvas = () => {
      if (video.videoWidth && video.videoHeight) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
      } else {
        canvas.width = width;
        canvas.height = height;
      }
    };

    resizeCanvas();
    video.addEventListener('resize', resizeCanvas);
    draw();

    return () => {
      video.removeEventListener('resize', resizeCanvas);
    };
  }, [zone, currentPolygon, isDrawing, selectedPolygonIndex, selectedPointIndex, width, height]);

  // Handle point dragging
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let isDragging = false;
    let dragPolygonIndex = -1;
    let dragPointIndex = -1;

    const handleMouseDown = (e: MouseEvent) => {
      if (readOnly || selectedPolygonIndex === null || selectedPointIndex === null) return;

      const { x, y } = getCanvasCoords(e);
      const polygon = zone[selectedPolygonIndex];
      if (!polygon) return;

      const point = polygon[selectedPointIndex];
      if (!point) return;

      const dist = Math.hypot(x - point.x, y - point.y);
      if (dist < 15) {
        isDragging = true;
        dragPolygonIndex = selectedPolygonIndex;
        dragPointIndex = selectedPointIndex;
      }
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      const { x, y } = getCanvasCoords(e);
      // Clamp to canvas bounds
      const clampedX = Math.max(0, Math.min(canvas.width, x));
      const clampedY = Math.max(0, Math.min(canvas.height, y));
      updatePoint(dragPolygonIndex, dragPointIndex, clampedX, clampedY);
    };

    const handleMouseUp = () => {
      isDragging = false;
    };

    canvas.addEventListener('mousedown', handleMouseDown);
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      canvas.removeEventListener('mousedown', handleMouseDown);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [zone, selectedPolygonIndex, selectedPointIndex, readOnly, updatePoint]);

  // Keyboard handler
  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown, isDrawing, currentPolygon, selectedPolygonIndex, history, historyIndex]);

  if (!videoLoaded && !readOnly) {
    return (
      <div ref={containerRef} className={`relative ${className}`} style={{ width, height }}>
        <VideoPlayer
          src={src}
          type={type}
          width={width}
          height={height}
          muted={true}
          controls={true}
          onLoad={() => setVideoLoaded(true)}
        />
        <div className="absolute inset-0 flex items-center justify-center bg-black/50 z-10">
          <div className="text-center text-white">
            <div className="w-10 h-10 mx-auto mb-4 animate-spin border-4 border-primary border-t-transparent rounded-full" />
            <p>{t('loadingStream') || 'Loading stream...'}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className={`relative ${className}`} style={{ width, height }}>
      <VideoPlayer
        src={src}
        type={type}
        width={width}
        height={height}
        muted={true}
        controls={true}
        onLoad={() => setVideoLoaded(true)}
      />
      <canvas
        ref={canvasRef}
        className="absolute top-0 left-0 pointer-events-none"
        style={{ width: '100%', height: '100%', touchAction: 'none' }}
        onClick={(e) => {
          if (readOnly || !isDrawing) return;
          const { x, y } = getCanvasCoords(e);
          setCurrentPolygon(prev => [...prev, { x, y }]);
        }}
      />
      {!readOnly && (
        <div className="absolute bottom-4 left-4 right-4 flex flex-wrap gap-2 justify-center pointer-events-auto">
          {!isDrawing ? (
            <Button
              variant={zone.length > 0 ? 'secondary' : 'default'}
              size="sm"
              onClick={() => setIsDrawing(true)}
              className="gap-1"
            >
              <Edit className="w-4 h-4" />
              {isDrawing ? t('drawing') : zone.length > 0 ? t('editZone') : t('drawZone')}
            </Button>
          ) : (
            <>
              <Button
                variant="default"
                size="sm"
                onClick={finishPolygon}
                disabled={currentPolygon.length < 3}
                className="gap-1"
              >
                <Save className="w-4 h-4" />
                {t('finishPolygon')} ({currentPolygon.length}/3+)
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => { setCurrentPolygon([]); setIsDrawing(false); }}
                className="gap-1"
              >
                <X className="w-4 h-4" />
                {t('cancel')}
              </Button>
            </>
          )}
          {zone.length > 0 && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={undo}
                disabled={historyIndex === 0}
                className="gap-1"
              >
                <Undo2 className="w-4 h-4" />
                {t('undo')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={redo}
                disabled={historyIndex >= history.length - 1}
                className="gap-1"
              >
                <RotateCcw className="w-4 h-4" />
                {t('redo')}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={clearAll}
                className="gap-1"
              >
                <Trash2 className="w-4 h-4" />
                {t('clearAll')}
              </Button>
            </>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={toggleFullscreen}
            className="gap-1 ml-auto"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            {isFullscreen ? t('exitFullscreen') : t('fullscreen')}
          </Button>
        </div>
      )}

      {/* Instructions overlay */}
      {!readOnly && isDrawing && (
        <div className="absolute top-4 left-4 right-4 pointer-events-none">
          <Card className="bg-primary/90 text-primary-foreground max-w-md mx-auto">
            <CardContent className="p-3 text-sm">
              <p className="font-medium">{t('drawInstructions') || 'Click to add points. Minimum 3 points to create a polygon.'}</p>
              <p className="text-xs opacity-80 mt-1">
                {t('enterToFinish')} Enter {t('toFinish')}, {t('escToCancel')} Esc {t('toCancel')}, {t('deleteToRemove')} Del {t('toRemove')}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Selected polygon info */}
      {selectedPolygonIndex !== null && zone[selectedPolygonIndex] && (
        <div className="absolute top-4 right-4 pointer-events-none">
          <Card className="bg-gray-900/90 text-white max-w-xs">
            <CardContent className="p-3 text-sm">
              <p className="font-medium">{t('polygon')} #{selectedPolygonIndex + 1}</p>
              <p>{zone[selectedPolygonIndex].length - 1} {t('points')}</p>
              {selectedPointIndex !== null && (
                <p className="text-xs opacity-70">
                  {t('point')} #{selectedPointIndex + 1}: {zone[selectedPolygonIndex][selectedPointIndex]?.x?.toFixed(0)}, {zone[selectedPolygonIndex][selectedPointIndex]?.y?.toFixed(0)}
                </p>
              )}
              <p className="text-xs opacity-50 mt-2">{t('dragToMove')} / {t('delToDelete')}</p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
};

// Zone data helpers
export const zoneToString = (zone: Point[][]): string => {
  return JSON.stringify(zone);
};

export const zoneFromString = (str: string): Point[][] => {
  try {
    const parsed = JSON.parse(str);
    if (Array.isArray(parsed)) {
      return parsed.map((polygon: any) => 
        Array.isArray(polygon) ? polygon.map((p: any) => ({ x: Number(p.x), y: Number(p.y) })) : []
      ).filter((p: Point[]) => p.length >= 4);
    }
  } catch {}
  return [];
};

export const normalizeZone = (zone: Point[][], videoWidth: number, videoHeight: number): Point[][] => {
  return zone.map(polygon => 
    polygon.map(point => ({
      x: point.x / videoWidth,
      y: point.y / videoHeight,
    }))
  );
};

export const denormalizeZone = (zone: Point[][], videoWidth: number, videoHeight: number): Point[][] => {
  return zone.map(polygon => 
    polygon.map(point => ({
      x: point.x * videoWidth,
      y: point.y * videoHeight,
    }))
  );
};