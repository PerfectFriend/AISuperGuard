"""
SuperGuard Core - Tuya Cloud Actuator Plugin

Tuya smart plug control via Tuya Cloud API (fallback when local fails).
"""

import asyncio
import logging
import time
import hmac
import hashlib
import json
from typing import Optional, Dict, Any

import aiohttp

from superguard_core.core.plugins import ActuatorPlugin, ActuatorState, PluginConfig
from superguard_core.core.database import Actuator


logger = logging.getLogger(__name__)


class TuyaCloudActuatorPlugin(ActuatorPlugin):
    """Tuya Cloud API actuator plugin."""
    
    name = "tuya_cloud"
    version = "1.0.0"
    plugin_type = "actuator"
    description = "Tuya smart plug via Tuya Cloud API"
    author = "SuperGuard Team"
    
    BASE_URL = "https://openapi.tuyaeu.com"  # EU region, configurable
    
    def __init__(self, config: PluginConfig, event_bus):
        super().__init__(config, event_bus)
        self._actuator: Optional[Actuator] = None
        self._client_id: str = ""
        self._client_secret: str = ""
        self._device_id: str = ""
        self._region: str = "eu"
        self._access_token: Optional[str] = None
        self._token_expires: float = 0
        self._current_state: bool = False
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self, actuator: Actuator) -> None:
        """Initialize Tuya Cloud client."""
        self._actuator = actuator
        
        # Get credentials from actuator config
        self._client_id = actuator.config.get("client_id", "")
        self._client_secret = actuator.config.get("client_secret", "")
        self._device_id = actuator.config.get("device_id", "")
        self._region = actuator.config.get("region", "eu")
        
        if not all([self._client_id, self._client_secret, self._device_id]):
            raise ValueError("Tuya Cloud requires client_id, client_secret, and device_id")
        
        # Set base URL based on region
        region_urls = {
            "us": "https://openapi.tuyaus.com",
            "eu": "https://openapi.tuyaeu.com",
            "cn": "https://openapi.tuyacn.com",
            "in": "https://openapi.tuyain.com",
        }
        self.BASE_URL = region_urls.get(self._region, self.BASE_URL)
        
        # Create HTTP session
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"Content-Type": "application/json"}
        )
        
        # Get initial token
        await self._get_access_token()
        
        # Get initial state
        try:
            await self._update_state()
        except Exception as e:
            logger.warning(f"Failed to get initial state for Tuya Cloud {actuator.id}: {e}")
        
        await self._set_status(self.PluginStatus.LOADED)
        self._initialized = True
        
        logger.info(f"Tuya Cloud actuator {actuator.id} ({actuator.name}) initialized")
    
    async def _get_access_token(self) -> str:
        """Get or refresh access token."""
        now = time.time()
        
        if self._access_token and now < self._token_expires - 60:
            return self._access_token
        
        # Generate signature
        timestamp = str(int(now * 1000))
        string_to_sign = f"{self._client_id}{timestamp}"
        
        sign = hmac.new(
            self._client_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().upper()
        
        url = f"{self.BASE_URL}/v1.0/token?grant_type=1"
        
        headers = {
            "client_id": self._client_id,
            "sign": sign,
            "t": timestamp,
            "sign_method": "HMAC-SHA256",
        }
        
        async with self._session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Token request failed: {resp.status}")
            
            data = await resp.json()
            
            if not data.get("success"):
                raise RuntimeError(f"Token error: {data.get('msg')}")
            
            self._access_token = data["result"]["access_token"]
            self._token_expires = now + data["result"]["expire_time"]
            
            logger.debug(f"Tuya Cloud token obtained, expires in {data['result']['expire_time']}s")
            
            return self._access_token
    
    async def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        """Make authenticated request to Tuya Cloud API."""
        token = await self._get_access_token()
        
        timestamp = str(int(time.time() * 1000))
        
        # Build string to sign
        body = kwargs.get("json", {})
        body_str = json.dumps(body, separators=(',', ':'), sort_keys=True) if body else ""
        
        string_to_sign = f"{method}\n{hashlib.sha256(body_str.encode()).hexdigest()}\n\n{path}"
        string_to_sign = f"{self._client_id}{token}{timestamp}{string_to_sign}"
        
        sign = hmac.new(
            self._client_secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest().upper()
        
        headers = {
            "client_id": self._client_id,
            "access_token": token,
            "sign": sign,
            "t": timestamp,
            "sign_method": "HMAC-SHA256",
        }
        
        url = f"{self.BASE_URL}{path}"
        
        async with self._session.request(method, url, headers=headers, **kwargs) as resp:
            data = await resp.json()
            
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}: {data}")
            
            if not data.get("success"):
                # Token might be expired, force refresh once
                if data.get("code") in [1010, 1004]:  # Invalid/expired token
                    self._access_token = None
                    return await self._request(method, path, **kwargs)
                raise RuntimeError(f"Tuya Cloud error: {data.get('msg')} (code: {data.get('code')})")
            
            return data
    
    async def turn_on(self) -> ActuatorState:
        """Turn actuator ON."""
        await self._send_command(True)
        self._current_state = True
        return ActuatorState(
            is_on=True,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "tuya_cloud"}
        )
    
    async def turn_off(self) -> ActuatorState:
        """Turn actuator OFF."""
        await self._send_command(False)
        self._current_state = False
        return ActuatorState(
            is_on=False,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "tuya_cloud"}
        )
    
    async def toggle(self) -> ActuatorState:
        """Toggle actuator state."""
        await self._update_state()
        if self._current_state:
            return await self.turn_off()
        else:
            return await self.turn_on()
    
    async def get_state(self) -> ActuatorState:
        """Get current actuator state from cloud."""
        await self._update_state()
        return ActuatorState(
            is_on=self._current_state,
            last_changed=asyncio.get_event_loop().time(),
            metadata={"source": "tuya_cloud"}
        )
    
    async def test_connection(self) -> bool:
        """Test cloud connectivity."""
        try:
            await self._update_state()
            return True
        except Exception:
            return False
    
    async def _send_command(self, state: bool) -> None:
        """Send command to device."""
        commands = {
            "commands": [
                {"code": "switch_1", "value": state}
            ]
        }
        
        await self._request(
            "POST",
            f"/v1.0/devices/{self._device_id}/commands",
            json=commands
        )
        
        logger.info(f"Tuya Cloud {self._actuator.id} turned {'ON' if state else 'OFF'}")
    
    async def _update_state(self) -> None:
        """Update state from cloud."""
        data = await self._request(
            "GET",
            f"/v1.0/devices/{self._device_id}/status"
        )
        
        for status in data.get("result", []):
            if status.get("code") == "switch_1":
                self._current_state = status.get("value", False)
                break
    
    async def shutdown(self) -> None:
        """Shutdown plugin."""
        if self._session:
            await self._session.close()
            self._session = None
        await self._set_status(self.PluginStatus.UNLOADED)