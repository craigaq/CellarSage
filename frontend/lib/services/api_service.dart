import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../models/wine_recommendation.dart';
import '../models/merchant.dart';
import '../models/wine_picks.dart';

class ApiService {
  // Singleton — one shared http.Client across all callers.
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal();

  final http.Client _client = http.Client();

  // Debug → Android emulator loopback. Release → production FastAPI host.
  static final String _baseUrl = kReleaseMode
      ? 'https://cellarsage-api.fly.dev'
      : 'http://10.0.2.2:8002';

  Future<String> fetchHello() async {
    final response = await _client.get(Uri.parse('$_baseUrl/hello'));
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['message'] as String;
    }
    throw Exception('Server returned status ${response.statusCode}');
  }

  Future<({
    List<WineRecommendation> recommendations,
    ConflictAlert? alert,
    GastroClash? gastroClash,
    PalateParadox? palateParadox,
  })> recommend({
    required int crispnessAcidity,
    required int weightBody,
    required int textureTannin,
    required int flavorIntensity,
    required String foodPairing,
    bool prefDry = false,
    String overrideMode = 'use_pairing_logic',
    String pairingMode = 'congruent',
  }) async {
    final response = await _client.post(
      Uri.parse('$_baseUrl/recommend'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'crispness_acidity': crispnessAcidity,
        'weight_body': weightBody,
        'texture_tannin': textureTannin,
        'flavor_intensity': flavorIntensity,
        'food_pairing': foodPairing,
        'pref_dry': prefDry,
        'override_mode': overrideMode,
        'pairing_mode': pairingMode,
      }),
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final recommendations = (data['recommendations'] as List)
          .map((r) => WineRecommendation.fromJson(r as Map<String, dynamic>))
          .toList();
      final alertJson   = data['conflict_alert']   as Map<String, dynamic>?;
      final gastroJson  = data['gastro_clash']      as Map<String, dynamic>?;
      final paradoxJson = data['pairing_conflict']  as Map<String, dynamic>?;
      return (
        recommendations: recommendations,
        alert:         alertJson   != null ? ConflictAlert.fromJson(alertJson)     : null,
        gastroClash:   gastroJson  != null ? GastroClash.fromJson(gastroJson)      : null,
        palateParadox: paradoxJson != null ? PalateParadox.fromJson(paradoxJson)   : null,
      );
    }
    throw Exception('Server returned status ${response.statusCode}');
  }

  Future<({GastroClash? gastroClash, PalateParadox? palateParadox})> checkPairing({
    required String foodType,
    required int crispnessAcidity,
    required int weightBody,
    required int textureTannin,
    required int flavorIntensity,
    bool prefDry = false,
  }) async {
    final uri = Uri.parse('$_baseUrl/check-pairing').replace(queryParameters: {
      'food_type': foodType,
      'crispness_acidity': '$crispnessAcidity',
      'weight_body': '$weightBody',
      'texture_tannin': '$textureTannin',
      'flavor_intensity': '$flavorIntensity',
      'pref_dry': '$prefDry',
    });
    final response = await _client
        .get(uri)
        .timeout(const Duration(seconds: 8));
    if (response.statusCode == 200) {
      final data        = jsonDecode(response.body) as Map<String, dynamic>;
      final clashJson   = data['gastro_clash']     as Map<String, dynamic>?;
      final paradoxJson = data['pairing_conflict'] as Map<String, dynamic>?;
      return (
        gastroClash:   clashJson   != null ? GastroClash.fromJson(clashJson)     : null,
        palateParadox: paradoxJson != null ? PalateParadox.fromJson(paradoxJson) : null,
      );
    }
    throw Exception('Server returned status ${response.statusCode}');
  }

  Future<List<BuyOption>> buyOptions({
    required String varietal,
    double budgetMin = 0.0,
    double budgetMax = 9999.0,
  }) async {
    final uri = Uri.parse('$_baseUrl/buy-options').replace(queryParameters: {
      'varietal': varietal,
      'budget_min': '$budgetMin',
      'budget_max': '$budgetMax',
    });
    final response = await _client.get(uri);
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as List;
      return data
          .map((o) => BuyOption.fromJson(o as Map<String, dynamic>))
          .toList();
    }
    throw Exception('Server returned status ${response.statusCode}');
  }

  Future<WinePicksResponse> winePicks({
    required String varietal,
    String? userState,
    double budgetMin = 0.0,
    double budgetMax = 9999.0,
    bool prefDry = false,
  }) async {
    final params = <String, String>{
      'varietal': varietal,
      'budget_min': '$budgetMin',
      'budget_max': '$budgetMax',
      'pref_dry': '$prefDry',
    };
    if (userState != null) params['user_state'] = userState;
    final uri = Uri.parse('$_baseUrl/wine-picks').replace(queryParameters: params);
    final response = await _client.get(uri);
    if (response.statusCode == 200) {
      return WinePicksResponse.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw Exception('Server returned status ${response.statusCode}');
  }

  Future<NearbyResponse> nearby({
    required String wineName,
    required double userLat,
    required double userLng,
    required double budgetMin,
    required double budgetMax,
    bool showGlobalTier = false,
    String currencyCode = 'AUD',
  }) async {
    final response = await _client.post(
      Uri.parse('$_baseUrl/nearby'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'wine_name':        wineName,
        'user_lat':         userLat,
        'user_lng':         userLng,
        'budget_min':       budgetMin,
        'budget_max':       budgetMax,
        'show_global_tier': showGlobalTier,
        'currency_code':    currencyCode,
      }),
    );
    if (response.statusCode == 200) {
      return NearbyResponse.fromJson(
        jsonDecode(response.body) as Map<String, dynamic>,
      );
    }
    throw Exception('Server returned status ${response.statusCode}');
  }
}
