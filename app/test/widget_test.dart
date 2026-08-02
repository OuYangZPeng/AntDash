import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:antdash/main.dart';

void main() {
  testWidgets('App launches to the login screen', (WidgetTester tester) async {
    await tester.pumpWidget(const AntDashApp());
    await tester.pump();

    // Brand title and login entry point are visible.
    expect(find.text('蚂蚁闪达'), findsOneWidget);
    expect(find.text('手机号登录'), findsOneWidget);
    expect(find.byType(TextField), findsWidgets);
  });
}
