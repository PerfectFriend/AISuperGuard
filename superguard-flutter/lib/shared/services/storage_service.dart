import 'package:shared_preferences/shared_preferences.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'storage_service.g.dart';

class StorageService {
  final SharedPreferences _prefs;
  
  StorageService({required SharedPreferences prefs}) : _prefs = prefs;
  
  // Theme
  Future<void> setThemeMode(String mode) async {
    await _prefs.setString('theme_mode', mode);
  }
  
  String getThemeMode() {
    return _prefs.getString('theme_mode') ?? 'system';
  }
  
  // Language
  Future<void> setLanguage(String locale) async {
    await _prefs.setString('language', locale);
  }
  
  String getLanguage() {
    return _prefs.getString('language') ?? 'ru';
  }
  
  // Last selected site
  Future<void> setLastSiteId(int siteId) async {
    await _prefs.setInt('last_site_id', siteId);
  }
  
  int? getLastSiteId() {
    return _prefs.getInt('last_site_id');
  }
  
  // Camera settings
  Future<void> setCameraQuality(int cameraId, String quality) async {
    await _prefs.setString('camera_quality_$cameraId', quality);
  }
  
  String getCameraQuality(int cameraId) {
    return _prefs.getString('camera_quality_$cameraId') ?? 'high';
  }
  
  // Notification settings
  Future<void> setNotificationsEnabled(bool enabled) async {
    await _prefs.setBool('notifications_enabled', enabled);
  }
  
  bool getNotificationsEnabled() {
    return _prefs.getBool('notifications_enabled') ?? true;
  }
  
  // Clear all
  Future<void> clearAll() async {
    await _prefs.clear();
  }
}

@riverpod
StorageService storageService(StorageServiceRef ref) {
  throw UnimplementedError('Инициализируйте в main.dart');
}