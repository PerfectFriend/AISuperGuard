"""
Encryption utilities for sensitive actuator configuration.
Uses Fernet (AES-128-CBC + HMAC) with key from env.
"""
from cryptography.fernet import Fernet
from typing import Optional, List
from app.core.config import settings


class ActuatorEncryption:
    """Handles encryption/decryption of sensitive actuator fields."""
    
    def __init__(self):
        self._fernet: Optional[Fernet] = None
        self._init_fernet()
    
    def _init_fernet(self):
        """Initialize Fernet from settings.encryption_key."""
        key = settings.encryption_key
        if not key:
            # Generate a new key if not set (for first run)
            key = Fernet.generate_key().decode()
            settings.encryption_key = key
            print(f"[ActuatorEncryption] Generated new encryption key: {key}")
            print("[ActuatorEncryption] Set SG_ENC_KEY=<this_key> in .env for persistence")
        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            raise RuntimeError(f"Invalid encryption key: {e}")
    
    def encrypt(self, value: str) -> str:
        """Encrypt a string value."""
        if not value:
            return value
        assert self._fernet is not None
        return self._fernet.encrypt(value.encode()).decode()
    
    def decrypt(self, encrypted: str) -> str:
        """Decrypt a string value."""
        if not encrypted:
            return encrypted
        assert self._fernet is not None
        try:
            return self._fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            # If decryption fails, return as-is (might be unencrypted legacy value)
            return encrypted
    
    def encrypt_dict(self, config: dict, fields: Optional[List[str]] = None) -> dict:
        """Encrypt specific fields in a config dict."""
        if fields is None:
            fields = ['local_key', 'password', 'device_id', 'ip']
        result = dict(config)
        for field in fields:
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]))
        return result
    
    def decrypt_dict(self, config: dict, fields: Optional[List[str]] = None) -> dict:
        """Decrypt specific fields in a config dict."""
        if fields is None:
            fields = ['local_key', 'password', 'device_id', 'ip']
        result = dict(config)
        for field in fields:
            if field in result and result[field]:
                result[field] = self.decrypt(str(result[field]))
        return result


# Singleton instance
_encryption: Optional[ActuatorEncryption] = None


def get_encryption() -> ActuatorEncryption:
    """Get or create the actuator encryption instance."""
    global _encryption
    if _encryption is None:
        _encryption = ActuatorEncryption()
    return _encryption