import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';

class StyleAdvisorPage extends StatefulWidget {
  const StyleAdvisorPage({
    super.key,
    required this.serverUrl,
    this.initialPhoto,
    this.client,
  });
  final String serverUrl;
  final File? initialPhoto;
  final http.Client? client;

  @override
  State<StyleAdvisorPage> createState() => _StyleAdvisorPageState();
}

class _StyleAdvisorPageState extends State<StyleAdvisorPage> {
  final _height = TextEditingController();
  final _weight = TextEditingController();
  late final http.Client _client;
  File? _photo;
  DateTime? _birthDate;
  bool _withFengShui = false;
  bool _consent = false;
  bool _busy = false;
  String _occasion = 'daily';
  String _preference = 'minimal';
  String _message = '';
  String? _advice;
  Map<String, dynamic>? _fengShui;
  int _revision = 0;

  @override
  void initState() {
    super.initState();
    _client = widget.client ?? http.Client();
    _photo = widget.initialPhoto;
  }

  @override
  void didUpdateWidget(covariant StyleAdvisorPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.serverUrl != widget.serverUrl) {
      _revision++;
      _busy = false;
      _advice = null;
      _message = '';
    }
    if (oldWidget.initialPhoto?.path != widget.initialPhoto?.path && !_busy) {
      _photo = widget.initialPhoto;
      _advice = null;
      _consent = false;
    }
  }

  @override
  void dispose() {
    _height.dispose();
    _weight.dispose();
    if (widget.client == null) _client.close();
    super.dispose();
  }

  void _invalidate() {
    _advice = null;
    _message = '';
  }

  String get _isoBirth => _birthDate == null
      ? ''
      : '${_birthDate!.year.toString().padLeft(4, '0')}-${_birthDate!.month.toString().padLeft(2, '0')}-${_birthDate!.day.toString().padLeft(2, '0')}';

  Future<void> _pickPhoto() async {
    final picked = await ImagePicker().pickImage(
      source: ImageSource.gallery,
      maxWidth: 1400,
      maxHeight: 2000,
      imageQuality: 88,
    );
    if (picked == null || !mounted) return;
    setState(() {
      _photo = File(picked.path);
      _consent = false;
      _invalidate();
    });
  }

  Future<void> _pickBirthDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _birthDate ?? DateTime(2000, 1, 1),
      firstDate: DateTime(1900, 1, 1),
      lastDate: DateTime.now(),
      helpText: 'Chọn ngày sinh dương lịch',
    );
    if (picked == null || !mounted) return;
    setState(() {
      _birthDate = picked;
      _fengShui = null;
      _invalidate();
    });
  }

  Future<void> _request({required bool ai}) async {
    if (_busy) return;
    final withPalette = !ai || _withFengShui;
    final height = double.tryParse(_height.text.trim().replaceAll(',', '.'));
    final weight = double.tryParse(_weight.text.trim().replaceAll(',', '.'));
    String? problem;
    if (withPalette && _birthDate == null) {
      problem = 'Hãy chọn ngày sinh dương lịch trước.';
    }
    if (ai) {
      if (_photo == null) {
        problem = 'Hãy chọn ảnh toàn thân để AI xem trang phục của bạn.';
      } else if (height == null ||
          weight == null ||
          !height.isFinite ||
          !weight.isFinite ||
          height < 50 ||
          height > 250 ||
          weight < 5 ||
          weight > 350) {
        problem = 'Nhập chiều cao 50–250 cm và cân nặng 5–350 kg; kiểm tra lại đơn vị.';
      } else if (!_consent) {
        problem =
            'Cần đồng ý gửi ảnh và số đo tới Cloudflare để nhận tư vấn AI.';
      }
    }
    if (problem != null) {
      setState(() => _message = problem!);
      return;
    }
    final revision = ++_revision;
    setState(() {
      _busy = true;
      _message = ai
          ? 'AI đang xem ảnh và tư vấn phối đồ…'
          : 'Đang tra màu phong thủy…';
      if (ai) _advice = null;
    });
    try {
      final request = http.MultipartRequest(
        'POST',
        Uri.parse('${widget.serverUrl}/${ai ? 'style-advice' : 'feng-shui'}'),
      );
      request.headers['ngrok-skip-browser-warning'] = 'true';
      if (withPalette) request.fields['birth_date'] = _isoBirth;
      if (ai) {
        if (await _photo!.length() > 12 * 1024 * 1024) {
          throw Exception('Ảnh vượt quá 12 MB. Hãy chọn ảnh nhỏ hơn.');
        }
        request.fields.addAll({
          'height_cm': height.toString(),
          'weight_kg': weight.toString(),
          'occasion': _occasion,
          'preference': _preference,
          'consent': 'true',
          'consent_provider': 'cloudflare',
        });
        request.files.add(
          await http.MultipartFile.fromPath('person', _photo!.path),
        );
      }
      final response = await _client
          .send(request)
          .timeout(const Duration(seconds: 150));
      final body = jsonDecode(
        await response.stream.bytesToString().timeout(
          const Duration(seconds: 150),
        ),
      ) as Map<String, dynamic>;
      if (!mounted || revision != _revision) return;
      setState(() {
        _fengShui = body['feng_shui'] is Map
            ? Map<String, dynamic>.from(body['feng_shui'])
            : null;
        _advice =
            body['advice'] is String && (body['advice'] as String).isNotEmpty
            ? body['advice'] as String
            : null;
        _message = response.statusCode == 200
            ? (ai
                  ? 'Đã nhận tư vấn dựa trên ảnh và hồ sơ của bạn.'
                  : 'Đã tra màu theo năm sinh âm lịch.')
            : (body['error'] ?? 'Chưa nhận được kết quả. Vui lòng thử lại.')
                  .toString();
      });
    } catch (error) {
      if (mounted && revision == _revision) {
        setState(
          () => _message = error is FormatException
              ? 'Máy chủ chưa có tính năng tư vấn hoặc trả dữ liệu chưa hợp lệ. Kiểm tra bản cập nhật máy chủ.'
              : 'Không nhận được tư vấn: $error',
        );
      }
    } finally {
      if (mounted && revision == _revision) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => ListView(
    key: const ValueKey('advisorList'),
    padding: const EdgeInsets.all(16),
    children: [
      const Text(
        'Tư vấn phong cách & phong thủy',
        style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
      ),
      const SizedBox(height: 8),
      const Text(
        'AI kết hợp ảnh, chiều cao, cân nặng và sở thích để gợi ý phom, cách phối màu và ba bộ đồ phù hợp.',
      ),
      const SizedBox(height: 12),
      if (_photo != null)
        SizedBox(height: 220, child: Image.file(_photo!, fit: BoxFit.contain)),
      OutlinedButton.icon(
        onPressed: _busy ? null : _pickPhoto,
        icon: const Icon(Icons.add_photo_alternate_outlined),
        label: const Text('Chọn ảnh để AI tư vấn'),
      ),
      const SizedBox(height: 12),
      Row(
        children: [
          Expanded(
            child: TextField(
              controller: _height,
              enabled: !_busy,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(
                labelText: 'Chiều cao (cm)',
                border: OutlineInputBorder(),
              ),
              onChanged: (_) => setState(_invalidate),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _weight,
              enabled: !_busy,
              keyboardType: const TextInputType.numberWithOptions(
                decimal: true,
              ),
              decoration: const InputDecoration(
                labelText: 'Cân nặng (kg)',
                border: OutlineInputBorder(),
              ),
              onChanged: (_) => setState(_invalidate),
            ),
          ),
        ],
      ),
      const SizedBox(height: 12),
      DropdownButtonFormField<String>(
        initialValue: _occasion,
        decoration: const InputDecoration(
          labelText: 'Bạn mặc trong dịp nào?',
          border: OutlineInputBorder(),
        ),
        items: const [
          DropdownMenuItem(value: 'daily', child: Text('Đi học / hằng ngày')),
          DropdownMenuItem(value: 'work', child: Text('Đi làm')),
          DropdownMenuItem(value: 'outing', child: Text('Đi chơi')),
          DropdownMenuItem(value: 'event', child: Text('Dự tiệc / sự kiện')),
        ],
        onChanged: _busy
            ? null
            : (value) => setState(() {
                _occasion = value!;
                _invalidate();
              }),
      ),
      const SizedBox(height: 12),
      DropdownButtonFormField<String>(
        initialValue: _preference,
        decoration: const InputDecoration(
          labelText: 'Phong cách bạn thích',
          border: OutlineInputBorder(),
        ),
        items: const [
          DropdownMenuItem(value: 'minimal', child: Text('Tối giản')),
          DropdownMenuItem(
            value: 'smart_casual',
            child: Text('Lịch sự thoải mái'),
          ),
          DropdownMenuItem(value: 'streetwear', child: Text('Streetwear')),
          DropdownMenuItem(value: 'elegant', child: Text('Thanh lịch')),
          DropdownMenuItem(value: 'sporty', child: Text('Năng động')),
        ],
        onChanged: _busy
            ? null
            : (value) => setState(() {
                _preference = value!;
                _invalidate();
              }),
      ),
      const SizedBox(height: 12),
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('Thêm gợi ý phong thủy (tùy chọn)'),
        subtitle: const Text('Tra ngũ hành và màu sắc theo năm sinh âm lịch.'),
        value: _withFengShui,
        onChanged: _busy
            ? null
            : (value) => setState(() {
                _withFengShui = value;
                _fengShui = null;
                _invalidate();
              }),
      ),
      if (_withFengShui) ...[
        OutlinedButton.icon(
          onPressed: _busy ? null : _pickBirthDate,
          icon: const Icon(Icons.calendar_month),
          label: Text(
            _birthDate == null
                ? 'Chọn ngày sinh dương lịch'
                : '${_birthDate!.day}/${_birthDate!.month}/${_birthDate!.year} (dương lịch)',
          ),
        ),
        TextButton(
          onPressed: _busy ? null : () => _request(ai: false),
          child: const Text('Xem màu phong thủy, không gọi AI'),
        ),
        const Text(
          'Ngày sinh được tra tại máy chủ của bạn. AI chỉ nhận nhóm màu, không nhận ngày sinh đầy đủ.',
          style: TextStyle(fontSize: 12, color: Colors.black54),
        ),
      ],
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        value: _consent,
        onChanged: _busy
            ? null
            : (value) => setState(() => _consent = value ?? false),
        title: const Text(
          'Tôi đồng ý gửi ảnh, chiều cao và cân nặng tới Cloudflare để nhận tư vấn AI.',
        ),
        subtitle: const Text(
          'Dùng chung hạn mức Workers AI. Không tự lưu hồ sơ hoặc ngày sinh.',
        ),
      ),
      FilledButton.icon(
        onPressed: _busy ? null : () => _request(ai: true),
        icon: const Icon(Icons.auto_awesome),
        label: Text(_busy ? 'Đang xử lý…' : 'Nhận tư vấn AI'),
      ),
      if (_message.isNotEmpty)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(_message),
        ),
      if (_advice != null)
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: SelectionArea(child: Text(_advice!)),
          ),
        ),
      if (_fengShui != null) FengShuiResult(result: _fengShui!),
      const SizedBox(height: 12),
      const Text(
        'Số đo và ảnh không xác định chính xác size. Gợi ý phong thủy là cảm hứng theo quan niệm truyền thống, không bảo đảm vận may.',
        style: TextStyle(fontSize: 12, color: Colors.black54),
      ),
    ],
  );
}

class FengShuiResult extends StatelessWidget {
  const FengShuiResult({super.key, required this.result});
  final Map<String, dynamic> result;

  @override
  Widget build(BuildContext context) => Card(
    color: const Color(0xFFFFF7ED),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Ngũ hành ${result['element']} · ${result['nap_am']}',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text('Năm âm lịch ${result['lunar_year']} · ${result['can_chi']}'),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 4,
            children: [
              for (final entry in (result['colors'] as List? ?? []))
                if (entry is Map)
                  Chip(
                    avatar: CircleAvatar(backgroundColor: _color(entry['hex'])),
                    label: Text('${entry['label']} · ${entry['relation']}'),
                  ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            (result['method'] ?? '').toString(),
            style: const TextStyle(fontSize: 12),
          ),
          const SizedBox(height: 8),
          Text(
            (result['note'] ?? '').toString(),
            style: const TextStyle(fontSize: 12, color: Colors.black54),
          ),
        ],
      ),
    ),
  );

  Color _color(dynamic value) {
    final text = value.toString();
    return RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(text)
        ? Color(int.parse('FF${text.substring(1)}', radix: 16))
        : Colors.grey;
  }
}
