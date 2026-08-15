"""
SuperGuard Core - Alarm Engine Service

Manages alarm lifecycle: creation, acknowledgment, escalation, auto-cancel.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from superguard_core.core.config import get_settings
from superguard_core.core.database import (
    Alarm, AlarmStatus, Camera, Actuator, NotificationRule, Site
)
from superguard_core.core.events import EventBus, publish_alarm, Streams
from superguard_core.core.plugins import PluginManager
from superguard_core.services.actuator_engine import ActuatorEngine


logger = logging.getLogger(__name__)


@dataclass
class ActiveAlarm:
    """Runtime alarm state."""
    alarm: Alarm
    auto_cancel_task: Optional[asyncio.Task] = None
    cooldown_task: Optional[asyncio.Task] = None
    notified: bool = False


class AlarmEngine:
    """Manages alarm lifecycle for a site."""
    
    def __init__(
        self,
        event_bus: EventBus,
        site_id: int,
        actuator_engine: Optional[ActuatorEngine] = None,
    ):
        self.event_bus = event_bus
        self.site_id = site_id
        self.actuator_engine = actuator_engine
        self.active_alarms: Dict[int, ActiveAlarm] = {}  # alarm_id -> ActiveAlarm
        self._running = False
        self._session_factory = None
        self._plugin_manager = None
    
    def set_session_factory(self, factory):
        """Set database session factory."""
        self._session_factory = factory
    
    def set_plugin_manager(self, plugin_manager: PluginManager):
        """Set plugin manager for notifiers."""
        self._plugin_manager = plugin_manager
    
    async def start(self) -> None:
        """Start alarm engine."""
        self._running = True
        logger.info(f"AlarmEngine started for site {self.site_id}")
        
        # Load existing active alarms
        await self._load_active_alarms()
    
    async def stop(self) -> None:
        """Stop alarm engine."""
        self._running = False
        
        # Cancel all auto-cancel tasks
        for active in self.active_alarms.values():
            if active.auto_cancel_task:
                active.auto_cancel_task.cancel()
            if active.cooldown_task:
                active.cooldown_task.cancel()
        
        self.active_alarms.clear()
        logger.info(f"AlarmEngine stopped for site {self.site_id}")
    
    async def _load_active_alarms(self) -> None:
        """Load active alarms from database on startup."""
        if not self._session_factory:
            return
        
        async with self._session_factory() as session:
            result = await session.execute(
                select(Alarm)
                .where(
                    Alarm.site_id == self.site_id,
                    Alarm.status.in_([AlarmStatus.ACTIVE, AlarmStatus.ACKNOWLEDGED])
                )
            )
            alarms = result.scalars().all()
            
            for alarm in alarms:
                active = ActiveAlarm(alarm=alarm)
                self.active_alarms[alarm.id] = active
                
                # Schedule auto-cancel if needed
                if alarm.auto_cancel_at and alarm.auto_cancel_at > datetime.now():
                    delay = (alarm.auto_cancel_at - datetime.now()).total_seconds()
                    active.auto_cancel_task = asyncio.create_task(
                        self._auto_cancel_after(alarm.id, delay)
                    )
                
                logger.info(f"Loaded active alarm: {alarm.id} (status: {alarm.status.value})")
    
    async def create_alarm(
        self,
        camera_id: int,
        detector_id: int,
        trigger_data: Dict[str, Any],
        actuator_id: Optional[int] = None,
    ) -> Alarm:
        """Create new alarm from detection."""
        if not self._session_factory:
            raise RuntimeError("Session factory not set")
        
        async with self._session_factory() as session:
            # Get camera and detector for validation
            camera_result = await session.execute(
                select(Camera).where(Camera.id == camera_id, Camera.site_id == self.site_id)
            )
            camera = camera_result.scalar_one_or_none()
            
            detector_result = await session.execute(
                select(Detector).where(Detector.id == detector_id, Detector.site_id == self.site_id)
            )
            detector = detector_result.scalar_one_or_none()
            
            if not camera or not detector:
                raise ValueError("Camera or detector not found")
            
            # Check cooldown
            cooldown = detector.config.get("alarm_cooldown", 30) if isinstance(detector.config, dict) else 30
            recent_alarm = await session.execute(
                select(Alarm)
                .where(
                    Alarm.camera_id == camera_id,
                    Alarm.status.in_([AlarmStatus.ACTIVE, AlarmStatus.ACKNOWLEDGED]),
                    Alarm.started_at >= datetime.now() - timedelta(seconds=cooldown)
                )
                .order_by(Alarm.started_at.desc())
            )
            if recent_alarm.scalar_one_or_none():
                logger.info(f"Alarm suppressed by cooldown for camera {camera_id}")
                return None  # Suppressed by cooldown
            
            # Create alarm
            auto_cancel_after = detector.config.get("auto_cancel_after", 300) if isinstance(detector.config, dict) else 300
            auto_cancel_at = datetime.now() + timedelta(seconds=auto_cancel_after) if auto_cancel_after > 0 else None
            
            alarm = Alarm(
                site_id=self.site_id,
                camera_id=camera_id,
                detector_id=detector_id,
                actuator_id=actuator_id,
                status=AlarmStatus.ACTIVE,
                trigger_data=trigger_data,
                auto_cancel_at=auto_cancel_at,
            )
            session.add(alarm)
            await session.flush()
            
            # Trigger actuator if bound
            if actuator_id and self.actuator_engine:
                await self.actuator_engine.trigger_actuator(actuator_id, True, alarm.id)
            
            # Send notifications
            await self._send_notifications(alarm, "alarm_created")
            
            await session.commit()
            await session.refresh(alarm)
            
            # Track active alarm
            active = ActiveAlarm(alarm=alarm)
            self.active_alarms[alarm.id] = active
            
            # Schedule auto-cancel
            if auto_cancel_at:
                delay = (auto_cancel_at - datetime.now()).total_seconds()
                active.auto_cancel_task = asyncio.create_task(
                    self._auto_cancel_after(alarm.id, delay)
                )
            
            # Publish alarm event
            await publish_alarm(self.event_bus, {
                "alarm_id": alarm.id,
                "uuid": alarm.uuid,
                "site_id": alarm.site_id,
                "camera_id": alarm.camera_id,
                "detector_id": alarm.detector_id,
                "status": alarm.status.value,
                "trigger_data": alarm.trigger_data,
                "started_at": alarm.started_at.isoformat(),
                "auto_cancel_at": alarm.auto_cancel_at.isoformat() if alarm.auto_cancel_at else None,
            })
            
            logger.info(f"Alarm created: {alarm.id} for camera {camera_id}")
            return alarm
    
    async def acknowledge_alarm(self, alarm_id: int, user_id: int) -> Alarm:
        """Acknowledge alarm by user."""
        if not self._session_factory:
            raise RuntimeError("Session factory not set")
        
        async with self._session_factory() as session:
            result = await session.execute(
                select(Alarm).where(Alarm.id == alarm_id, Alarm.site_id == self.site_id)
            )
            alarm = result.scalar_one_or_none()
            
            if not alarm:
                raise ValueError("Alarm not found")
            
            if alarm.status not in [AlarmStatus.ACTIVE, AlarmStatus.ACKNOWLEDGED]:
                raise ValueError(f"Cannot acknowledge alarm in status: {alarm.status.value}")
            
            alarm.status = AlarmStatus.ACKNOWLEDGED
            alarm.acknowledged_at = datetime.now()
            alarm.acknowledged_by = user_id
            
            # Cancel auto-cancel if acknowledged
            if alarm_id in self.active_alarms:
                active = self.active_alarms[alarm_id]
                if active.auto_cancel_task:
                    active.auto_cancel_task.cancel()
                    active.auto_cancel_task = None
            
            # Send notifications
            await self._send_notifications(alarm, "alarm_acknowledged")
            
            await session.commit()
            await session.refresh(alarm)
            
            # Publish event
            await publish_alarm(self.event_bus, {
                "alarm_id": alarm.id,
                "status": alarm.status.value,
                "acknowledged_at": alarm.acknowledged_at.isoformat(),
                "acknowledged_by": user_id,
            })
            
            logger.info(f"Alarm {alarm_id} acknowledged by user {user_id}")
            return alarm
    
    async def resolve_alarm(self, alarm_id: int, user_id: int, reason: str = "resolved") -> Alarm:
        """Resolve alarm (mark as resolved/false positive)."""
        if not self._session_factory:
            raise RuntimeError("Session factory not set")
        
        async with self._session_factory() as session:
            result = await session.execute(
                select(Alarm).where(Alarm.id == alarm_id, Alarm.site_id == self.site_id)
            )
            alarm = result.scalar_one_or_none()
            
            if not alarm:
                raise ValueError("Alarm not found")
            
            # Turn off actuator if was triggered
            if alarm.actuator_id and self.actuator_engine:
                await self.actuator_engine.trigger_actuator(alarm.actuator_id, False, alarm.id)
            
            if reason == "false_positive":
                alarm.status = AlarmStatus.FALSE_POSITIVE
            else:
                alarm.status = AlarmStatus.RESOLVED
            
            alarm.ended_at = datetime.now()
            alarm.acknowledged_by = user_id
            alarm.acknowledged_at = datetime.now()
            
            # Cancel auto-cancel
            if alarm_id in self.active_alarms:
                active = self.active_alarms[alarm_id]
                if active.auto_cancel_task:
                    active.auto_cancel_task.cancel()
                del self.active_alarms[alarm_id]
            
            # Send notifications
            await self._send_notifications(alarm, f"alarm_{reason}")
            
            await session.commit()
            await session.refresh(alarm)
            
            # Publish event
            await publish_alarm(self.event_bus, {
                "alarm_id": alarm.id,
                "status": alarm.status.value,
                "ended_at": alarm.ended_at.isoformat(),
                "reason": reason,
            })
            
            logger.info(f"Alarm {alarm_id} {reason} by user {user_id}")
            return alarm
    
    async def _auto_cancel_after(self, alarm_id: int, delay: float) -> None:
        """Auto-cancel alarm after delay."""
        try:
            await asyncio.sleep(delay)
            
            if alarm_id in self.active_alarms:
                await self.resolve_alarm(alarm_id, 0, "auto_cancel")  # 0 = system user
                
        except asyncio.CancelledError:
            pass  # Cancelled by acknowledgment
        except Exception as e:
            logger.error(f"Auto-cancel error for alarm {alarm_id}: {e}")
    
    async def _send_notifications(self, alarm: Alarm, trigger: str) -> None:
        """Send notifications for alarm event."""
        if not self._session_factory or not self._plugin_manager:
            return
        
        async with self._session_factory() as session:
            result = await session.execute(
                select(NotificationRule)
                .where(
                    NotificationRule.site_id == self.site_id,
                    NotificationRule.trigger == trigger,
                    NotificationRule.is_enabled == True
                )
            )
            rules = result.scalars().all()
            
            for rule in rules:
                try:
                    # Load notifier plugin
                    plugin_name = rule.notifier_plugin
                    plugin_class = self._plugin_manager.get_plugin_class(
                        self._plugin_manager.metadata.get(plugin_name, None) and self._plugin_manager.metadata[plugin_name].plugin_type,
                        plugin_name
                    )
                    
                    if not plugin_class:
                        for name, meta in self._plugin_manager.metadata.items():
                            if meta.plugin_type.value == "notifier" and name == plugin_name:
                                plugin_class = meta.entry_point.load()
                                break
                    
                    if plugin_class:
                        from superguard_core.core.plugins import PluginConfig
                        plugin_config = PluginConfig(
                            enabled=True,
                            site_id=self.site_id,
                            **rule.notifier_config
                        )
                        plugin = await self._plugin_manager.load_plugin(
                            self._plugin_manager.metadata[plugin_name].plugin_type,
                            plugin_name,
                            plugin_config,
                            self.event_bus,
                        )
                        
                        # Build notification payload
                        from superguard_core.core.plugins import NotificationPayload
                        camera_result = await session.execute(
                            select(Camera).where(Camera.id == alarm.camera_id)
                        )
                        camera = camera_result.scalar_one_or_none()
                        
                        payload = NotificationPayload(
                            title=f"���� Alarm: {camera.name if camera else 'Unknown Camera'}",
                            message=f"Alarm {trigger.replace('_', ' ')} at {alarm.started_at.strftime('%H:%M:%S')}",
                            priority="high" if trigger == "alarm_created" else "normal",
                            metadata={
                                "alarm_id": alarm.id,
                                "camera_id": alarm.camera_id,
                                "trigger": trigger,
                            }
                        )
                        
                        # Get targets from config
                        targets = rule.notifier_config.get("targets", [])
                        if "chat_id" in rule.notifier_config:
                            targets.append(rule.notifier_config["chat_id"])
                        
                        await plugin.send(payload, targets)
                        
                except Exception as e:
                    logger.error(f"Notification failed for rule {rule.id}: {e}")
    
    async def get_active_alarms(self) -> List[Alarm]:
        """Get all active alarms for site."""
        if not self._session_factory:
            return []
        
        async with self._session_factory() as session:
            result = await session.execute(
                select(Alarm)
                .where(
                    Alarm.site_id == self.site_id,
                    Alarm.status.in_([AlarmStatus.ACTIVE, AlarmStatus.ACKNOWLEDGED])
                )
                .order_by(Alarm.started_at.desc())
            )
            return result.scalars().all()
    
    async def get_alarm_history(
        self,
        limit: int = 100,
        offset: int = 0,
        status_filter: Optional[AlarmStatus] = None,
        camera_id: Optional[int] = None,
        since: Optional[datetime] = None,
    ) -> List[Alarm]:
        """Get alarm history with filters."""
        if not self._session_factory:
            return []
        
        async with self._session_factory() as session:
            query = select(Alarm).where(Alarm.site_id == self.site_id)
            
            if status_filter:
                query = query.where(Alarm.status == status_filter)
            if camera_id:
                query = query.where(Alarm.camera_id == camera_id)
            if since:
                query = query.where(Alarm.started_at >= since)
            
            query = query.order_by(Alarm.started_at.desc()).limit(limit).offset(offset)
            result = await session.execute(query)
            return result.scalars().all()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get alarm engine statistics."""
        active_count = len([a for a in self.active_alarms.values() if a.alarm.status == AlarmStatus.ACTIVE])
        acknowledged_count = len([a for a in self.active_alarms.values() if a.alarm.status == AlarmStatus.ACKNOWLEDGED])
        
        return {
            "site_id": self.site_id,
            "active_alarms": active_count,
            "acknowledged_alarms": acknowledged_count,
            "total_tracked": len(self.active_alarms),
        }


# Factory
_alarm_engines: Dict[int, AlarmEngine] = {}


async def get_alarm_engine(
    site_id: int,
    event_bus: EventBus,
    actuator_engine: Optional[ActuatorEngine] = None,
) -> AlarmEngine:
    """Get or create alarm engine for site."""
    if site_id not in _alarm_engines:
        _alarm_engines[site_id] = AlarmEngine(event_bus, site_id, actuator_engine)
        await _alarm_engines[site_id].start()
    return _alarm_engines[site_id]


async def close_all_alarm_engines() -> None:
    """Close all alarm engines."""
    for engine in _alarm_engines.values():
        await engine.stop()
    _alarm_engines.clear()