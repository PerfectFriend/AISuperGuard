import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:superguard_client/shared/widgets/main_scaffold.dart';

class AlarmsScreen extends ConsumerWidget {
  final int siteId;
  
  const AlarmsScreen({super.key, required this.siteId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MainScaffold(
      title: 'Тревоги объекта #$siteId',
      body: Center(child: Text('Тревоги объекта #$siteId')),
    );
  }
}