import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:superguard_client/shared/widgets/main_scaffold.dart';

class SitesScreen extends ConsumerWidget {
  const SitesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return const MainScaffold(
      title: 'Объекты',
      body: Center(child: Text('Список объектов')),
    );
  }
}

class SiteDetailScreen extends ConsumerWidget {
  final int siteId;
  
  const SiteDetailScreen({super.key, required this.siteId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MainScaffold(
      title: 'Объект #$siteId',
      body: Center(child: Text('Детали объекта #$siteId')),
    );
  }
}