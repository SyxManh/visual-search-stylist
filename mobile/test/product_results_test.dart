import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:visual_search_app/product_results.dart';

void main() {
  Widget panel(
    Map<String, dynamic> result, {
    ValueChanged<String>? open,
    VoidCallback? retry,
  }) {
    return MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ProductResultsPanel(
            result: result,
            loading: false,
            onRetry: retry ?? () {},
            onOpenProduct: open ?? (_) {},
          ),
        ),
      ),
    );
  }

  testWidgets(
    'Unconfigured API shows no keyword or Lens cards and permits retry',
    (tester) async {
      var retries = 0;
      await tester.pumpWidget(
        panel({
          'status': 'not_configured',
          'message': 'Chưa cấu hình API tìm sản phẩm bằng ảnh.',
          'products': <String, dynamic>{},
        }, retry: () => retries++),
      );
      expect(
        find.text('Chưa cấu hình API tìm sản phẩm bằng ảnh.'),
        findsOneWidget,
      );
      expect(find.text('Xem sản phẩm ↗'), findsNothing);
      expect(find.textContaining('Google Lens'), findsNothing);
      await tester.tap(find.text('Kiểm tra lại sau khi thêm API'));
      expect(retries, 1);
    },
  );

  testWidgets(
    'API cards appear inside app, filter by platform and open direct product',
    (tester) async {
      String? opened;
      await tester.pumpWidget(
        panel({
          'status': 'ready',
          'message': 'Kết quả tương tự theo ảnh',
          'products': {
            'shopee': [
              {
                'title': 'Áo Shopee tương tự',
                'price': '199.000 ₫',
                'source': 'Shopee',
                'thumbnail': '',
                'link': 'https://shopee.vn/product/1/2',
                'link_type': 'product',
              },
            ],
            'lazada': [
              {
                'title': 'Áo Lazada tương tự',
                'price': 'Chưa có giá',
                'source': 'Lazada',
                'thumbnail': '',
                'link': 'https://lazada.vn/products/item.html',
                'link_type': 'product',
              },
            ],
            'amazon': [],
            'others': [],
          },
        }, open: (link) => opened = link),
      );
      expect(find.text('2 sản phẩm tương tự'), findsOneWidget);
      expect(find.text('Áo Shopee tương tự'), findsOneWidget);
      expect(find.text('Áo Lazada tương tự'), findsOneWidget);
      await tester.tap(find.text('Shopee (1)'));
      await tester.pumpAndSettle();
      expect(find.text('Áo Lazada tương tự'), findsNothing);
      await tester.tap(find.text('Xem sản phẩm ↗'));
      expect(opened, 'https://shopee.vn/product/1/2');
      await tester.tap(find.text('Amazon (0)'));
      await tester.pumpAndSettle();
      expect(find.textContaining('API chưa trả sản phẩm'), findsOneWidget);
    },
  );

  testWidgets('Legacy keyword cards cannot appear as visual products', (
    tester,
  ) async {
    await tester.pumpWidget(
      panel({
        'status': 'ready',
        'products': {
          'shopee': [
            {
              'title': 'Tìm shirt trên Shopee',
              'link': 'https://shopee.vn/search?keyword=shirt',
              'link_type': 'search',
            },
          ],
        },
      }),
    );
    expect(find.text('Tìm shirt trên Shopee'), findsNothing);
    expect(find.text('Xem sản phẩm ↗'), findsNothing);
  });
}
