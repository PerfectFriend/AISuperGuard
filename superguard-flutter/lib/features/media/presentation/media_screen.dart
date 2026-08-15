import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:superguard_client/shared/widgets/main_scaffold.dart';

class MediaScreen extends ConsumerWidget {
  final int siteId;
  
  const MediaScreen({super.key, required this.siteId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MainScaffold(
      title: 'Медиа объект #$siteId',
      body: Center(child: Text('Медиафайлы объекта #$siteId')),
    );
  }
}