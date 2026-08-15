import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:superguard_client/core/di.dart';
import 'package:superguard_client/shared/services/notification_service.dart';
import 'package:superguard_client/core/app.dart';

Future<void> configureDependencies() async {
  // Инициализация SharedPreferences
  final prefs = await SharedPreferences.getInstance();
  
  // Переопределяем провайдеры в runtime
  // Это будет сделано через ProviderScope overrides в main
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Инициализация SharedPreferences
  final prefs = await SharedPreferences.getInstance();
  
  // Инициализация уведомлений
  await NotificationService.instance.initialize();
  
  runApp(
    ProviderScope(
      overrides: [
        sharedPreferencesProvider.overrideWithValue(prefs),
        secureStorageProvider.overrideWithValue(
          const FlutterSecureStorage(
            aOptions: AndroidOptions(encryptedSharedPreferences: true),
            iOptions: IOSOptions(accessibility: KeychainAccessibility.first_unlock_this_device),
          ),
        ),
      ],
      child: const SuperGuardApp(),
    ),
  );
}