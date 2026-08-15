import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'package:superguard_client/shared/services/api_client.dart';
import 'package:superguard_client/shared/services/auth_service.dart';
import 'package:superguard_client/shared/services/websocket_service.dart';
import 'package:superguard_client/shared/services/storage_service.dart';

part 'di.g.dart';

@riverpod
SharedPreferences sharedPreferences(SharedPreferencesRef ref) {
  throw UnimplementedError('Инициализируйте в main.dart');
}

@riverpod
FlutterSecureStorage secureStorage(SecureStorageRef ref) {
  return const FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
    iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
  );
}

@riverpod
Dio dio(DioRef ref) {
  final dio = Dio(BaseOptions(
    baseUrl: 'http://localhost:8000/api',
    connectTimeout: const Duration(seconds: 10),
    receiveTimeout: const Duration(seconds: 30),
    sendTimeout: const Duration(seconds: 30),
    headers: {'Content-Type': 'application/json'},
  ));
  
  dio.interceptors.add(LogInterceptor(
    requestBody: true,
    responseBody: true,
    logPrint: (obj) => print('[DIO] $obj'),
  ));
  
  return dio;
}

@riverpod
ApiClient apiClient(ApiClientRef ref) {
  return ApiClient(ref.watch(dioProvider));
}

@riverpod
AuthService authService(AuthServiceRef ref) {
  return AuthService(
    apiClient: ref.watch(apiClientProvider),
    secureStorage: ref.watch(secureStorageProvider),
    sharedPreferences: ref.watch(sharedPreferencesProvider),
  );
}

@riverpod
WebSocketService websocketService(WebSocketServiceRef ref) {
  return WebSocketService(
    authService: ref.watch(authServiceProvider),
  );
}

@riverpod
StorageService storageService(StorageServiceRef ref) {
  return StorageService(
    sharedPreferences: ref.watch(sharedPreferencesProvider),
  );
}