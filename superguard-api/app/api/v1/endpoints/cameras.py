"""
Cameras endpoints - CRUD, zone, stream, discover, bindings
"""
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.encryption import get_encryption
from app.models import Camera, Zone, ActuatorBinding, Actuator, User
from app.api.v1.endpoints.auth import get_current_user
from app.schemas import (
    CameraCreate, CameraUpdate, CameraResponse,
    ZoneCreate, ZoneResponse,
    CameraDiscoverRequest, DiscoveredCamera,
    ActuatorBindingCreate, ActuatorBindingResponse,
)

router = APIRouter()


@router.get("/sites/{site_id}/cameras", response_model=List[CameraResponse])
async def list_cameras(
    site_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Camera)
        .where(Camera.site_id == site_id)
        .offset(skip)
        .limit(limit)
        .options(selectinload(Camera.zone))
        .order_by(Camera.created_at)
    )
    return result.scalars().all()


@router.post("/sites/{site_id}/cameras", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    site_id: str,
    req: CameraCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Encrypt sensitive fields using Fernet encryption
    encryption = get_encryption()
    data = req.model_dump(exclude={"zone", "password"})
    
    # Encrypt password if provided
    if req.password:
        data["password_hash"] = encryption.encrypt(req.password)
    
    cam = Camera(site_id=site_id, **data)
    db.add(cam)
    await db.flush()

    if req.zone:
        zone = Zone(camera_id=cam.id, **req.zone.model_dump())
        db.add(zone)
        await db.flush()

    # Reload with zone relationship
    await db.refresh(cam, attribute_names=["zone"])

    # Build response manually to avoid lazy-load issues
    from app.schemas import CameraResponse, ZoneResponse
    zone_resp = None
    if cam.zone:
        zone_resp = ZoneResponse(rows=cam.zone.rows, cols=cam.zone.cols, cell=cam.zone.cell)
    return CameraResponse(
        id=cam.id, site_id=cam.site_id, name=cam.name, description=cam.description,
        type=cam.type.value, stream_url=cam.stream_url, width=cam.width, height=cam.height,
        fps=cam.fps, is_enabled=cam.is_enabled, is_online=cam.is_online,
        last_seen=cam.last_seen, ptz_enabled=cam.ptz_enabled, zone=zone_resp,
        created_at=cam.created_at,
    )


@router.get("/sites/{site_id}/cameras/{camera_id}", response_model=CameraResponse)
async def get_camera(
    site_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Camera)
        .where(Camera.id == camera_id, Camera.site_id == site_id)
        .options(selectinload(Camera.zone))
    )
    cam = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    return cam


@router.patch("/sites/{site_id}/cameras/{camera_id}", response_model=CameraResponse)
async def update_camera(
    site_id: str,
    camera_id: str,
    req: CameraUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id))
    cam = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")

    # Encrypt sensitive fields if provided
    encryption = get_encryption()
    update_data = req.model_dump(exclude_unset=True)
    
    # Encrypt password if provided
    if 'password' in update_data and update_data['password']:
        update_data['password_hash'] = encryption.encrypt(update_data.pop('password'))
    
    for k, v in update_data.items():
        setattr(cam, k, v)
    await db.flush()
    return cam


@router.delete("/sites/{site_id}/cameras/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    site_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id))
    cam = result.scalar_one_or_none()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    await db.delete(cam)
    await db.flush()


@router.patch("/sites/{site_id}/cameras/{camera_id}/zone", response_model=ZoneResponse)
async def update_zone(
    site_id: str,
    camera_id: str,
    req: ZoneCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Zone).where(Zone.camera_id == camera_id))
    zone = result.scalar_one_or_none()
    if zone:
        zone.rows = req.rows
        zone.cols = req.cols
        zone.cell = req.cell
    else:
        zone = Zone(camera_id=camera_id, **req.model_dump())
        db.add(zone)
    await db.flush()
    return zone


