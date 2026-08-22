"""
System endpoints - health, version, backup, logs
"""
import time
from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from app.core.config import settings
from app.schemas import SystemHealth
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


class PingRequest(BaseModel):
    ip: str
    count: int = 3


class ScanMacRequest(BaseModel):
    mac: str
    timeout: int = 2000


@router.get("/health", response_model=SystemHealth)
async def health():
    from app.core.database import get_db
    from app.models.models import Camera
    from sqlalchemy import select, func
    
    cameras_online = 0
    cameras_total = 0
    
    async for db in get_db():
        total_result = await db.execute(select(func.count(Camera.id)).where(Camera.is_enabled == True))
        cameras_total = total_result.scalar() or 0
        
        online_result = await db.execute(select(func.count(Camera.id)).where(Camera.is_enabled == True, Camera.is_online == True))
        cameras_online = online_result.scalar() or 0
        
        break
    
    return SystemHealth(
        status="healthy",
        version=settings.app_version,
        uptime_seconds=time.time() - getattr(router, "_start_time", time.time()),
        cameras_online=cameras_online,
        cameras_total=cameras_total,
    )


@router.get("/version")
async def version():
    return {
        "version": settings.app_version,
        "name": settings.app_name,
        "python": "3.11+",
        "api": "v1",
    }


@router.post("/backup")
async def backup(user=Depends(get_current_user)):
    return {"status": "ok", "message": "Backup started (placeholder)"}


@router.post("/restore")
async def restore(user=Depends(get_current_user)):
    return {"status": "ok", "message": "Restore endpoint (placeholder)"}


@router.get("/logs")
async def logs(
    level: str = "INFO",
    limit: int = 100,
    user=Depends(get_current_user),
):
    return {"level": level, "limit": limit, "logs": []}


@router.post("/ping")
async def ping(
    request: PingRequest = Body(...),
    user=Depends(get_current_user),
):
    """Ping an IP address"""
    ip = request.ip
    count = request.count
    
    import subprocess
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", ip],
            capture_output=True,
            text=True,
            timeout=10
        )
        success = result.returncode == 0
        return {
            "success": success,
            "output": result.stdout,
            "error": result.stderr if not success else None
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Ping timeout"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/scan-mac")
async def scan_mac(
    request: ScanMacRequest = Body(...),
    user=Depends(get_current_user),
):
    """Scan for device by MAC address using arp-scan or nmap"""
    mac = request.mac.lower().replace(':', '-').replace('-', ':')
    timeout = request.timeout
    
    import subprocess
    # Try arp-scan first
    try:
        result = subprocess.run(
            ["arp-scan", "--localnet", "--quiet"],
            capture_output=True,
            text=True,
            timeout=timeout / 1000 + 5
        )
        for line in result.stdout.split('\n'):
            if mac in line.lower():
                parts = line.split()
                if len(parts) >= 2:
                    return {"ip": parts[0], "mac": parts[1]}
    except FileNotFoundError:
        pass
    except Exception as e:
        pass
    
    # Try nmap as fallback
    try:
        result = subprocess.run(
            ["nmap", "-sn", "-n", "192.168.1.0/24"],
            capture_output=True,
            text=True,
            timeout=timeout / 1000 + 10
        )
        current_ip = None
        for line in result.stdout.split('\n'):
            if "Nmap scan report for" in line:
                current_ip = line.split()[-1]
            elif "MAC Address:" in line and mac.lower() in line.lower():
                return {"ip": current_ip, "mac": mac}
    except FileNotFoundError:
        pass
    except Exception as e:
        pass
    
    # Try reading from /proc/net/arp
    try:
        with open("/proc/net/arp", "r") as f:
            for line in f:
                if mac.lower() in line.lower():
                    parts = line.split()
                    if len(parts) >= 4:
                        return {"ip": parts[0], "mac": parts[3]}
    except:
        pass
    
    return {"error": "Device not found"}