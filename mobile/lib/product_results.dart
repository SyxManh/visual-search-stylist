import 'package:flutter/material.dart';

/// Renders API results inside the app. This widget never creates search links.
class ProductResultsPanel extends StatefulWidget {
  const ProductResultsPanel({
    super.key,
    required this.result,
    required this.loading,
    required this.onRetry,
    required this.onOpenProduct,
    this.hasSelection = true,
  });

  final Map<String, dynamic>? result;
  final bool loading;
  final bool hasSelection;
  final VoidCallback onRetry;
  final ValueChanged<String> onOpenProduct;

  @override
  State<ProductResultsPanel> createState() => _ProductResultsPanelState();
}

class _ProductResultsPanelState extends State<ProductResultsPanel> {
  String _platform = 'all';
  static const _platforms = {
    'all': 'Tất cả',
    'shopee': 'Shopee',
    'lazada': 'Lazada',
    'amazon': 'Amazon',
    'others': 'Khác',
  };

  bool _validProduct(dynamic item) {
    if (item is! Map || item['link_type'] != 'product') return false;
    final uri = Uri.tryParse(item['link']?.toString() ?? '');
    return uri != null &&
        ['http', 'https'].contains(uri.scheme) &&
        uri.host.isNotEmpty;
  }

  @override
  Widget build(BuildContext context) {
    if (widget.loading) {
      return const Padding(
        padding: EdgeInsets.all(32),
        child: Center(
          child: Column(
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 12),
              Text('Đang tìm sản phẩm tương tự từ ảnh...'),
            ],
          ),
        ),
      );
    }
    if (!widget.hasSelection) {
      return const Padding(
        padding: EdgeInsets.all(24),
        child: Text('Chọn một món đồ trong ảnh để tìm sản phẩm tương tự.'),
      );
    }
    final result = widget.result;
    if (result == null) return const SizedBox.shrink();
    final status = result['status'];
    final products = result['products'] is Map ? result['products'] as Map : {};
    List<dynamic> itemsFor(String key) {
      final value = products[key];
      return value is List ? value.where(_validProduct).toList() : [];
    }

    final allItems = _platforms.keys
        .where((key) => key != 'all')
        .expand(itemsFor)
        .toList();
    if (status != 'ready' || allItems.isEmpty) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                status == 'not_configured'
                    ? Icons.key_outlined
                    : Icons.search_off,
                size: 32,
              ),
              const SizedBox(height: 12),
              Text(
                result['message']?.toString() ?? 'Chưa có kết quả sản phẩm.',
              ),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                onPressed: widget.onRetry,
                icon: const Icon(Icons.refresh),
                label: Text(
                  status == 'not_configured'
                      ? 'Kiểm tra lại sau khi thêm API'
                      : 'Thử lại',
                ),
              ),
            ],
          ),
        ),
      );
    }
    final items = _platform == 'all' ? allItems : itemsFor(_platform);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                '${allItems.length} sản phẩm tương tự',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
            IconButton(
              tooltip: 'Tìm lại bằng ảnh',
              onPressed: widget.onRetry,
              icon: const Icon(Icons.refresh),
            ),
          ],
        ),
        if ((result['message']?.toString() ?? '').isNotEmpty)
          Text(
            result['message'].toString(),
            style: const TextStyle(color: Colors.blueGrey),
          ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 4,
          children: _platforms.entries.map((entry) {
            final count = entry.key == 'all'
                ? allItems.length
                : itemsFor(entry.key).length;
            return ChoiceChip(
              label: Text('${entry.value} ($count)'),
              selected: _platform == entry.key,
              onSelected: (_) => setState(() => _platform = entry.key),
            );
          }).toList(),
        ),
        const SizedBox(height: 12),
        if (items.isEmpty)
          const Padding(
            padding: EdgeInsets.all(20),
            child: Text(
              'API chưa trả sản phẩm từ sàn này. Chọn Tất cả để xem các kết quả khác.',
            ),
          )
        else
          LayoutBuilder(
            builder: (context, constraints) => GridView.builder(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: constraints.maxWidth >= 650 ? 3 : 2,
                mainAxisExtent: 296,
                crossAxisSpacing: 10,
                mainAxisSpacing: 10,
              ),
              itemCount: items.length,
              itemBuilder: (context, index) {
                final item = items[index] as Map;
                final link = item['link'].toString();
                final thumbnail = item['thumbnail']?.toString() ?? '';
                return Card(
                  margin: EdgeInsets.zero,
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () => widget.onOpenProduct(link),
                    child: Padding(
                      padding: const EdgeInsets.all(10),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SizedBox(
                            height: 118,
                            width: double.infinity,
                            child: thumbnail.isEmpty
                                ? const Icon(Icons.image_outlined, size: 40)
                                : Image.network(
                                    thumbnail,
                                    fit: BoxFit.contain,
                                    errorBuilder: (_, _, _) => const Icon(
                                      Icons.broken_image_outlined,
                                      size: 40,
                                    ),
                                  ),
                          ),
                          const SizedBox(height: 8),
                          SizedBox(
                            height: 40,
                            child: Text(
                              item['title']?.toString() ?? 'Sản phẩm tương tự',
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            item['price']?.toString() ?? 'Chưa có giá',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(color: Colors.red),
                          ),
                          Text(
                            item['source']?.toString() ?? '',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: Colors.grey,
                              fontSize: 12,
                            ),
                          ),
                          const Spacer(),
                          SizedBox(
                            width: double.infinity,
                            child: FilledButton(
                              onPressed: () => widget.onOpenProduct(link),
                              child: const Text('Xem sản phẩm ↗'),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
      ],
    );
  }
}
