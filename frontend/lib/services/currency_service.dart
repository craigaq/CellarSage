import 'dart:io' show Platform;
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:geolocator/geolocator.dart';

class CurrencyInfo {
  final String code;
  final String symbol;
  final String name;

  const CurrencyInfo(this.code, this.symbol, this.name);
}

class BudgetBracket {
  final String label;
  final double min;
  final double max;

  const BudgetBracket(this.label, this.min, this.max);
}

class CurrencyService {
  // Locale country code → ISO 4217 currency code
  static const _localeToCode = {
    'AU': 'AUD',  'NZ': 'NZD',
    'US': 'USD',
    'CA': 'CAD',
    'GB': 'GBP',
    'IE': 'EUR',  'FR': 'EUR',  'DE': 'EUR',  'IT': 'EUR',
    'ES': 'EUR',  'PT': 'EUR',  'NL': 'EUR',  'BE': 'EUR',  'AT': 'EUR',
    'CH': 'CHF',
    'JP': 'JPY',
    'SG': 'SGD',
    'HK': 'HKD',
    'CN': 'CNY',
    'ZA': 'ZAR',
  };

  static const _meta = {
    'AUD': CurrencyInfo('AUD', 'A\$',  'Australian Dollar'),
    'USD': CurrencyInfo('USD', '\$',   'US Dollar'),
    'EUR': CurrencyInfo('EUR', '€',    'Euro'),
    'GBP': CurrencyInfo('GBP', '£',    'British Pound'),
    'NZD': CurrencyInfo('NZD', 'NZ\$', 'New Zealand Dollar'),
    'CAD': CurrencyInfo('CAD', 'CA\$', 'Canadian Dollar'),
    'JPY': CurrencyInfo('JPY', '¥',    'Japanese Yen'),
    'SGD': CurrencyInfo('SGD', 'S\$',  'Singapore Dollar'),
    'ZAR': CurrencyInfo('ZAR', 'R',    'South African Rand'),
    'HKD': CurrencyInfo('HKD', 'HK\$', 'Hong Kong Dollar'),
    'CNY': CurrencyInfo('CNY', '¥',    'Chinese Yuan'),
    'CHF': CurrencyInfo('CHF', 'Fr',   'Swiss Franc'),
  };

  // Budget brackets per currency, derived from AUD base ranges:
  //   Under 20 / 20–35 / 36–60 / 61–100 / 101+
  static const _brackets = {
    'AUD': [
      BudgetBracket('Under A\$20',       0,    20),
      BudgetBracket('A\$20 – A\$35',    20,    35),
      BudgetBracket('A\$36 – A\$60',    36,    60),
      BudgetBracket('A\$61 – A\$100',   61,   100),
      BudgetBracket('Over A\$100',      101,  9999),
    ],
    'USD': [
      BudgetBracket('Under \$13',        0,    13),
      BudgetBracket('\$13 – \$22',      13,    22),
      BudgetBracket('\$23 – \$38',      23,    38),
      BudgetBracket('\$39 – \$63',      39,    63),
      BudgetBracket('Over \$63',        64,  9999),
    ],
    'EUR': [
      BudgetBracket('Under €12',         0,    12),
      BudgetBracket('€12 – €20',        12,    20),
      BudgetBracket('€21 – €35',        21,    35),
      BudgetBracket('€36 – €58',        36,    58),
      BudgetBracket('Over €58',         59,  9999),
    ],
    'GBP': [
      BudgetBracket('Under £10',         0,    10),
      BudgetBracket('£10 – £17',        10,    17),
      BudgetBracket('£18 – £30',        18,    30),
      BudgetBracket('£31 – £50',        31,    50),
      BudgetBracket('Over £50',         51,  9999),
    ],
    'NZD': [
      BudgetBracket('Under NZ\$22',      0,    22),
      BudgetBracket('NZ\$22 – NZ\$38',  22,    38),
      BudgetBracket('NZ\$39 – NZ\$65',  39,    65),
      BudgetBracket('NZ\$66 – NZ\$108', 66,   108),
      BudgetBracket('Over NZ\$108',    109,  9999),
    ],
    'CAD': [
      BudgetBracket('Under CA\$17',      0,    17),
      BudgetBracket('CA\$17 – CA\$30',  17,    30),
      BudgetBracket('CA\$31 – CA\$52',  31,    52),
      BudgetBracket('CA\$53 – CA\$87',  53,    87),
      BudgetBracket('Over CA\$87',      88,  9999),
    ],
    'JPY': [
      BudgetBracket('Under ¥1,940',       0,  1940),
      BudgetBracket('¥1,940 – ¥3,395', 1940,  3395),
      BudgetBracket('¥3,492 – ¥5,820', 3492,  5820),
      BudgetBracket('¥5,917 – ¥9,700', 5917,  9700),
      BudgetBracket('Over ¥9,700',     9701, 999999),
    ],
    'SGD': [
      BudgetBracket('Under S\$17',       0,    17),
      BudgetBracket('S\$17 – S\$30',    17,    30),
      BudgetBracket('S\$31 – S\$51',    31,    51),
      BudgetBracket('S\$52 – S\$85',    52,    85),
      BudgetBracket('Over S\$85',       86,  9999),
    ],
  };

