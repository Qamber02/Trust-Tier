import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart';

class TrustTierService {
  TrustTierService({String? apiUrl})
      : apiUrl = apiUrl ??
            const String.fromEnvironment('TRUSTTIER_API_URL',
                defaultValue: 'http://127.0.0.1:8000');
  final String apiUrl;
  SupabaseClient? get _supabase =>
      Supabase.instance.isInitialized ? Supabase.instance.client : null;

  Future<List<Map<String, dynamic>>> jobs(String workerId) async {
    final uri = Uri.parse('$apiUrl/api/jobs').replace(queryParameters: {
      'worker_id': workerId,
      'status': 'requested',
      'limit': '100',
    });
    final response = await http.get(uri);
    if (response.statusCode != 200) throw Exception('Could not load jobs');
    return (jsonDecode(response.body) as List)
        .cast<Map<String, dynamic>>()
        .where((row) => !row['id'].toString().startsWith('DEL-'))
        .toList();
  }

  Future<void> recordJobAction(
      {required String jobId,
      required String workerId,
      required String action}) async {
    final response = await http.post(
        Uri.parse('$apiUrl/api/jobs/$jobId/actions'),
        headers: {'content-type': 'application/json'},
        body: jsonEncode({'worker_id': workerId, 'action': action}));
    if (response.statusCode >= 300) {
      throw Exception('Could not sync rider action');
    }
  }

  Future<List<Map<String, dynamic>>> trustHistory(String workerId) async {
    final response = await http.get(Uri.parse('$apiUrl/api/live/history'));
    if (response.statusCode != 200) throw Exception('Could not load history');
    return (jsonDecode(response.body) as List)
        .cast<Map<String, dynamic>>()
        .where((event) => event['worker_id'] == workerId)
        .toList();
  }

  Future<Map<String, dynamic>?> trustScoreRow(String workerId) async {
    final response = await http.get(Uri.parse('$apiUrl/api/trust-scores'));
    if (response.statusCode != 200) {
      throw Exception('Could not load trust score');
    }
    final rows =
        (jsonDecode(response.body) as List).cast<Map<String, dynamic>>();
    return rows.where((item) => item['worker_id'] == workerId).firstOrNull;
  }

  Future<double?> trustScore(String workerId) async {
    final row = await trustScoreRow(workerId);
    final score = row?['score'];
    return score is num ? score.toDouble().clamp(0, 1) : null;
  }

  RealtimeChannel? subscribeWorker(
          String workerId, void Function(Map<String, dynamic>) onChange) =>
      _supabase
          ?.channel('rider-$workerId')
          .onPostgresChanges(
              event: PostgresChangeEvent.all,
              schema: 'public',
              table: 'trust_scores',
              filter: PostgresChangeFilter(
                  type: PostgresChangeFilterType.eq,
                  column: 'worker_id',
                  value: workerId),
              callback: (payload) => onChange(payload.newRecord))
          .subscribe();
}
