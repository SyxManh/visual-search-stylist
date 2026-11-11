import 'dart:io';
import 'dart:convert';

import 'product_results.dart';
import 'style_advisor.dart';

import 'package:shared_preferences/shared_preferences.dart';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

void main() {
  runApp(const MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Visual Search + Stylist',
      theme: ThemeData(primarySwatch: Colors.indigo, useMaterial3: true),
      home: const SearchScreen(),
    );
  }
}

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});
  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  File? _image;
  File? _profileImage;
  String _mode = 'search';
  bool _isTryingOn = false;
  String? _tryOnResultUrl;
  bool _isDetecting = false;
  bool _isSearchingProducts = false;
  final ImagePicker _picker = ImagePicker();

  List<dynamic> _detectedItems = [];
  final Map<String, dynamic> _productsCache =
      {}; // Lưu cache kết quả theo crop_path

  String? _activeCropPath;
  String _tryOnClothType = 'upper';

  // Override per deployment with --dart-define=API_BASE_URL=https://your-api.example
  String serverUrl = const String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  Map<String, dynamic>? _currentSearchResult;

  @override
  void initState() {
    super.initState();
    _loadServerUrl();
  }

  Future<void> _loadServerUrl() async {
    final prefs = await SharedPreferences.getInstance();
    if (mounted) {
      setState(() => serverUrl = prefs.getString('serverUrl') ?? serverUrl);
    }
  }

  Future<void> _configureServer() async {
    final controller = TextEditingController(text: serverUrl);
    final value = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Kết nối máy chủ'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            labelText: 'URL máy chủ',
            hintText: 'https://...trycloudflare.com',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Kiểm tra và lưu'),
          ),
        ],
      ),
    );
    if (value == null || !mounted) return;
    final uri = Uri.tryParse(value);
    if (uri == null ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment ||
        (uri.path.isNotEmpty && uri.path != '/')) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Nhập URL HTTP/HTTPS gốc hợp lệ.')),
      );
      return;
    }
    final base = value.replaceFirst(RegExp(r'/+$'), '');
    try {
      final response = await http
          .get(
            Uri.parse('$base/health'),
            headers: {'ngrok-skip-browser-warning': 'true'},
          )
          .timeout(const Duration(seconds: 15));
      if (response.statusCode != 200 ||
          jsonDecode(response.body)['status'] != 'ok') {
        throw Exception('Máy chủ chưa sẵn sàng');
      }
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('serverUrl', base);
      if (!mounted) return;
      setState(() {
        serverUrl = base;
        _productsCache.clear();
        _detectedItems = [];
        _activeCropPath = null;
        _currentSearchResult = null;
        _tryOnResultUrl = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã kết nối và lưu máy chủ.')),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Không kết nối được: $e')));
      }
    }
  }

  @override
  void dispose() {
    super.dispose();
  }

  Future<void> _openProductLink(String link) async {
    try {
      final uri = Uri.tryParse(link);
      if (uri == null ||
          !['http', 'https'].contains(uri.scheme) ||
          uri.host.isEmpty ||
          !await launchUrl(uri, mode: LaunchMode.externalApplication)) {
        throw Exception('Không mở được liên kết.');
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'Không mở được liên kết. Hãy kiểm tra trình duyệt trên điện thoại.',
            ),
          ),
        );
      }
    }
  }

  Future<void> _pickProfileImage() async {
    final XFile? file = await _picker.pickImage(
      source: ImageSource.gallery,
      maxWidth: 1400,
      maxHeight: 2000,
      imageQuality: 90,
    );
    if (file != null && mounted) {
      setState(() => _profileImage = File(file.path));
    }
  }

  Future<void> _tryOn() async {
    if (_activeCropPath == null) return;
    if (_profileImage == null) {
      await _pickProfileImage();
      if (_profileImage == null) return;
    }
    if (!mounted) return;
    final consent = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Gửi ảnh để thử đồ?'),
        content: const Text(
          'Ảnh toàn thân và ảnh trang phục sẽ được gửi tới Cloudflare Workers AI qua máy chủ của bạn để tạo ảnh thử đồ. Lượt tạo dùng hạn mức Workers AI; gói trả phí có thể phát sinh chi phí khi vượt phần miễn phí. Chiều cao và cân nặng không được gửi. Chỉ tiếp tục với ảnh bạn có quyền sử dụng và khi bạn đồng ý gửi ảnh.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Hủy'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Tiếp tục'),
          ),
        ],
      ),
    );
    if (consent != true || !mounted) return;
    setState(() {
      _isTryingOn = true;
      _tryOnResultUrl = null;
    });
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$serverUrl/virtual-try-on'),
      );
      request.fields['crop_path'] = _activeCropPath!;
      request.fields['consent'] = 'true';
      request.fields['consent_provider'] = 'cloudflare';
      request.headers['ngrok-skip-browser-warning'] = 'true';
      request.fields['cloth_type'] = _tryOnClothType;
      request.files.add(
        await http.MultipartFile.fromPath('person', _profileImage!.path),
      );
      final response = await request.send().timeout(const Duration(minutes: 5));
      final body = jsonDecode(
        await response.stream.bytesToString().timeout(
          const Duration(minutes: 5),
        ),
      );
      if (!mounted) return;
      if (response.statusCode == 200 && body['result_url'] != null) {
        final resultUrl = body['result_url'].toString();
        setState(
          () =>
              _tryOnResultUrl = Uri.parse(serverUrl)
                  .resolve(resultUrl)
                  .toString(),
        );
      } else {
        throw Exception(body['error'] ?? 'Không tạo được ảnh thử đồ.');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Thử đồ thất bại: $e'),
            duration: const Duration(seconds: 6),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isTryingOn = false);
    }
  }

  String? get _activeGarmentUrl {
    for (final item in _detectedItems) {
      if (item['crop_path'] == _activeCropPath) {
        return Uri.parse(serverUrl)
            .resolve(item['crop_url'].toString())
            .toString();
      }
    }
    return null;
  }

  Future<void> _pickGarmentForTryOn() async {
    final file = await _picker.pickImage(
      source: ImageSource.gallery,
      maxWidth: 1600,
      maxHeight: 2000,
      imageQuality: 90,
    );
    if (file == null || !mounted) return;
    setState(() => _isDetecting = true);
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$serverUrl/upload-garment'),
      );
      request.headers['ngrok-skip-browser-warning'] = 'true';
      request.files.add(await http.MultipartFile.fromPath('file', file.path));
      final response = await request.send().timeout(
        const Duration(seconds: 45),
      );
      final data = jsonDecode(
        await response.stream.bytesToString(),
      ) as Map<String, dynamic>;
      if (response.statusCode != 200) {
        throw Exception(data['error'] ?? 'Không tải được ảnh trang phục');
      }
      if (!mounted) return;
      setState(() {
        _detectedItems.add(data);
        _activeCropPath = data['crop_path'].toString();
        _currentSearchResult = null;
        _tryOnResultUrl = null;
      });
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    } finally {
      if (mounted) setState(() => _isDetecting = false);
    }
  }

  Widget _buildStylePage() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        const Text(
          'Tạo ảnh AI mặc trang phục',
          style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 6),
        const Text(
          'Chọn ảnh toàn thân và ảnh trang phục, rồi bấm Tạo ảnh thử đồ. Ảnh chỉ gửi tới Cloudflare Workers AI sau khi bạn xác nhận; lượt tạo dùng hạn mức Workers AI miễn phí hằng ngày hoặc tính phí theo gói tài khoản.',
        ),
        const SizedBox(height: 16),
        Card(
          clipBehavior: Clip.antiAlias,
          child: InkWell(
            onTap: _pickProfileImage,
            child: SizedBox(
              height: 300,
              child: _profileImage == null
                  ? const Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.add_a_photo_outlined, size: 48),
                        SizedBox(height: 8),
                        Text('Thêm ảnh toàn thân, thấy rõ từ đầu đến chân'),
                      ],
                    )
                  : Image.file(_profileImage!, fit: BoxFit.contain),
            ),
          ),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: _pickProfileImage,
          icon: const Icon(Icons.photo),
          label: const Text('Chọn ảnh toàn thân'),
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: _isDetecting || _isTryingOn ? null : _pickGarmentForTryOn,
          icon: const Icon(Icons.checkroom),
          label: Text(
            _isDetecting
                ? 'Đang tải trang phục...'
                : 'Chọn ảnh trang phục muốn mặc',
          ),
        ),
        if (_activeGarmentUrl != null)
          SizedBox(
            height: 140,
            child: Image.network(_activeGarmentUrl!, fit: BoxFit.contain),
          ),
        const SizedBox(height: 12),
        DropdownButtonFormField<String>(
          initialValue: _tryOnClothType,
          decoration: const InputDecoration(
            labelText: 'Loại trang phục',
            border: OutlineInputBorder(),
          ),
          items: const [
            DropdownMenuItem(value: 'upper', child: Text('Áo')),
            DropdownMenuItem(value: 'lower', child: Text('Quần / chân váy')),
            DropdownMenuItem(value: 'overall', child: Text('Váy liền / bộ đồ')),
          ],
          onChanged: _isTryingOn
              ? null
              : (value) => setState(() => _tryOnClothType = value!),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: _activeCropPath == null || _isTryingOn || _isDetecting
              ? null
              : _tryOn,
          icon: const Icon(Icons.auto_awesome),
          label: Text(_isTryingOn ? 'Đang tạo ảnh...' : 'Tạo ảnh thử đồ'),
        ),
        if (_activeCropPath == null)
          const Text('Hãy chọn ảnh trang phục trước khi tạo ảnh.'),
        if (_tryOnResultUrl != null)
          Image.network(_tryOnResultUrl!, fit: BoxFit.contain),
        const SizedBox(height: 24),
        TextButton.icon(
          onPressed: () => setState(() => _mode = 'advice'),
          icon: const Icon(Icons.palette_outlined),
          label: const Text('Tư vấn phong cách theo ảnh, số đo & phong thủy'),
        ),
      ],
    );
  }

  // 1. Chụp ảnh hoặc chọn ảnh từ thư viện (Có tối ưu nén & resize để chống quá tải camera)
  Future<void> _pickImage(ImageSource source) async {
    final XFile? pickedFile = await _picker.pickImage(
      source: source,
      maxWidth: 1024,
      maxHeight: 1024,
      imageQuality: 85,
    );
    if (pickedFile != null && mounted) {
      setState(() {
        _image = File(pickedFile.path);
        _detectedItems = [];
        _productsCache.clear();
        _activeCropPath = null;
        _currentSearchResult = null;
        _isSearchingProducts = false;
      });
      _uploadAndDetect(File(pickedFile.path));
    }
  }

  // 2. Gửi ảnh gốc lên Python để YOLO cắt vật thể (/detect-objects)
  Future<void> _uploadAndDetect(File imageFile) async {
    setState(() {
      _isDetecting = true;
    });
    try {
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$serverUrl/detect-objects'),
      );
      request.files.add(
        await http.MultipartFile.fromPath('file', imageFile.path),
      );

      request.headers['ngrok-skip-browser-warning'] = 'true';
      var response = await request.send().timeout(const Duration(seconds: 90));
      if (response.statusCode == 200) {
        String responseBody = await response.stream.bytesToString();
        var data = jsonDecode(responseBody);

        if (!mounted) return;
        setState(() {
          _detectedItems = data['detected_items'] ?? [];
        });
      } else {
        final body = jsonDecode(await response.stream.bytesToString());
        throw Exception(
          body['error'] ?? 'Server trả về mã ${response.statusCode}.',
        );
      }
    } catch (e) {
      debugPrint("Lỗi nhận diện: $e");
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Lỗi kết nối server: $e')));
      }
    } finally {
      if (mounted) {
        setState(() {
          _isDetecting = false;
        });
      }
    }
  }

  Future<void> _fetchProductsForCrop(
    String cropPath, {
    bool refresh = false,
  }) async {
    if (_activeCropPath == cropPath && _isSearchingProducts) return;
    if (refresh) _productsCache.remove(cropPath);
    final cached = _productsCache[cropPath];
    setState(() {
      _activeCropPath = cropPath;
      _currentSearchResult = cached;
      _isSearchingProducts = cached == null;
    });
    if (cached != null) return;
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('$serverUrl/search-products'),
      );
      request.fields['crop_path'] = cropPath;
      request.headers['ngrok-skip-browser-warning'] = 'true';
      final response = await request.send().timeout(
        const Duration(seconds: 65),
      );
      final body = await response.stream.bytesToString().timeout(
        const Duration(seconds: 15),
      );
      final data = jsonDecode(body) as Map<String, dynamic>;
      if (response.statusCode != 200) {
        throw Exception(
          data['error'] ?? 'Máy chủ trả mã ${response.statusCode}',
        );
      }
      if (!mounted) return;
      // Only successful image matches are cached; missing-key/error states can be retried.
      if (data['status'] == 'ready' &&
          _detectedItems.any((item) => item['crop_path'] == cropPath)) {
        _productsCache[cropPath] = data;
      }
      if (_activeCropPath == cropPath) {
        setState(() => _currentSearchResult = data);
      }
    } catch (_) {
      if (mounted && _activeCropPath == cropPath) {
        setState(
          () => _currentSearchResult = {
            'status': 'connection_error',
            'message': 'Không tải được danh sách sản phẩm. Kiểm tra kết nối máy chủ rồi thử lại.',
            'products': <String, dynamic>{},
          },
        );
      }
    } finally {
      if (mounted && _activeCropPath == cropPath) {
        setState(() => _isSearchingProducts = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Visual Search + Stylist · v1.6.0"),
        centerTitle: true,
        actions: [
          IconButton(
            tooltip: 'Kết nối máy chủ',
            onPressed: _isDetecting || _isSearchingProducts || _isTryingOn
                ? null
                : _configureServer,
            icon: const Icon(Icons.settings_ethernet),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
            child: SegmentedButton<String>(
              showSelectedIcon: false,
              style: const ButtonStyle(visualDensity: VisualDensity.compact),
              segments: const [
                ButtonSegment(value: 'search', label: Text('Tìm sản phẩm')),
                ButtonSegment(value: 'style', label: Text('Thử đồ AI')),
                ButtonSegment(value: 'advice', label: Text('Tư vấn')),
              ],
              selected: {_mode},
              onSelectionChanged: (selection) =>
                  setState(() => _mode = selection.first),
            ),
          ),
          Expanded(
            child: IndexedStack(
              index: _mode == 'search'
                  ? 0
                  : _mode == 'style'
                  ? 1
                  : 2,
              children: [
                SingleChildScrollView(
                  padding: const EdgeInsets.all(12.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Thanh nút chọn ảnh
                      Row(
                        children: [
                          Expanded(
                            child: ElevatedButton.icon(
                              onPressed: () => _pickImage(ImageSource.camera),
                              icon: const Icon(Icons.camera_alt),
                              label: const Text("Chụp ảnh"),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: ElevatedButton.icon(
                              style: ElevatedButton.styleFrom(
                                backgroundColor: Colors.grey[800],
                                foregroundColor: Colors.white,
                              ),
                              onPressed: () => _pickImage(ImageSource.gallery),
                              icon: const Icon(Icons.photo_library),
                              label: const Text("Thư viện"),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 15),
                      // Khu vực hiển thị ảnh gốc
                      if (_image != null) ...[
                        const Text(
                          "1. Ảnh gốc:",
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.grey,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Container(
                          height: 200,
                          width: double.infinity,
                          decoration: BoxDecoration(
                            color: Colors.grey[200],
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(10),
                            child: Image.file(_image!, fit: BoxFit.contain),
                          ),
                        ),
                        const SizedBox(height: 15),
                      ],
                      // Trạng thái đang nhận diện YOLO
                      if (_isDetecting) ...[
                        const Center(child: CircularProgressIndicator()),
                        const SizedBox(height: 8),
                        const Center(
                          child: Text("YOLO-World đang bóc tách vật thể..."),
                        ),
                      ],
                      // Danh sách các vật thể cắt ra (Crops)
                      if (_detectedItems.isNotEmpty) ...[
                        const Text(
                          "2. Chọn món đồ muốn tìm link:",
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.grey,
                          ),
                        ),
                        const SizedBox(height: 8),
                        SizedBox(
                          height: 110,
                          child: ListView.builder(
                            scrollDirection: Axis.horizontal,
                            itemCount: _detectedItems.length,
                            itemBuilder: (context, index) {
                              var item = _detectedItems[index];
                              String cropUrl = serverUrl + item['crop_url'];
                              bool isSelected =
                                  _activeCropPath == item['crop_path'];
                              return GestureDetector(
                                onTap: () =>
                                    _fetchProductsForCrop(item['crop_path']),
                                child: Container(
                                  width: 90,
                                  margin: const EdgeInsets.only(right: 10),
                                  padding: const EdgeInsets.all(6),
                                  decoration: BoxDecoration(
                                    color: isSelected
                                        ? Colors.indigo.shade50
                                        : Colors.white,
                                    border: Border.all(
                                      color: isSelected
                                          ? Colors.indigo
                                          : Colors.grey.shade300,
                                      width: isSelected ? 2 : 1,
                                    ),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Expanded(
                                        child: ClipRRect(
                                          borderRadius: BorderRadius.circular(
                                            6,
                                          ),
                                          child: Image.network(
                                            cropUrl,
                                            fit: BoxFit.cover,
                                            width: double.infinity,
                                          ),
                                        ),
                                      ),
                                      const SizedBox(height: 4),
                                      Text(
                                        item['label'],
                                        style: TextStyle(
                                          fontSize: 11,
                                          fontWeight: FontWeight.bold,
                                          color: isSelected
                                              ? Colors.indigo
                                              : Colors.black87,
                                        ),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                        ),
                        const SizedBox(height: 20),
                      ],
                      // Khu vực hiển thị kết quả các sàn (Shopee, Lazada, Amazon...)
                      if (_activeCropPath != null) ...[
                        const Text(
                          "3. Kết quả tìm kiếm sản phẩm:",
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.grey,
                          ),
                        ),
                        const SizedBox(height: 8),
                        ...[
                          SizedBox(
                            width: double.infinity,
                            child: FilledButton.icon(
                              onPressed: _isTryingOn ? null : _tryOn,
                              icon: const Icon(Icons.checkroom),
                              label: Text(
                                _isTryingOn
                                    ? 'Đang tạo ảnh thử đồ...'
                                    : 'Mặc thử trang phục này',
                              ),
                            ),
                          ),
                          if (_isTryingOn)
                            const Padding(
                              padding: EdgeInsets.all(16),
                              child: Center(child: CircularProgressIndicator()),
                            ),
                          if (_tryOnResultUrl != null) ...[
                            const SizedBox(height: 8),
                            ClipRRect(
                              borderRadius: BorderRadius.circular(12),
                              child: Image.network(
                                _tryOnResultUrl!,
                                fit: BoxFit.contain,
                              ),
                            ),
                            const Text(
                              'Ảnh mô phỏng bằng AI; kết quả có thể khác thực tế.',
                              style: TextStyle(
                                fontSize: 12,
                                color: Colors.black54,
                              ),
                            ),
                          ],
                          const SizedBox(height: 12),
                        ],
                        ProductResultsPanel(
                          key: ValueKey(_activeCropPath),
                          result: _currentSearchResult,
                          loading: _isSearchingProducts,
                          hasSelection: _activeCropPath != null,
                          onRetry: () {
                            final crop = _activeCropPath;
                            if (crop != null) {
                              _fetchProductsForCrop(crop, refresh: true);
                            }
                          },
                          onOpenProduct: _openProductLink,
                        ),
                      ],
                    ],
                  ),
                ),
                _buildStylePage(),
                StyleAdvisorPage(
                  serverUrl: serverUrl,
                  initialPhoto: _profileImage,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
