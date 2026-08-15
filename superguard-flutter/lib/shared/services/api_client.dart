import 'package:dio/dio.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';

part 'api_client.g.dart';

class ApiClient {
  final Dio _dio;
  
  ApiClient(this._dio);
  
  // Auth
  Future<Response> login(String email, String password) => 
    _dio.post('/auth/login', data: {'username': email, 'password': password});
  
  Future<Response> refreshToken(String refreshToken) => 
    _dio.post('/auth/refresh', data: {'refresh_token': refreshToken});
  
  Future<Response> getMe() => _dio.get('/auth/me');
  
  // Sites
  Future<Response> getSites() => _dio.get('/sites');
  Future<Response> getSite(int id) => _dio.get('/sites/$id');
  Future<Response> createSite(Map<String, dynamic> data) => _dio.post('/sites', data: data);
  Future<Response> updateSite(int id, Map<String, dynamic> data) => _dio.put('/sites/$id', data: data);
  Future<Response> deleteSite(int id) => _dio.delete('/sites/$id');
  
  // Cameras
  Future<Response> getCameras(int siteId) => _dio.get('/sites/$siteId/cameras');
  Future<Response> getCamera(int id) => _dio.get('/cameras/$id');
  Future<Response> createCamera(int siteId, Map<String, dynamic> data) => 
    _dio.post('/sites/$siteId/cameras', data: data);
  Future<Response> updateCamera(int id, Map<String, dynamic> data) => 
    _dio.put('/cameras/$id', data: data);
  Future<Response> deleteCamera(int id) => _dio.delete('/cameras/$id');
  Future<Response> testCamera(int id) => _dio.post('/cameras/$id/test');
  Future<Response> getSnapshot(int id) => _dio.get('/cameras/$id/snapshot');
  
  // Detectors
  Future<Response> getDetectors(int siteId) => _dio.get('/sites/$siteId/detectors');
  Future<Response> getDetector(int id) => _dio.get('/detectors/$id');
  Future<Response> createDetector(int siteId, Map<String, dynamic> data) => 
    _dio.post('/sites/$siteId/detectors', data: data);
  Future<Response> updateDetector(int id, Map<String, dynamic> data) => 
    _dio.put('/detectors/$id', data: data);
  Future<Response> deleteDetector(int id) => _dio.delete('/detectors/$id');
  Future<Response> testDetector(int id) => _dio.post('/detectors/$id/test');
  
  // Actuators
  Future<Response> getActuators(int siteId) => _dio.get('/sites/$siteId/actuators');
  Future<Response> getActuator(int id) => _dio.get('/actuators/$id');
  Future<Response> createActuator(int siteId, Map<String, dynamic> data) => 
    _dio.post('/sites/$siteId/actuators', data: data);
  Future<Response> updateActuator(int id, Map<String, dynamic> data) => 
    _dio.put('/actuators/$id', data: data);
  Future<Response> deleteActuator(int id) => _dio.delete('/actuators/$id');
  Future<Response> actuatorOn(int id) => _dio.post('/actuators/$id/on');
  Future<Response> actuatorOff(int id) => _dio.post('/actuators/$id/off');
  Future<Response> actuatorToggle(int id) => _dio.post('/actuators/$id/toggle');
  Future<Response> actuatorState(int id) => _dio.get('/actuators/$id/state');
  
  // Alarms
  Future<Response> getAlarms(int siteId, {Map<String, dynamic>? query}) => 
    _dio.get('/sites/$siteId/alarms', queryParameters: query);
  Future<Response> getAlarm(int id) => _dio.get('/alarms/$id');
  Future<Response> acknowledgeAlarm(int id, int userId) => 
    _dio.post('/alarms/$id/acknowledge', data: {'user_id': userId});
  Future<Response> resolveAlarm(int id, int userId, String reason) => 
    _dio.post('/alarms/$id/resolve', data: {'user_id': userId, 'reason': reason});
  
  // Media
  Future<Response> getAlarmMedia(int alarmId) => _dio.get('/media/alarm/$alarmId');
  Future<Response> getCameraMedia(int cameraId, {Map<String, dynamic>? query}) => 
    _dio.get('/media/camera/$cameraId', queryParameters: query);
  Future<Response> downloadMedia(int mediaId) => _dio.get('/media/$mediaId/download');
  Future<Response> getThumbnail(int mediaId) => _dio.get('/media/$mediaId/thumbnail');
  
  // System
  Future<Response> getHealth() => _dio.get('/system/health');
  Future<Response> getMetrics() => _dio.get('/system/metrics');
  Future<Response> getStatus() => _dio.get('/system/status');
}

@riverpod
ApiClient apiClient(ApiClientRef ref) {
  throw UnimplementedError('Инициализируйте в main.dart');
}