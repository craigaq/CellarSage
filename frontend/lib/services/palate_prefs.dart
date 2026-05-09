import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

/// Persists the user's palate quiz answers between app sessions.
class PalatePrefs {
  static const _kCrispness   = 'palate_crispness';
  static const _kWeight      = 'palate_weight';
  static const _kTexture     = 'palate_texture';
  static const _kFlavor      = 'palate_flavor';
  static const _kFoodPairing = 'palate_food_pairing';
  static const _kBudgetIndex = 'palate_budget_index';
  static const _kPrefDry     = 'palate_pref_dry';
  static const _kProfiles    = 'palate_named_profiles';

  static const int maxProfiles = 5;

  static Future<PalateSnapshot?> load() async {
    final prefs = await SharedPreferences.getInstance();
    if (!prefs.containsKey(_kCrispness)) return null;
    return PalateSnapshot(
      crispness:   prefs.getInt(_kCrispness)     ?? 3,
      weight:      prefs.getInt(_kWeight)         ?? 3,
      texture:     prefs.getInt(_kTexture)        ?? 3,
      flavor:      prefs.getInt(_kFlavor)         ?? 3,
      foodPairing: prefs.getString(_kFoodPairing) ?? 'none',
      budgetIndex: prefs.getInt(_kBudgetIndex)    ?? 1,
      prefDry:     prefs.getBool(_kPrefDry)       ?? false,
    );
  }

  static Future<void> save({
    required int crispness,
    required int weight,
    required int texture,
    required int flavor,
    required String foodPairing,
    required int budgetIndex,
    required bool prefDry,
  }) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_kCrispness, crispness);
    await prefs.setInt(_kWeight, weight);
    await prefs.setInt(_kTexture, texture);
    await prefs.setInt(_kFlavor, flavor);
    await prefs.setString(_kFoodPairing, foodPairing);
    await prefs.setInt(_kBudgetIndex, budgetIndex);
    await prefs.setBool(_kPrefDry, prefDry);
  }

  // ---------------------------------------------------------------------------
  // Named profiles (up to maxProfiles)
  // ---------------------------------------------------------------------------

  static Future<List<PalateProfile>> loadProfiles() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kProfiles);
    if (raw == null) return [];
    try {
      final list = json.decode(raw) as List<dynamic>;
      return list
          .map((e) => PalateProfile.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {
      return [];
    }
  }

  /// Saves a named profile. If a profile with the same name already exists
  /// it is replaced in-place; otherwise it is appended (up to maxProfiles).
  /// Returns false if the list is already full and no match by name exists.
  static Future<bool> saveProfile(String name, PalateSnapshot snap) async {
    final prefs = await SharedPreferences.getInstance();
    final profiles = await loadProfiles();
    final profile = PalateProfile(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      name: name,
      crispness:   snap.crispness,
      weight:      snap.weight,
      texture:     snap.texture,
      flavor:      snap.flavor,
      foodPairing: snap.foodPairing,
      budgetIndex: snap.budgetIndex,
      prefDry:     snap.prefDry,
    );
    final idx = profiles.indexWhere((p) => p.name == name);
    if (idx >= 0) {
      profiles[idx] = profile;
    } else if (profiles.length >= maxProfiles) {
      return false;
    } else {
      profiles.add(profile);
    }
    await prefs.setString(
      _kProfiles,
      json.encode(profiles.map((p) => p.toJson()).toList()),
    );
    return true;
  }

  static Future<void> deleteProfile(String id) async {
    final prefs = await SharedPreferences.getInstance();
    final profiles = await loadProfiles();
    profiles.removeWhere((p) => p.id == id);
    await prefs.setString(
      _kProfiles,
      json.encode(profiles.map((p) => p.toJson()).toList()),
    );
  }
}

class PalateSnapshot {
  final int crispness;
  final int weight;
  final int texture;
  final int flavor;
  final String foodPairing;
  final int budgetIndex;
  final bool prefDry;

  const PalateSnapshot({
    required this.crispness,
    required this.weight,
    required this.texture,
    required this.flavor,
    required this.foodPairing,
    required this.budgetIndex,
    required this.prefDry,
  });
}

class PalateProfile {
  final String id;
  final String name;
  final int crispness;
  final int weight;
  final int texture;
  final int flavor;
  final String foodPairing;
  final int budgetIndex;
  final bool prefDry;

  const PalateProfile({
    required this.id,
    required this.name,
    required this.crispness,
    required this.weight,
    required this.texture,
    required this.flavor,
    required this.foodPairing,
    required this.budgetIndex,
    required this.prefDry,
  });

  factory PalateProfile.fromJson(Map<String, dynamic> json) => PalateProfile(
        id:          json['id']           as String,
        name:        json['name']         as String,
        crispness:   json['crispness']    as int,
        weight:      json['weight']       as int,
        texture:     json['texture']      as int,
        flavor:      json['flavor']       as int,
        foodPairing: json['food_pairing'] as String,
        budgetIndex: json['budget_index'] as int,
        prefDry:     json['pref_dry']     as bool,
      );

  Map<String, dynamic> toJson() => {
        'id':           id,
        'name':         name,
        'crispness':    crispness,
        'weight':       weight,
        'texture':      texture,
        'flavor':       flavor,
        'food_pairing': foodPairing,
        'budget_index': budgetIndex,
        'pref_dry':     prefDry,
      };

  PalateSnapshot toSnapshot() => PalateSnapshot(
        crispness:   crispness,
        weight:      weight,
        texture:     texture,
        flavor:      flavor,
        foodPairing: foodPairing,
        budgetIndex: budgetIndex,
        prefDry:     prefDry,
      );
}