  // Australian state bounding boxes — checked top-to-bottom; first match wins.
  // Smaller/more specific regions (TAS, ACT) are listed before larger ones
  // that overlap them (NSW, VIC) to ensure correct assignment.
  static const _auStateBoxes = <(double, double, double, double, String)>[
    (-43.7, -39.5, 143.8, 148.5, 'TAS'),
    (-35.9, -35.1, 148.8, 149.4, 'ACT'),
    (-39.2, -34.0, 140.9, 150.0, 'VIC'),
    (-37.5, -28.1, 140.9, 153.7, 'NSW'),
    (-38.2, -25.9, 129.0, 141.1, 'SA'),
    (-35.2, -13.7, 112.9, 129.1, 'WA'),
    (-29.2, -10.4, 138.0, 153.7, 'QLD'),
    (-26.1, -10.4, 129.0, 138.1, 'NT'),
  ];

  /// Return the two-letter Australian state code for a given position,
  /// or null when outside Australia.
  static String? detectAustralianState(double lat, double lng) {
    for (final box in _auStateBoxes) {
      if (lat >= box.$1 && lat <= box.$2 && lng >= box.$3 && lng <= box.$4) {
        return box.$5;
      }
    }
    return null;
  }

  /// Detect the user's Australian state from GPS.
  /// Returns null if outside Australia or location is unavailable.
  static Future<String?> detectAustralianStateFromGps() async {
    try {
      bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) { return null; }
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) { return null; }
      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.low),
      );
      return detectAustralianState(pos.latitude, pos.longitude);
    } catch (_) {
      return null;
    }
  }

  // Bounding boxes: (latMin, latMax, lngMin, lngMax, countryCode)
  static const _boxes = [
    (-44.0, -10.0,  113.0,  154.0, 'AU'),
    (-47.0, -34.0,  166.0,  178.0, 'NZ'),
    ( 24.0,  49.0, -125.0,  -66.0, 'US'),
    ( 42.0,  83.0, -141.0,  -52.0, 'CA'),
    ( 49.0,  61.0,   -8.0,    2.0, 'GB'),
    ( 51.0,  56.0,  -10.0,   -5.0, 'IE'),
    ( 41.0,  51.0,   -5.0,   10.0, 'FR'),
    ( 47.0,  55.0,    6.0,   15.0, 'DE'),
    ( 36.0,  47.0,    6.0,   19.0, 'IT'),
    ( 36.0,  44.0,   -9.0,    4.0, 'ES'),
    ( 36.0,  42.0,   -9.0,   -6.0, 'PT'),
    ( 46.0,  48.0,    6.0,   11.0, 'CH'),
    ( 24.0,  46.0,  122.0,  146.0, 'JP'),
    (  1.1,   1.5,  103.6,  104.0, 'SG'),
    ( 22.0,  24.0,  113.8,  114.5, 'HK'),
    ( 18.0,  53.5,   73.0,  135.0, 'CN'),
    (-35.0, -22.0,   16.0,   33.0, 'ZA'),
  ];

  /// Detect currency from GPS coordinates using bounding-box lookup.
  /// Falls back to "AUD" when no region matches.
  static String detectCodeFromLatLng(double lat, double lng) {
    for (final box in _boxes) {
      if (lat >= box.$1 && lat <= box.$2 && lng >= box.$3 && lng <= box.$4) {
        return _localeToCode[box.$5] ?? 'AUD';
      }
    }
    return 'AUD';
  }

  /// Detect currency from the device's GPS location.
  /// Falls back to locale-based detection if location is unavailable.
  static Future<String> detectCodeFromGps() async {
    try {
      bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
      if (!serviceEnabled) return detectCodeFromLocale();

      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return detectCodeFromLocale();
      }

      final pos = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.low),
      );
      return detectCodeFromLatLng(pos.latitude, pos.longitude);
    } catch (_) {
      return detectCodeFromLocale();
    }
  }

  /// Detect currency code from the device locale (e.g. "en_AU" → "AUD").
  /// Falls back to "AUD" if the locale is unavailable or unrecognised.
  static String detectCodeFromLocale() {
    try {
      if (!kIsWeb) {
        final locale = Platform.localeName; // e.g. "en_AU" or "en_AU.UTF-8"
        final parts = locale.split(RegExp(r'[_\-\.]'));
        if (parts.length >= 2) {
          final country = parts[1].toUpperCase();
          return _localeToCode[country] ?? 'AUD';
        }
      }
    } catch (_) {}
    return 'AUD';
  }

  /// Kept for backwards compatibility — now delegates to [detectCodeFromLocale].
  static String detectCode() => detectCodeFromLocale();

  static CurrencyInfo getInfo(String code) =>
      _meta[code] ?? const CurrencyInfo('AUD', 'A\$', 'Australian Dollar');

  static List<BudgetBracket> getBrackets(String code) =>
      _brackets[code] ?? _brackets['AUD']!;
}