@router.post("/sites/{site_id}/cameras/{camera_id}/test")
async def test_camera(
    site_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify camera belongs to site
    result = await db.execute(
        select(Camera).where(Camera.id == camera_id, Camera.site_id == site_id)
    )
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Use the health monitor for testing with rediscovery (using same session)
    from app.services.camera_health import CameraHealthMonitor, CameraConfig, CameraDiscovery
    
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
    
    await db.commit()
    await db.refresh(camera)
    
    return {
        "status": "ok" if result.get("online") else "offline",
        "message": f"Camera {'online' if result.get('online') else 'offline'}",
        "details": result,
    }


@router.post("/sites/{site_id}/cameras/discover", response_model=List[DiscoveredCamera])
async def discover_cameras(
    site_id: str,
    req: CameraDiscoverRequest,
    user: User = Depends(get_current_user),
):
    """
    Discover cameras on the network using multiple protocols:
    - WS-Discovery (ONVIF)
    - UPnP/SSDP
    - mDNS/Bonjour
    - ARP scan for local devices
    
    Returns a list of discovered cameras with their stream URLs and capabilities.
    """
    import asyncio
    import subprocess
    import re
    import ipaddress
    from urllib.parse import urlparse
    
    discovered = []
    network_range = req.network_range or "192.168.1.0/24"
    
    # Parse network range for scanning
    network = None
    hosts = []
    try:
        network = ipaddress.ip_network(network_range, strict=False)
        hosts = list(network.hosts())[:50]  # Limit to first 50 hosts for performance
    except Exception:
        hosts = []
    
    # Method 1: WS-Discovery (ONVIF) - scan for ONVIF devices
    async def scan_ws_discovery():
        """Scan for ONVIF devices using WS-Discovery probe."""
        try:
            # Use wsdiscovery library if available, otherwise use raw UDP probe
            try:
                from wsdiscovery import WSDiscovery
                wsd = WSDiscovery()
                wsd.start()
                services = wsd.searchServices()
                wsd.stop()
                
                for service in services:
                    xaddrs = service.getXAddrs()
                    for xaddr in xaddrs:
                        if xaddr:
                            parsed = urlparse(xaddr)
                            ip = parsed.hostname
                            port = parsed.port or 80
                            # Try to get device info
                            try:
                                from onvif import ONVIFCamera
                                cam = ONVIFCamera(ip, port, '', '')
                                info = cam.devicemgmt.GetDeviceInformation()
                                manufacturer_name = info.Manufacturer if info and info.Manufacturer else "Unknown"
                                discovered.append(DiscoveredCamera(
                                    ip=ip,
                                    port=port,
                                    manufacturer=manufacturer_name,
                                    onvif=True,
                                    url=f"rtsp://{ip}:554/stream1"
                                ))
                            except Exception:
                                # ONVIF device found but auth failed or no stream
                                discovered.append(DiscoveredCamera(
                                    ip=ip,
                                    port=port,
                                    manufacturer="Unknown",
                                    onvif=True,
                                    url=f"rtsp://{ip}:554/stream1"
                                ))
            except ImportError:
                # wsdiscovery not available, fall back to manual probe
                pass
        except Exception as e:
            print(f"[CameraDiscovery] WS-Discovery error: {e}")
    
    # Method 2: UPnP/SSDP scan
    async def scan_upnp():
        """Scan for UPnP devices using SSDP M-SEARCH."""
        try:
            import socket
            import struct
            
            # SSDP M-SEARCH request
            message = (
                "M-SEARCH * HTTP/1.1\r\n"
                "HOST: 239.255.255.250:1900\r\n"
                "MAN: \"ssdp:discover\"\r\n"
                "MX: 3\r\n"
                "ST: urn:schemas-upnp-org:device:basic:1\r\n"
                "\r\n"
            )
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.settimeout(3)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            
            # Send to multicast
            sock.sendto(message.encode(), ('239.255.255.250', 1900))
            
            # Collect responses
            try:
                while True:
                    data, addr = sock.recvfrom(65507)
                    response = data.decode('utf-8', errors='ignore')
                    ip = addr[0]
                    
                    # Parse UPnP response for camera info
                    manufacturer = "Unknown"
                    if "Manufacturer" in response:
                        match = re.search(r'Manufacturer:\s*(.+)', response, re.IGNORECASE)
                        if match:
                            manufacturer = match.group(1).strip()
                    elif "Server" in response:
                        match = re.search(r'Server:\s*(.+)', response, re.IGNORECASE)
                        if match:
                            manufacturer = match.group(1).strip()
                    
                    # Check if it's a camera
                    is_camera = any(keyword in response.lower() for keyword in 
                                   ['camera', 'ipcam', 'nvr', 'dvr', 'onvif', 'surveillance'])
                    
                    if is_camera or 'camera' in manufacturer.lower():
                        discovered.append(DiscoveredCamera(
                            ip=ip,
                            port=80,
                            manufacturer=manufacturer,
                            onvif='onvif' in response.lower(),
                            url=f"rtsp://{ip}:554/stream1"
                        ))
            except socket.timeout:
                pass
            finally:
                sock.close()
        except Exception as e:
            print(f"[CameraDiscovery] UPnP scan error: {e}")
    
    # Method 3: mDNS/Bonjour scan
    async def scan_mdns():
        """Scan for cameras using mDNS/DNS-SD."""
        try:
            # Try to use zeroconf if available
            try:
                from zeroconf import Zeroconf, ServiceBrowser, ServiceStateChange
                import threading
                
                found_devices = []
                
                def on_service_state_change(zeroconf, service_type, name, state_change):
                    if state_change == ServiceStateChange.Added:
                        info = zeroconf.get_service_info(service_type, name)
                        if info:
                            ip = info.parsed_addresses()[0] if info.parsed_addresses() else None
                            if ip:
                                found_devices.append({
                                    'ip': ip,
                                    'name': name,
                                    'port': info.port,
                                    'properties': info.properties
                                })
                
                zc = Zeroconf()
                browser = ServiceBrowser(zc, "_rtsp._tcp.local.", handlers=[on_service_state_change])
                browser2 = ServiceBrowser(zc, "_onvif._tcp.local.", handlers=[on_service_state_change])
                
                await asyncio.sleep(3)
                zc.close()
                
                for device in found_devices:
                    manufacturer = device['properties'].get(b'manufacturer', b'Unknown').decode('utf-8', errors='ignore')
                    discovered.append(DiscoveredCamera(
                        ip=device['ip'],
                        port=device['port'],
                        manufacturer=manufacturer,
                        onvif=True,
                        url=f"rtsp://{device['ip']}:554/stream1"
                    ))
            except ImportError:
                pass
        except Exception as e:
            print(f"[CameraDiscovery] mDNS scan error: {e}")
    
    # Method 4: ARP/Ping scan for local network
    async def scan_arp_ping():
        """Scan local network via ARP table and ping sweep."""
        if not hosts:
            return
            
        # Get current ARP table
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
                                ip_addr = parts[0]
                                mac = parts[lladdr_idx + 1]
                                # Only add if in our scan range
                                if network is not None:
                                    try:
                                        if ipaddress.ip_address(ip_addr) in network:
                                            discovered.append(DiscoveredCamera(
                                                ip=ip_addr,
                                                port=80,
                                                manufacturer="Unknown (ARP)",
                                                onvif=False,
                                                url=f"rtsp://{ip_addr}:554/stream1"
                                            ))
                                    except Exception:
                                        pass
                        except ValueError:
                            pass
        except Exception:
            pass
    
    # Run all discovery methods concurrently
    await asyncio.gather(
        scan_ws_discovery(),
        scan_upnp(),
        scan_mdns(),
        scan_arp_ping(),
        return_exceptions=True
    )
    
    # Deduplicate by IP
    seen_ips = set()
    unique_discovered = []
    for cam in discovered:
        if cam.ip not in seen_ips:
            seen_ips.add(cam.ip)
            unique_discovered.append(cam)
    
    return unique_discovered


@router.get("/sites/{site_id}/cameras/{camera_id}/bindings", response_model=List[ActuatorBindingResponse])
async def list_bindings(
    site_id: str,
    camera_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ActuatorBinding).where(ActuatorBinding.camera_id == camera_id)
    )
    return result.scalars().all()


@router.delete("/sites/{site_id}/cameras/{camera_id}/bindings/{binding_id}", status_code=204)
async def delete_binding(
    site_id: str,
    camera_id: str,
    binding_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ActuatorBinding).where(
            ActuatorBinding.id == binding_id,
            ActuatorBinding.camera_id == camera_id
        )
    )
    binding = result.scalar_one_or_none()
    if not binding:
        raise HTTPException(status_code=404, detail="Binding not found")
    await db.delete(binding)
    await db.flush()


@router.post("/sites/{site_id}/cameras/{camera_id}/bindings", response_model=ActuatorBindingResponse, status_code=201)
async def create_binding(
    site_id: str,
    camera_id: str,
    req: ActuatorBindingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    binding = ActuatorBinding(camera_id=camera_id, **req.model_dump())
    db.add(binding)
    await db.flush()
    return binding