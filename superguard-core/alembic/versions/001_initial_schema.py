"""Initial migration - SuperGuard Core schema

Revision ID: 001
Revises: 
Create Date: 2025-08-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('full_name', sa.String(length=120), nullable=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, default=False),
        sa.Column('role', sa.String(length=32), nullable=False, default='user'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])

    # Sites table
    op.create_table(
        'sites',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('timezone', sa.String(length=64), nullable=False, default='UTC'),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.Column('address', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sites_owner_id', 'sites', ['owner_id'])

    # Site members (many-to-many users <-> sites)
    op.create_table(
        'site_members',
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False, default='viewer'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('site_id', 'user_id'),
    )

    # Cameras table
    op.create_table(
        'cameras',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('url', sa.String(length=500), nullable=False),
        sa.Column('username', sa.String(length=120), nullable=True),
        sa.Column('password', sa.String(length=255), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('fps', sa.Float(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_recording', sa.Boolean(), nullable=False, default=False),
        sa.Column('last_frame_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cameras_site_id', 'cameras', ['site_id'])
    op.create_index('ix_cameras_type', 'cameras', ['type'])

    # Detectors table
    op.create_table(
        'detectors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('model_path', sa.String(length=500), nullable=True),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('confidence_threshold', sa.Float(), nullable=False, default=0.5),
        sa.Column('iou_threshold', sa.Float(), nullable=False, default=0.45),
        sa.Column('classes', sa.JSON(), nullable=True),
        sa.Column('input_width', sa.Integer(), nullable=True),
        sa.Column('input_height', sa.Integer(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('last_detection_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_detectors_site_id', 'detectors', ['site_id'])
    op.create_index('ix_detectors_type', 'detectors', ['type'])

    # Camera-Detector associations (many-to-many)
    op.create_table(
        'camera_detectors',
        sa.Column('camera_id', sa.Integer(), nullable=False),
        sa.Column('detector_id', sa.Integer(), nullable=False),
        sa.Column('zone_config', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['detector_id'], ['detectors.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('camera_id', 'detector_id'),
    )

    # Actuators table
    op.create_table(
        'actuators',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('camera_ids', sa.JSON(), nullable=True),
        sa.Column('trigger_on_alarm', sa.Boolean(), nullable=False, default=True),
        sa.Column('trigger_classes', sa.JSON(), nullable=True),
        sa.Column('auto_off_seconds', sa.Integer(), nullable=True),
        sa.Column('last_state', sa.JSON(), nullable=True),
        sa.Column('last_command_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_actuators_site_id', 'actuators', ['site_id'])
    op.create_index('ix_actuators_type', 'actuators', ['type'])

    # Zones table
    op.create_table(
        'zones',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', sa.String(length=32), nullable=False, default='polygon'),
        sa.Column('coordinates', sa.JSON(), nullable=False),
        sa.Column('color', sa.String(length=7), nullable=False, default='#FF0000'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_exclusion', sa.Boolean(), nullable=False, default=False),
        sa.Column('classes', sa.JSON(), nullable=True),
        sa.Column('min_confidence', sa.Float(), nullable=False, default=0.5),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_zones_site_id', 'zones', ['site_id'])
    op.create_index('ix_zones_camera_id', 'zones', ['camera_id'])

    # Alarms table
    op.create_table(
        'alarms',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=False),
        sa.Column('detector_id', sa.Integer(), nullable=True),
        sa.Column('zone_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, default='active'),
        sa.Column('trigger_data', sa.JSON(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('resolution_reason', sa.String(length=32), nullable=True),
        sa.Column('escalation_level', sa.Integer(), nullable=False, default=0),
        sa.Column('escalated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['acknowledged_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['detector_id'], ['detectors.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['zone_id'], ['zones.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alarms_site_id', 'alarms', ['site_id'])
    op.create_index('ix_alarms_camera_id', 'alarms', ['camera_id'])
    op.create_index('ix_alarms_status', 'alarms', ['status'])
    op.create_index('ix_alarms_started_at', 'alarms', ['started_at'])

    # Alarm Media table
    op.create_table(
        'alarm_media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('alarm_id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('thumbnail_path', sa.String(length=500), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('is_alarm_frame', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['alarm_id'], ['alarms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_alarm_media_alarm_id', 'alarm_media', ['alarm_id'])
    op.create_index('ix_alarm_media_camera_id', 'alarm_media', ['camera_id'])
    op.create_index('ix_alarm_media_type', 'alarm_media', ['type'])

    # Recordings table
    op.create_table(
        'recordings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=False),
        sa.Column('camera_id', sa.Integer(), nullable=False),
        sa.Column('alarm_id', sa.Integer(), nullable=True),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('thumbnail_path', sa.String(length=500), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration', sa.Float(), nullable=False),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('fps', sa.Float(), nullable=True),
        sa.Column('codec', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['alarm_id'], ['alarms.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_recordings_site_id', 'recordings', ['site_id'])
    op.create_index('ix_recordings_camera_id', 'recordings', ['camera_id'])
    op.create_index('ix_recordings_alarm_id', 'recordings', ['alarm_id'])
    op.create_index('ix_recordings_started_at', 'recordings', ['started_at'])

    # Events table (audit log)
    op.create_table(
        'events',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('camera_id', sa.Integer(), nullable=True),
        sa.Column('actuator_id', sa.Integer(), nullable=True),
        sa.Column('alarm_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('event_stream', sa.String(length=64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['alarm_id'], ['alarms.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['actuator_id'], ['actuators.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_events_site_id', 'events', ['site_id'])
    op.create_index('ix_events_camera_id', 'events', ['camera_id'])
    op.create_index('ix_events_actuator_id', 'events', ['actuator_id'])
    op.create_index('ix_events_alarm_id', 'events', ['alarm_id'])
    op.create_index('ix_events_type', 'events', ['event_type'])
    op.create_index('ix_events_created_at', 'events', ['created_at'])

    # Settings table (key-value per site)
    op.create_table(
        'settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('site_id', sa.Integer(), nullable=True),
        sa.Column('key', sa.String(length=120), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_encrypted', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('site_id', 'key', name='uq_site_key'),
    )
    op.create_index('ix_settings_site_id', 'settings', ['site_id'])


def downgrade() -> None:
    op.drop_table('settings')
    op.drop_table('events')
    op.drop_table('recordings')
    op.drop_table('alarm_media')
    op.drop_table('alarms')
    op.drop_table('zones')
    op.drop_table('actuators')
    op.drop_table('camera_detectors')
    op.drop_table('detectors')
    op.drop_table('cameras')
    op.drop_table('site_members')
    op.drop_table('sites')
    op.drop_table('users')