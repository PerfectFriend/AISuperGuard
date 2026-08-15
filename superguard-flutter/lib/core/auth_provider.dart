import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:dio/dio.dart';
import 'package:superguard_client/shared/models/user.dart';

part 'auth_provider.g.dart';

class AuthState {
  final bool isAuthenticated;
  final User? user;
  final String? accessToken;
  final String? refreshToken;
  
  const AuthState({
    this.isAuthenticated = false,
    this.user,
    this.accessToken,
    this.refreshToken,
  });
  
  AuthState copyWith({
    bool? isAuthenticated,
    User? user,
    String? accessToken,
    String? refreshToken,
  }) {
    return AuthState(
      isAuthenticated: isAuthenticated ?? this.isAuthenticated,
      user: user ?? this.user,
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
    );
  }
}

@riverpod
class AuthStateNotifier extends _$AuthStateNotifier {
  @override
  AuthState build() {
    return const AuthState();
  }
  
  void setAuthenticated({
    required User user,
    required String accessToken,
    required String refreshToken,
  }) {
    state = AuthState(
      isAuthenticated: true,
      user: user,
      accessToken: accessToken,
      refreshToken: refreshToken,
    );
  }
  
  void updateToken(String accessToken) {
    state = state.copyWith(accessToken: accessToken);
  }
  
  void logout() {
    state = const AuthState();
  }
  
  void updateUser(User user) {
    state = state.copyWith(user: user);
  }
}

final authStateProvider = authStateNotifierProvider;