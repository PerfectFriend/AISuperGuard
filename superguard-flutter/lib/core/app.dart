import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:superguard_client/features/auth/presentation/login_screen.dart';
import 'package:superguard_client/features/sites/presentation/sites_screen.dart';
import 'package:superguard_client/features/cameras/presentation/cameras_screen.dart';
import 'package:superguard_client/features/detectors/presentation/detectors_screen.dart';
import 'package:superguard_client/features/actuators/presentation/actuators_screen.dart';
import 'package:superguard_client/features/alarms/presentation/alarms_screen.dart';
import 'package:superguard_client/features/media/presentation/media_screen.dart';
import 'package:superguard_client/features/settings/presentation/settings_screen.dart';
import 'package:superguard_client/shared/widgets/main_scaffold.dart';
import 'package:superguard_client/core/auth_provider.dart';
import 'package:superguard_client/core/theme_provider.dart';

class SuperGuardApp extends ConsumerWidget {
  const SuperGuardApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(routerProvider);
    final theme = ref.watch(themeProvider);
    
    return MaterialApp.router(
      title: 'SuperGuard Alarm',
      debugShowCheckedModeBanner: false,
      theme: theme.lightTheme,
      darkTheme: theme.darkTheme,
      themeMode: theme.themeMode,
      routerConfig: router,
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [
        Locale('ru', 'RU'),
        Locale('en', 'US'),
      ],
      locale: const Locale('ru', 'RU'),
    );
  }
}

// Router provider
final routerProvider = Provider<GoRouter>((ref) {
  final authState = ref.watch(authStateProvider);
  
  return GoRouter(
    initialLocation: '/login',
    redirect: (context, state) {
      final isLoggedIn = authState.isAuthenticated;
      final isLoginRoute = state.matchedLocation == '/login';
      
      if (!isLoggedIn && !isLoginRoute) {
        return '/login';
      }
      if (isLoggedIn && isLoginRoute) {
        return '/sites';
      }
      return null;
    },
    routes: [
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      ShellRoute(
        builder: (context, state, child) => MainScaffold(child: child),
        routes: [
          GoRoute(
            path: '/sites',
            builder: (context, state) => const SitesScreen(),
            routes: [
              GoRoute(
                path: ':siteId',
                builder: (context, state) => SiteDetailScreen(siteId: int.parse(state.pathParameters['siteId']!)),
                routes: [
                  GoRoute(
                    path: 'cameras',
                    builder: (context, state) => CamerasScreen(siteId: int.parse(state.pathParameters['siteId']!)),
                  ),
                  GoRoute(
                    path: 'detectors',
                    builder: (context, state) => DetectorsScreen(siteId: int.parse(state.pathParameters['siteId']!)),
                  ),
                  GoRoute(
                    path: 'actuators',
                    builder: (context, state) => ActuatorsScreen(siteId: int.parse(state.pathParameters['siteId']!)),
                  ),
                  GoRoute(
                    path: 'alarms',
                    builder: (context, state) => AlarmsScreen(siteId: int.parse(state.pathParameters['siteId']!)),
                  ),
                  GoRoute(
                    path: 'media',
                    builder: (context, state) => MediaScreen(siteId: int.parse(state.pathParameters['siteId']!)),
                  ),
                  GoRoute(
                    path: 'settings',
                    builder: (context, state) => SettingsScreen(siteId: int.parse(state.pathParameters['siteId']!)),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    ],
  );
});