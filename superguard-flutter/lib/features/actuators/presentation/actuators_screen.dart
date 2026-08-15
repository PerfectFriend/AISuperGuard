import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:superguard_client/shared/widgets/main_scaffold.dart';

class ActuatorsScreen extends ConsumerWidget {
  final int siteId;
  
  const ActuatorsScreen({super.key, required this.siteId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MainScaffold(
      title: 'Розетки объекта #$siteId',
      body: Center(child: Text('Розетки объекта #$siteId')),
      floatingActionButton: FloatingActionButton(
        onPressed: () {},
        child: const Icon(Icons.add),
      ),
    );
  }
}