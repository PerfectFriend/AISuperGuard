"""
Actuator health monitoring and IP discovery service.
Runs periodic keep-alive checks and auto-rediscovers IPs via MAC/ARP.
Sends Telegram alerts if actuator is offline for 3+ minutes.
"""
import asyncio
import subprocess
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass

try:
    import tinytuya
except ImportError:
    tinytuya = None

from app.core.encryption import get_encryption


@dataclass
class ActuatorConfig:
    """Actuator configuration extracted from DB."""
    id: str
    name: str
    type: str
    ip: str
    device_id: str
    local_key: str
    mac: str
    port: int = 6668
    version: float = 3.4


class ActuatorDiscovery:
    """Handles IP discovery and health checks for Tuya actuators."""
    
    @staticmethod
    def discover_ip_by_mac(mac: str) -> Optional[str]:
        """
        Discover current IP address of device by MAC address from ARP/neighbor cache.
        
        Uses `ip neigh` (Linux) or falls back to /proc/net/arp.
        """
        if not mac:
            return None
        
        mac_lower = mac.lower()
        
        try:
            # Try `ip neigh show` first (modern Linux)
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
        
        # Fallback to /proc/net/arp
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
    def test_tuya_connection(config: ActuatorConfig, timeout: int = 5) -> bool:
        """Test Tuya actuator connection via tinytuya."""
        if not tinytuya:
            # Fallback to ping if tinytuya not available
            return ActuatorDiscovery.ping_host(config.ip, timeout)
        
        try:
            device = tinytuya.OutletDevice(
                dev_id=config.device_id,
                address=config.ip,
                local_key=config.local_key,
                version=config.version
            )
            device.set_socketPersistent(False)
            device.set_socketTimeout(timeout)
            
            # Try to get status - this will fail if unreachable
            status = device.status()
            return status is not None and 'dps' in status
        except Exception:
            return False

    @staticmethod
    def get_tuya_status(config: ActuatorConfig, timeout: int = 5) -> Optional[bool]:
        """Get actual on/off status from Tuya actuator."""
        if not tinytuya:
            return None
        
        try:
            device = tinytuya.OutletDevice(
                dev_id=config.device_id,
                address=config.ip,
                local_key=config.local_key,
                version=config.version
            )
            device.set_socketPersistent(False)
            device.set_socketTimeout(timeout)
            
            status = device.status()
            if status and 'dps' in status:
                # DPS '1' is typically the switch state
                return bool(status['dps'].get('1', False))
            return None
        except Exception:
            return None

    @staticmethod
    def set_tuya_state(config: ActuatorConfig, turn_on: bool, timeout: int = 5) -> bool:
        """Set Tuya actuator on/off state."""
        if not tinytuya:
            return False
        
        try:
            device = tinytuya.OutletDevice(
                dev_id=config.device_id,
                address=config.ip,
                local_key=config.local_key,
                version=config.version
            )
            device.set_socketPersistent(False)
            device.set_socketTimeout(timeout)
            
            # DPS '1' is typically the switch
            result = device.set_status(turn_on, switch=1)
            return result is not None
        except Exception:
            return False
    
    @classmethod
    def check_and_rediscover(cls, config: ActuatorConfig) -> Dict[str, Any]:
        """
        Check actuator connectivity, rediscover IP via MAC if needed.
        
        Returns dict with:
        - online: bool
        - ip_changed: bool
        - new_ip: str or None
        - method: 'ping' | 'tuya' | 'rediscovered'
        """
        # First try ping (fast)
        if cls.ping_host(config.ip):
            # Host responds to ping, try Tuya protocol
            if cls.test_tuya_connection(config):
                return {
                    'online': True,
                    'ip_changed': False,
                    'new_ip': None,
                    'method': 'tuya'
                }
        
        # Not reachable - try ARP discovery via MAC
        new_ip = cls.discover_ip_by_mac(config.mac)
        
        if new_ip and new_ip != config.ip:
            # Found new IP, test it
            old_ip = config.ip
            config.ip = new_ip
            
            if cls.test_tuya_connection(config):
                return {
                    'online': True,
                    'ip_changed': True,
                    'new_ip': new_ip,
                    'method': 'rediscovered',
                    'old_ip': old_ip
                }
            else:
                # Revert IP if new one doesn't work
                config.ip = old_ip
        
        # Still offline
        return {
            'online': False,
            'ip_changed': False,
            'new_ip': None,
            'method': 'failed'
        }


