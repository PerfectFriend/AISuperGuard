import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:superguard_client/shared/models/user.dart';

part 'auth_service.g.dart';

class AuthService {
  final Dio _apiClient;
  final FlutterSecureStorage _secureStorage;
  final SharedPreferences _prefs;
  
  static const _accessTokenKey = 'access_token';
  static const _refreshTokenKey = 'refresh_token';
  static const _userKey = 'user_data';
  
  AuthService({
    required Dio apiClient,
    required FlutterSecureStorage secureStorage,
    required SharedPreferences prefs,
  }) : _apiClient = apiClient,
       _secureStorage = secureStorage,
       _prefs = prefs;
  
  Future<void> login({
    required String email,
    required String password,
  }) async {
    final response = await _apiClient.post('/auth/login', data: {
      'username': email,
      'password': password,
    });
    
    final data = response.data;
    final accessToken = data['access_token'] as String;
    final refreshToken = data['refresh_token'] as String;
    
    await _saveTokens(accessToken, refreshToken);
    await _fetchAndSaveUser();
  }
  
  Future<void> _saveTokens(String accessToken, String refreshToken) async {
    await _secureStorage.write(key: _accessTokenKey, value: accessToken);
    await _secureStorage.write(key: _refreshTokenKey, value: refreshToken);
    _apiClient.options.headers['Authorization'] = 'Bearer $accessToken';
  }
  
  Future<void> _fetchAndSaveUser() async {
    final response = await _apiClient.get('/auth/me');
    final user = User.fromJson(response.data);
    await _saveUser(user);
  }
  
  Future<void> _saveUser(User user) async {
    await _prefs.setString(_userKey, user.toJson().toString());
  }
  
  Future<User?> getSavedUser() async {
    final userJson = _prefs.getString(_userKey);
    if (userJson != null) {
      // В реальности нужно парсить JSON, здесь упрощено
      return null;
    }
    return null;
  }
  
  Future<String?> getAccessToken() async {
    return await _secureStorage.read(key: _accessTokenKey);
  }
  
  Future<String?> getRefreshToken() async {
    return await _secureStorage.read(key: _refreshTokenKey);
  }
  
  Future<void> refreshToken() async {
    final refreshToken = await getRefreshToken();
    if (refreshToken == null) throw Exception('No refresh token');
    
    final response = await _apiClient.post('/auth/refresh', data: {
      'refresh_token': refreshToken,
    });
    
    final newAccessToken = response.data['access_token'] as String;
    final newRefreshToken = response.data['refresh_token'] as String;
    
    await _saveTokens(newAccessToken, newRefreshToken);
  }
  
  Future<void> logout() async {
    await _secureStorage.delete(key: _accessTokenKey);
    await _secureStorage.delete(key: _refreshTokenKey);
    await _prefs.remove(_userKey);
    _apiClient.options.headers.remove('Authorization');
  }
  
  Future<void> initializeFromStorage() async {
    final accessToken = await getAccessToken();
    if (accessToken != null) {
      _apiClient.options.headers['Authorization'] = 'Bearer $accessToken';
    }
  }
}

@riverpod
AuthService authService(AuthServiceRef ref) {
  throw UnimplementedError('Инициализируйте в main.dart');
}