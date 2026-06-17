import 'package:shared_preferences/shared_preferences.dart';

/// Persists the user's Australian state for "Local Hero" geo-personalisation,
/// so the tier still works when GPS is off/denied. Set from the last successful
/// GPS detection, or manually by the user.
class StatePrefs {
  static const _kUserState = 'user_state';

  /// AU states/territories offered in the manual picker.
  static const auStates = <String>['SA', 'VIC', 'NSW', 'QLD', 'WA', 'TAS', 'ACT', 'NT'];

  static Future<String?> load() async {
    final prefs = await SharedPreferences.getInstance();
    final v = prefs.getString(_kUserState);
    return (v != null && v.isNotEmpty) ? v : null;
  }

  static Future<void> save(String state) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUserState, state);
  }
}
