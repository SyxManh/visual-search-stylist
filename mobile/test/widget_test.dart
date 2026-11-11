import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:visual_search_app/main.dart';

void main() {
  testWidgets('Try-on can be opened before detecting any clothing', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Thử đồ AI'));
    await tester.pumpAndSettle();
    expect(find.text('Tạo ảnh AI mặc trang phục'), findsOneWidget);
    expect(find.textContaining('Cloudflare Workers AI'), findsOneWidget);
    expect(find.text('Chọn ảnh toàn thân'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Chọn ảnh trang phục muốn mặc'),
      150,
    );
    expect(find.text('Chọn ảnh trang phục muốn mặc'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Tạo ảnh thử đồ'), 150);
    final createButton = tester.widget<FilledButton>(
      find.ancestor(
        of: find.text('Tạo ảnh thử đồ'),
        matching: find.byType(FilledButton),
      ),
    );
    expect(createButton.onPressed, isNull);
  });

  testWidgets('Search screen exposes server connection settings', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const MyApp());
    await tester.pumpAndSettle();
    expect(find.text('Tìm sản phẩm'), findsOneWidget);
    await tester.tap(find.byIcon(Icons.settings_ethernet));
    await tester.pumpAndSettle();
    expect(find.text('Kết nối máy chủ'), findsOneWidget);
    expect(find.text('Kiểm tra và lưu'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'javascript:alert(1)');
    await tester.tap(find.text('Kiểm tra và lưu'));
    await tester.pumpAndSettle();
    expect(find.text('Nhập URL HTTP/HTTPS gốc hợp lệ.'), findsOneWidget);
  });
}
