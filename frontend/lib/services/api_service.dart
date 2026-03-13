import 'dart:convert';
import 'package:http/http.dart' as http;

import '../models/wine_recommendation.dart';
import '../models/merchant.dart';

class ApiService {
  // Android emulator routes 10.0.2.2 → host machine's localhost.
  // For a physical device or iOS simulator, replace with your machine's LAN IP
  // e.g. 'http://192.168.1.X:8000'
  static const String _baseUrl = 'http://localhost:8000';

  Future<String> fetchHello() async {
    final response = await http.get(Uri.parse('$_baseUrl/hello'));
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return data['message'] as String;
    }
    throw Exception('Server returned status ${response.statusCode}');
  }

  Future<List<WineRecommendation>> recommend({
    required int crispnessAcidity,
    required int weightBody,
    required int textureTannin,
    required int flavorIntensity,
    required String foodPairing,
  }) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/recommend'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'crispness_acidity': crispnessAcidity,
        'weight_body': weightBody,
        'texture_tannin': textureTannin,
        'flavor_intensity': flavorIntensity,
        'food_pairing': foodPairing,
      }),
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return (data['recommendations'] as List)
          .map((r) => WineRecommendation.fromJson(r as Map<String, dynamic>))
          .toList();
    }
    throw Exception('Server returned status ${response.statusCode}');
  }

  Future<List<Merchant>> nearby({
    required String wineName,
    required double userLat,
    required double userLng,
    required double budgetMin,
    required double budgetMax,
  }) async {
    final response = await http.post(
      Uri.parse('$_baseUrl/nearby'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'wine_name': wineName,
        'user_lat': userLat,
        'user_lng': userLng,
        'budget_min': budgetMin,
        'budget_max': budgetMax,
      }),
    );
    if (response.statusCode == 200) {
      final data = jsonDecode(response.body) as Map<String, dynamic>;
      return (data['merchants'] as List)
          .map((m) => Merchant.fromJson(m as Map<String, dynamic>))
          .toList();
    }
    throw Exception('Server returned status ${response.statusCode}');
  }
}
