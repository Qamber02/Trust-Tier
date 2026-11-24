import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

/// API access with an optional Supabase Realtime channel. UI can retain its
/// current in-memory Store when API/Supabase are not configured or reachable.
class TrustTierService {
  TrustTierService({String? apiUrl})
      : apiUrl = apiUrl ??
            const String.fromEnvironment('TRUSTTIER_API_URL',
                defaultValue: 'http://127.0.0.1:8000');

  final String apiUrl;
  final String clientId = const String.fromEnvironment('TRUSTTIER_CLIENT_ID',
      defaultValue: 'CLT-0350');
  SupabaseClient? get _supabase =>
      Supabase.instance.isInitialized ? Supabase.instance.client : null;

  Future<List<Map<String, dynamic>>> workers() async {
    final response = await http.get(Uri.parse('$apiUrl/api/riders'));
    if (response.statusCode != 200) throw Exception('Could not load workers');
    return (jsonDecode(response.body) as List).cast<Map<String, dynamic>>();
  }

  Future<List<Map<String, dynamic>>> trustScores() async {
    final response = await http.get(Uri.parse('$apiUrl/api/trust-scores'));
    if (response.statusCode != 200) {
      throw Exception('Could not load trust scores');
    }
    return (jsonDecode(response.body) as List)
        .cast<Map<String, dynamic>>()
        .where((row) => !row['id'].toString().startsWith('DEL-'))
        .toList();
  }

  Future<Map<String, dynamic>> createJob(
      {required String workerId,
      required String clientId,
      required String title,
      required String address}) async {
    final response = await http.post(Uri.parse('$apiUrl/api/jobs'),
        headers: {'content-type': 'application/json'},
        body: jsonEncode({
          'worker_id': workerId,
          'client_id': clientId,
          'title': title,
          'address': address
        }));
    if (response.statusCode >= 300) throw Exception('Could not request worker');
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<List<Map<String, dynamic>>> jobsForClient(String clientId) async {
    final uri = Uri.parse('$apiUrl/api/jobs').replace(queryParameters: {
      'client_id': clientId,
      'limit': '100',
    });
    final response = await http.get(uri);
    if (response.statusCode != 200) throw Exception('Could not load your jobs');
    return (jsonDecode(response.body) as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> confirmJob(
      {required String jobId,
      required String clientId,
      required int stars,
      required String body}) async {
    final response = await http.post(
        Uri.parse('$apiUrl/api/jobs/$jobId/confirm'),
        headers: {'content-type': 'application/json'},
        body:
            jsonEncode({'client_id': clientId, 'stars': stars, 'body': body}));
    if (response.statusCode >= 300) {
      throw Exception('Could not confirm delivery');
    }
    return jsonDecode(response.body) as Map<String, dynamic>;
  }

  Future<void> createReview(Map<String, dynamic> review) async {
    final response = await http.post(Uri.parse('$apiUrl/api/reviews'),
        headers: {'content-type': 'application/json'},
        body: jsonEncode(review));
    if (response.statusCode >= 300) throw Exception('Could not save review');
  }

  Future<void> createDispute(Map<String, dynamic> dispute) async {
    final response = await http.post(Uri.parse('$apiUrl/api/disputes'),
        headers: {'content-type': 'application/json'},
        body: jsonEncode(dispute));
    if (response.statusCode >= 300) throw Exception('Could not submit dispute');
  }

  Future<void> updateJobStatus(String jobId, String status) async {
    if (status != 'cancelled') throw ArgumentError.value(status, 'status');
    final response = await http.post(Uri.parse(
        '$apiUrl/api/jobs/$jobId/cancel?client_id=${Uri.encodeQueryComponent(clientId)}'));
    if (response.statusCode >= 300) throw Exception('Could not cancel job');
  }

  RealtimeChannel? subscribeTrustScores(
          void Function(Map<String, dynamic>) onChange) =>
      _supabase
          ?.channel('customer-trust-scores')
          .onPostgresChanges(
              event: PostgresChangeEvent.all,
              schema: 'public',
              table: 'trust_scores',
              callback: (payload) => onChange(payload.newRecord))
          .subscribe();
}
