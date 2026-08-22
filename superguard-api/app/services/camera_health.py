"""
Camera health monitoring and IP discovery service.
Runs periodic keep-alive checks and auto-rediscovers IPs for cameras.
Sends alerts if camera is offline for 3+ minutes.
"""
import asyncio
import subprocess
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass


@dataclass
class CameraConfig:
    """Camera configuration extracted from DB."""
    id: str
    name: str
    type: str
    stream_url: str
    username: str = ""
    password: str = ""
    mac: str = ""
    onvif_profile: str = ""


class CameraDiscovery:
    """Handles IP discovery and health checks for cameras."""

    @staticmethod
    def discover_ip_by_mac(mac: str) -> Optional[str]:
        """Discover current IP address of device by MAC address from ARP/neighbor cache."""
        if not mac:
            return None

        mac_lower = mac.lower()

        try:
            result = subprocess.run(
                ['ip', 'neigh', 'show'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if 'lladdr' in line:
                        parts = line.split()
                        try:
                            lladdr_idx = parts.index('lladdr')
                            if lladdr_idx + 1 < len(parts):
                                found_mac = parts[lladdr_idx + 1]
                                ip_addr = parts[0]
                                if found_mac.lower() == mac_lower:
                                    return ip_addr
                        except ValueError:
                            pass
        except Exception:
            pass

        try:
            with open('/proc/net/arp', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4:
                        ip_addr = parts[0]
                        hw_addr = parts[3]
                        if hw_addr.lower() == mac_lower:
                            return ip_addr
        except Exception:
            pass

        return None

    @staticmethod
    def ping_host(ip: str, timeout: int = 2) -> bool:
        """Ping a host to check if it's reachable."""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', str(timeout), ip],
                capture_output=True,
                timeout=timeout + 2
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    async def test_camera_connection(config: CameraConfig, timeout: int = 5) -> bool:
        """Test camera connection via RTSP/HTTP/ONVIF."""
        import cv2
        
        def _test_sync():
            try:
                # Try OpenCV to open stream
                cap = cv2.VideoCapture(config.stream_url)
                cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout * 1000)
                cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout * 1000)
                
                ret, frame = cap.read()
                cap.release()
                
                if ret and frame is not None:
                    return True
            except Exception:
                pass
            
            # Fallback: try to connect to the IP
            if config.stream_url:
                from urllib.parse import urlparse
                parsed = urlparse(config.stream_url)
                ip = parsed.hostname
                if ip:
                    return CameraDiscovery.ping_host(ip, timeout)
            
            return False
        
        # Run in thread pool to avoid blocking event loop
        try:
            return await asyncio.wait_for(asyncio.to_thread(_test_sync), timeout=timeout + 10)
        except asyncio.TimeoutError:
            return False
        except Exception:
            return False

    @classmethod
    async def check_and_rediscover(cls, config: CameraConfig) -> Dict[str, Any]:
        """
        Check camera connectivity, rediscover IP via MAC if needed.

        Returns dict with:
        - online: bool
        - ip_changed: bool
        - new_ip: str or None
        - method: 'ping' | 'stream' | 'rediscovered'
        """
        # Extract IP from stream URL
        from urllib.parse import urlparse
        parsed = urlparse(config.stream_url)
        current_ip = parsed.hostname or config.stream_url
        
        # First try to open stream
        if await cls.test_camera_connection(config):
            return {
                'online': True,
                'ip_changed': False,
                'new_ip': None,
                'method': 'stream'
            }

        # Not reachable - try ARP discovery via MAC
        new_ip = cls.discover_ip_by_mac(config.mac)

        if new_ip and new_ip != current_ip:
            # Found new IP, test it with updated stream URL
            old_stream_url = config.stream_url
            # Update stream URL with new IP
            new_stream_url = old_stream_url.replace(current_ip, new_ip)
            config.stream_url = new_stream_url
            
            if await cls.test_camera_connection(config):
                return {
                    'online': True,
                    'ip_changed': True,
                    'new_ip': new_ip,
                    'method': 'rediscovered',
                    'old_ip': current_ip,
                    'new_stream_url': new_stream_url
                }
            else:
                # Revert if new one doesn't work
                config.stream_url = old_stream_url

        # Still offline
        return {
            'online': False,
            'ip_changed': False,
            'new_ip': None,
            'method': 'failed'
        }


class CameraHealthMonitor:
    """Background monitor that checks all cameras every minute.

    Tracks consecutive offline checks and sends alerts
    after 3 minutes (3 failed checks) of being unreachable.
    """

    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._offline_tracking: Dict[str, Dict[str, Any]] = {}

    async def start(self, interval: int = 60):
        """Start the periodic health check."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval))

    async def stop(self):
        """Stop the monitor."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self, interval: int):
        """Main monitoring loop."""
        while self._running:
            try:
                await self.check_all_cameras()
            except Exception as e:
                print(f"[CameraHealthMonitor] Error in check loop: {e}")

            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    async def check_all_cameras(self):
        """Check all cameras across all sites."""
        from app.models import Camera, Site
        from sqlalchemy import select

        async for db in self.db_session_factory():
            try:
                result = await db.execute(
                    select(Camera).where(Camera.is_enabled == True)
                )
                cameras = result.scalars().all()

                for camera in cameras:
                    await self._check_single_camera(db, camera)

                await db.commit()

            except Exception as e:
                print(f"[CameraHealthMonitor] Error checking cameras: {e}")
                await db.rollback()

    async def _check_single_camera(self, db, camera) -> Dict[str, Any]:
        """Check a single camera and update its status in DB."""
        cfg = camera.config or {}

        config = CameraConfig(
            id=camera.id,
            name=camera.name,
            type=camera.type.value,
            stream_url=camera.stream_url,
            username=cfg.get('username', ''),
            password=cfg.get('password', ''),
            mac=cfg.get('mac', ''),
            onvif_profile=cfg.get('onvif_profile', ''),
        )

        # Check and potentially rediscover
        result = await CameraDiscovery.check_and_rediscover(config)

        # Update camera in DB
        camera.is_online = result['online']
        camera.last_seen = datetime.utcnow() if result['online'] else camera.last_seen

        # If IP/stream URL changed, update config in DB
        if result.get('ip_changed') and result.get('new_stream_url'):
            new_config = dict(cfg)
            new_config['stream_url'] = result['new_stream_url']
            camera.config = new_config
            print(f"[CameraHealthMonitor] {camera.name}: Stream URL updated -> {result['new_stream_url']}")

        # Track offline state and send alerts if needed
        await self._update_offline_tracking(camera.id, result['online'], camera.name, cfg, db)

        return result

    async def _update_offline_tracking(self, camera_id: str, online: bool, name: str = "", config: Optional[Dict] = None, db=None):
        """Track consecutive offline checks and send alert after 3 minutes."""
        now = datetime.utcnow()

        async with self._lock:
            if camera_id not in self._offline_tracking:
                self._offline_tracking[camera_id] = {
                    'offline_since': None,
                    'alert_sent': False,
                    'consecutive_failures': 0
                }

            tracking = self._offline_tracking[camera_id]

            if online:
                if tracking['offline_since'] is not None:
                    print(f"[CameraHealthMonitor] {name or camera_id}: Back online after {tracking['consecutive_failures']} failed checks")
                tracking['offline_since'] = None
                tracking['alert_sent'] = False
                tracking['consecutive_failures'] = 0
            else:
                tracking['consecutive_failures'] += 1

                if tracking['offline_since'] is None:
                    tracking['offline_since'] = now

                # Check if we should send alert (3 consecutive failures = 3 minutes)
                if tracking['consecutive_failures'] >= 3 and not tracking['alert_sent']:
                    tracking['alert_sent'] = True
                    asyncio.create_task(self._send_camera_lost_alert(camera_id, name, config, db))

    async def _send_camera_lost_alert(self, camera_id: str, name: str, config: Optional[Dict], db):
        """Send Telegram alert when camera is lost for 3+ minutes."""
        try:
            from app.models import Camera, Notifier
            from sqlalchemy import select

            async for db_session in self.db_session_factory():
                result = await db_session.execute(
                    select(Camera).where(Camera.id == camera_id)
                )
                camera = result.scalar_one_or_none()
                if not camera:
                    return

                result = await db_session.execute(
                    select(Notifier).where(
                        Notifier.site_id == camera.site_id,
                        Notifier.is_enabled == True,
                        Notifier.type == 'telegram'
                    )
                )
                notifiers = result.scalars().all()

                for notifier in notifiers:
                    try:
                        await self._send_telegram_alert(notifier, camera, name)
                    except Exception as e:
                        print(f"[CameraHealthMonitor] Failed to send Telegram alert: {e}")

                break

        except Exception as e:
            print(f"[CameraHealthMonitor] Error sending alert for {camera_id}: {e}")

    async def _send_telegram_alert(self, notifier: 'Notifier', camera: 'Camera', name: str):
        """Send Telegram message via Bot API."""
        import requests

        bot_token = notifier.config.get('bot_token')
        chat_id = notifier.config.get('chat_id')

        if not bot_token or not chat_id:
            return

        message = (
            f"🚨 <b>CAMERA LOST</b> 🚨\n\n"
            f"<b>Camera:</b> {name} ({camera.id[:8]}...)\n"
            f"<b>Site:</b> {camera.site_id[:8]}...\n"
            f"<b>Stream URL:</b> {camera.stream_url}\n"
            f"<b>MAC:</b> {camera.config.get('mac', 'unknown')}\n"
            f"<b>Offline for:</b> 3+ minutes (3 consecutive failed checks)\n\n"
            f"⚠️ <b>Possible tampering detected</b> - camera feed may have been deliberately\n"
            f"disconnected to disable security. Please investigate immediately."
        )

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                },
                timeout=10
            )
            if response.status_code == 200:
                print(f"[CameraHealthMonitor] Telegram alert sent for {name}")
            else:
                print(f"[CameraHealthMonitor] Telegram alert failed: {response.text}")
        except Exception as e:
            print(f"[CameraHealthMonitor] Telegram send error: {e}")

    async def test_camera(self, camera_id: str) -> Dict[str, Any]:
        """Test a specific camera (called from API endpoint)."""
        from app.models import Camera
        from sqlalchemy import select

        async for db in self.db_session_factory():
            result = await db.execute(
                select(Camera).where(Camera.id == camera_id)
            )
            camera = result.scalar_one_or_none()

            if not camera:
                return {'online': False, 'error': 'Camera not found'}

            check_result = await self._check_single_camera(db, camera)
            await db.commit()
            return check_result