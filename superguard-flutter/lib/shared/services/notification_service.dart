import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:timezone/data/latest.dart' as tz;
import 'package:timezone/timezone.dart' as tz;

part 'notification_service.g.dart';

class NotificationService {
  static final NotificationService _instance = NotificationService._internal();
  factory NotificationService() => _instance;
  static NotificationService get instance => _instance;
  
  final FlutterLocalNotificationsPlugin _notifications = FlutterLocalNotificationsPlugin();
  bool _initialized = false;
  
  NotificationService._internal();
  
  Future<void> initialize() async {
    if (_initialized) return;
    
    // Initialize timezone
    tz.initializeTimeZones();
    
    // Android settings
    const androidSettings = AndroidInitializationSettings('@mipmap/ic_launcher');
    
    // iOS settings
    const iosSettings = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );
    
    const initSettings = InitializationSettings(
      android: androidSettings,
      iOS: iosSettings,
    );
    
    await _notifications.initialize(
      initSettings,
      onDidReceiveNotificationResponse: _onNotificationTap,
    );
    
    // Create notification channels for Android
    await _createChannels();
    
    _initialized = true;
  }
  
  Future<void> _createChannels() async {
    const alarmChannel = AndroidNotificationChannel(
      'alarms',
      'Тревоги',
      description: 'Уведомления о тревогах',
      importance: Importance.max,
      playSound: true,
      enableVibration: true,
    );
    
    const systemChannel = AndroidNotificationChannel(
      'system',
      'Система',
      description: 'Системные уведомления',
      importance: Importance.high,
      playSound: true,
      enableVibration: false,
    );
    
    await _notifications
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(alarmChannel);
    
    await _notifications
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(systemChannel);
  }
  
  void _onNotificationTap(NotificationResponse response) {
    // Handle notification tap - navigate to relevant screen
    print('Notification tapped: ${response.payload}');
  }
  
  Future<void> showAlarmNotification({
    required int alarmId,
    required String cameraName,
    required String className,
    required double confidence,
    String? imagePath,
  }) async {
    const androidDetails = AndroidNotificationDetails(
      'alarms',
      'Тревоги',
      channelDescription: 'Уведомления о тревогах',
      importance: Importance.max,
      priority: Priority.high,
      playSound: true,
      enableVibration: true,
      icon: '@mipmap/ic_launcher',
      largeIcon: DrawableResourceAndroidBitmap('@mipmap/ic_launcher'),
      styleInformation: BigPictureStyleInformation(
        FilePathAndroidBitmap(''), // Будет заменено при наличии изображения
        contentTitle: 'Тревога',
        summaryText: '$cameraName: $className (${(confidence * 100).toInt()}%)',
      ),
    );
    
    const iosDetails = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
      sound: 'default',
    );
    
    const details = NotificationDetails(
      android: androidDetails,
      iOS: iosDetails,
    );
    
    await _notifications.show(
      alarmId,
      'ТРЕВОГА: $cameraName',
      '$className обнаружена с уверенностью ${(confidence * 100).toInt()}%',
      details,
      payload: 'alarm:$alarmId',
    );
  }
  
  Future<void> showSystemNotification({
    required String title,
    required String body,
    int id = 0,
  }) async {
    const androidDetails = AndroidNotificationDetails(
      'system',
      'Система',
      channelDescription: 'Системные уведомления',
      importance: Importance.high,
      priority: Priority.high,
      playSound: true,
      enableVibration: false,
    );
    
    const iosDetails = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
    );
    
    const details = NotificationDetails(
      android: androidDetails,
      iOS: iosDetails,
    );
    
    await _notifications.show(
      id,
      title,
      body,
      details,
    );
  }
  
  Future<void> cancelNotification(int id) async {
    await _notifications.cancel(id);
  }
  
  Future<void> cancelAll() async {
    await _notifications.cancelAll();
  }
}

@riverpod
NotificationService notificationService(NotificationServiceRef ref) {
  return NotificationService.instance;
}