class ActuatorHealthMonitor:
    """Background monitor that checks all actuators every minute.
    
    Tracks consecutive offline checks and sends Telegram alerts
    after 3 minutes (3 failed checks) of being unreachable.
    """
    
    def __init__(self, db_session_factory):
        self.db_session_factory = db_session_factory
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._lock = threading.Lock()
        # Track offline state: actuator_id -> {'offline_since': datetime, 'alert_sent': bool, 'consecutive_failures': int}
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
                await self.check_all_actuators()
            except Exception as e:
                print(f"[ActuatorHealthMonitor] Error in check loop: {e}")
            
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
    
    async def check_all_actuators(self):
        """Check all actuators across all sites."""
        from app.models import Actuator, Site
        from sqlalchemy import select
        
        async for db in self.db_session_factory():
            try:
                # Get all enabled actuators
                result = await db.execute(
                    select(Actuator).where(Actuator.is_enabled == True)
                )
                actuators = result.scalars().all()
                
                for actuator in actuators:
                    await self._check_single_actuator(db, actuator)
                
                await db.commit()
                
            except Exception as e:
                print(f"[ActuatorHealthMonitor] Error checking actuators: {e}")
                await db.rollback()
    
    async def _check_single_actuator(self, db, actuator) -> Dict[str, Any]:
        """Check a single actuator and update its status in DB."""
        # Extract and decrypt config
        cfg = actuator.config or {}
        encryption = get_encryption()
        cfg = encryption.decrypt_dict(cfg)
        
        # Only handle Tuya actuators for now
        if actuator.type.value not in ('tuya', 'tinytuya'):
            # For other types, just ping
            ip = cfg.get('ip')
            online = False
            if ip:
                online = ActuatorDiscovery.ping_host(ip)
                actuator.is_online = online
                actuator.last_seen = datetime.utcnow() if online else actuator.last_seen
            
            # Track offline state
            await self._update_offline_tracking(actuator.id, online)
            return {'online': online}
        
        config = ActuatorConfig(
            id=actuator.id,
            name=actuator.name,
            type=actuator.type.value,
            ip=cfg.get('ip', ''),
            device_id=cfg.get('device_id', ''),
            local_key=cfg.get('local_key', ''),
            mac=cfg.get('mac', ''),
            port=cfg.get('port', 6668),
            version=cfg.get('version', 3.4),
        )
        
        # Check and potentially rediscover
        result = ActuatorDiscovery.check_and_rediscover(config)
        
        # Update actuator in DB
        actuator.is_online = result['online']
        actuator.last_seen = datetime.utcnow() if result['online'] else actuator.last_seen
        
        # If IP changed, update config in DB (encrypt before saving)
        if result.get('ip_changed') and result.get('new_ip'):
            encryption = get_encryption()
            new_config = dict(cfg)
            new_config['ip'] = result['new_ip']
            new_config = encryption.encrypt_dict(new_config)
            actuator.config = new_config
            print(f"[ActuatorHealthMonitor] {actuator.name}: IP updated {result.get('old_ip')} -> {result['new_ip']}")
        
        # Track offline state and send alerts if needed
        await self._update_offline_tracking(actuator.id, result['online'], actuator.name, cfg, db)
        
        return result
    
    async def _update_offline_tracking(self, actuator_id: str, online: bool, name: str = "", config: Dict = None, db=None):
        """Track consecutive offline checks and send alert after 3 minutes."""
        now = datetime.utcnow()
        
        with self._lock:
            if actuator_id not in self._offline_tracking:
                self._offline_tracking[actuator_id] = {
                    'offline_since': None,
                    'alert_sent': False,
                    'consecutive_failures': 0
                }
            
            tracking = self._offline_tracking[actuator_id]
            
            if online:
                # Actuator is back online - reset tracking
                if tracking['offline_since'] is not None:
                    print(f"[ActuatorHealthMonitor] {name or actuator_id}: Back online after {tracking['consecutive_failures']} failed checks")
                tracking['offline_since'] = None
                tracking['alert_sent'] = False
                tracking['consecutive_failures'] = 0
            else:
                # Actuator is offline
                tracking['consecutive_failures'] += 1
                
                if tracking['offline_since'] is None:
                    tracking['offline_since'] = now
                
                # Check if we should send alert (3 consecutive failures = 3 minutes)
                if tracking['consecutive_failures'] >= 3 and not tracking['alert_sent']:
                    tracking['alert_sent'] = True
                    # Send alert asynchronously
                    asyncio.create_task(self._send_actuator_lost_alert(actuator_id, name, config, db))
    
    async def _send_actuator_lost_alert(self, actuator_id: str, name: str, config: Dict, db):
        """Send Telegram alert when actuator is lost for 3+ minutes."""
        try:
            from app.models import Actuator, Notifier
            from sqlalchemy import select
            
            # Find enabled Telegram notifiers for this actuator's site
            async for db_session in self.db_session_factory():
                # Get the actuator to find its site
                result = await db_session.execute(
                    select(Actuator).where(Actuator.id == actuator_id)
                )
                actuator = result.scalar_one_or_none()
                if not actuator:
                    return
                
                # Find Telegram notifiers for this site
                result = await db_session.execute(
                    select(Notifier).where(
                        Notifier.site_id == actuator.site_id,
                        Notifier.is_enabled == True,
                        Notifier.type == 'telegram'
                    )
                )
                notifiers = result.scalars().all()
                
                for notifier in notifiers:
                    try:
                        await self._send_telegram_alert(notifier, actuator, name)
                    except Exception as e:
                        print(f"[ActuatorHealthMonitor] Failed to send Telegram alert: {e}")
                
                break  # Only need one session
                
        except Exception as e:
            print(f"[ActuatorHealthMonitor] Error sending alert for {actuator_id}: {e}")
    
    async def _send_telegram_alert(self, notifier: 'Notifier', actuator: 'Actuator', name: str):
        """Send Telegram message via Bot API."""
        import requests
        
        bot_token = notifier.config.get('bot_token')
        chat_id = notifier.config.get('chat_id')
        
        if not bot_token or not chat_id:
            return
        
        message = (
            f"🚨 <b>ACTUATOR LOST</b> 🚨\n\n"
            f"<b>Actuator:</b> {name} ({actuator.id[:8]}...)\n"
            f"<b>Site:</b> {actuator.site_id[:8]}...\n"
            f"<b>Last IP:</b> {actuator.config.get('ip', 'unknown')}\n"
            f"<b>MAC:</b> {actuator.config.get('mac', 'unknown')}\n"
            f"<b>Offline for:</b> 3+ minutes (3 consecutive failed checks)\n\n"
            f"⚠️ <b>Possible tampering detected</b> - someone may have deliberately\n"
            f"disconnected the actuator to disable security. Please investigate immediately."
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
                print(f"[ActuatorHealthMonitor] Telegram alert sent for {name}")
            else:
                print(f"[ActuatorHealthMonitor] Telegram alert failed: {response.text}")
        except Exception as e:
            print(f"[ActuatorHealthMonitor] Telegram send error: {e}")
    
    async def test_actuator(self, actuator_id: str) -> Dict[str, Any]:
        """Test a specific actuator (called from API endpoint)."""
        from app.models import Actuator
        from sqlalchemy import select
        
        async for db in self.db_session_factory():
            result = await db.execute(
                select(Actuator).where(Actuator.id == actuator_id)
            )
            actuator = result.scalar_one_or_none()
            
            if not actuator:
                return {'online': False, 'error': 'Actuator not found'}
            
            check_result = await self._check_single_actuator(db, actuator)
            await db.commit()
            return check_result