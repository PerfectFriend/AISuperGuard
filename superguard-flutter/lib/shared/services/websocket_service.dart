import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/status.dart' as status;
import 'package:riverpod_annotation/riverpod_annotation.dart';
import 'package:superguard_client/shared/services/auth_service.dart';
import 'dart:async';
import 'dart:convert';

part 'websocket_service.g.dart';

class WebSocketMessage {
  final String type;
  final Map<String, dynamic> data;
  final DateTime timestamp;
  
  WebSocketMessage({
    required this.type,
    required this.data,
    DateTime? timestamp,
  }) : timestamp = timestamp ?? DateTime.now();
  
  factory WebSocketMessage.fromJson(Map<String, dynamic> json) {
    return WebSocketMessage(
      type: json['type'] as String,
      data: json['data'] as Map<String, dynamic>,
      timestamp: json['timestamp'] != null 
          ? DateTime.parse(json['timestamp'] as String) 
          : DateTime.now(),
    );
  }
  
  Map<String, dynamic> toJson() {
    return {
      'type': type,
      'data': data,
      'timestamp': timestamp.toIso8601String(),
    };
  }
}

class WebSocketService {
  final AuthService _authService;
  WebSocketChannel? _channel;
  StreamController<WebSocketMessage>? _messageController;
  Timer? _reconnectTimer;
  Timer? _pingTimer;
  int _siteId = 0;
  bool _isConnecting = false;
  
  WebSocketService({required AuthService authService}) : _authService = authService;
  
  Stream<WebSocketMessage> get messages => _messageController?.stream ?? const Stream.empty();
  bool get isConnected => _channel != null;
  
  Future<void> connect(int siteId) async {
    if (_isConnecting || _channel != null) return;
    
    _siteId = siteId;
    _isConnecting = true;
    
    try {
      final token = await _authService.getAccessToken();
      if (token == null) throw Exception('No access token');
      
      final uri = Uri.parse('ws://localhost:8000/ws/$siteId?token=$token');
      _channel = WebSocketChannel.connect(uri);
      _messageController = StreamController<WebSocketMessage>.broadcast();
      
      _channel!.stream.listen(
        _onMessage,
        onError: _onError,
        onDone: _onDone,
        cancelOnError: true,
      );
      
      // Start ping timer
      _pingTimer = Timer.periodic(const Duration(seconds: 30), (_) {
        _sendPing();
      });
      
      _isConnecting = false;
    } catch (e) {
      _isConnecting = false;
      _scheduleReconnect();
    }
  }
  
  void _onMessage(dynamic message) {
    try {
      final json = jsonDecode(message as String);
      final wsMessage = WebSocketMessage.fromJson(json);
      _messageController?.add(wsMessage);
    } catch (e) {
      print('WebSocket message parse error: $e');
    }
  }
  
  void _onError(dynamic error) {
    print('WebSocket error: $error');
    _scheduleReconnect();
  }
  
  void _onDone() {
    print('WebSocket disconnected');
    _cleanup();
    _scheduleReconnect();
  }
  
  void _sendPing() {
    if (_channel != null) {
      _channel!.sink.add(jsonEncode({'type': 'ping'}));
    }
  }
  
  void _scheduleReconnect() {
    if (_reconnectTimer?.isActive ?? false) return;
    
    _reconnectTimer = Timer(const Duration(seconds: 5), () {
      if (_siteId > 0) {
        connect(_siteId);
      }
    });
  }
  
  void _cleanup() {
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    _channel?.sink.close(status.normalClosure);
    _channel = null;
    _messageController?.close();
    _messageController = null;
  }
  
  void send(String type, Map<String, dynamic> data) {
    if (_channel != null) {
      _channel!.sink.add(jsonEncode({'type': type, 'data': data}));
    }
  }
  
  void disconnect() {
    _cleanup();
  }
  
  void dispose() {
    disconnect();
  }
}

@riverpod
WebSocketService websocketService(WebSocketServiceRef ref) {
  throw UnimplementedError('Инициализируйте в main.dart');
}