import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visual_search_app/main.dart';
import 'package:visual_search_app/style_advisor.dart';

Future<void> reveal(WidgetTester tester, Finder target, double delta) async {
  final list = find.byKey(const ValueKey('advisorList'));
  await tester.scrollUntilVisible(
    target,
    delta,
    scrollable: find
        .descendant(of: list, matching: find.byType(Scrollable))
        .first,
  );
}

void main() {
  testWidgets(
    'Adviser is discoverable and keeps profile while switching tabs',
    (tester) async {
      SharedPreferences.setMockInitialValues({});
      await tester.pumpWidget(const MyApp());
      await tester.pumpAndSettle();
      await tester.tap(find.text('Tư vấn'));
      await tester.pumpAndSettle();
      expect(find.text('Tư vấn phong cách & phong thủy'), findsOneWidget);
      await tester.enterText(
        find.widgetWithText(TextField, 'Chiều cao (cm)'),
        '170',
      );
      await tester.tap(find.text('Tìm sản phẩm'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Tư vấn'));
      await tester.pumpAndSettle();
      expect(find.text('170'), findsOneWidget);
      await reveal(tester, find.text('Nhận tư vấn AI'), 180);
      await tester.tap(find.text('Nhận tư vấn AI'));
      await tester.pumpAndSettle();
      expect(
        find.text('Hãy chọn ảnh toàn thân để AI xem trang phục của bạn.'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'Birth palette needs no photo, measurements or external AI consent',
    (tester) async {
      var calls = 0;
      final client = MockClient((request) async {
        calls++;
        expect(request.url.path, '/feng-shui');
        expect(request.body, contains('2000-01-01'));
        expect(request.body, isNot(contains('height_cm')));
        expect(request.body, isNot(contains('name="person"')));
        return http.Response(
          jsonEncode({
            'feng_shui': {
              'element': 'Thổ',
              'nap_am': 'Thành Đầu Thổ',
              'can_chi': 'Kỷ Mão',
              'lunar_year': 1999,
              'colors': [
                {
                  'label': 'Vàng đất',
                  'hex': '#CA8A04',
                  'relation': 'Cùng hành',
                },
              ],
              'note': 'Tham khảo theo quan niệm truyền thống.',
              'method': 'Năm âm lịch Việt Nam',
            },
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      addTearDown(client.close);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: StyleAdvisorPage(
              serverUrl: 'https://example.test',
              client: client,
            ),
          ),
        ),
      );
      await reveal(tester, find.text('Thêm gợi ý phong thủy (tùy chọn)'), 180);
      await tester.tap(find.byType(SwitchListTile));
      await tester.pumpAndSettle();
      await reveal(tester, find.text('Chọn ngày sinh dương lịch'), 100);
      await tester.tap(find.text('Chọn ngày sinh dương lịch'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('OK'));
      await tester.pumpAndSettle();
      await reveal(tester, find.text('Xem màu phong thủy, không gọi AI'), 120);
      await tester.tap(find.text('Xem màu phong thủy, không gọi AI'));
      await tester.pumpAndSettle();
      expect(calls, 1);
      await reveal(tester, find.text('Ngũ hành Thổ · Thành Đầu Thổ'), 160);
      expect(find.text('Ngũ hành Thổ · Thành Đầu Thổ'), findsOneWidget);
    },
  );
}
