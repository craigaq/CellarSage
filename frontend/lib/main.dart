import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'screens/age_gate_screen.dart';
import 'screens/onboarding_screen.dart';
import 'screens/quiz_screen.dart';
import 'theme/app_theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  runApp(const CellarSageApp());
}

enum _AppStage { ageGate, onboarding, quiz }

class CellarSageApp extends StatefulWidget {
  const CellarSageApp({super.key});

  @override
  State<CellarSageApp> createState() => _CellarSageAppState();
}

class _CellarSageAppState extends State<CellarSageApp> {
  _AppStage _stage = _AppStage.ageGate;

  // Onboarding (the 3 Sage Fox intro cards) runs only on first launch and
  // again after an app version change. We persist the version that last saw
  // onboarding; if it matches the running version, onboarding is skipped.
  static const _kOnboardingVersionKey = 'onboarding_seen_version';
  bool _needsOnboarding = true; // assume yes until the check completes
  String _currentVersion = '';

  @override
  void initState() {
    super.initState();
    _checkOnboardingSeen();
  }

  Future<void> _checkOnboardingSeen() async {
    try {
      final info = await PackageInfo.fromPlatform();
      final prefs = await SharedPreferences.getInstance();
      _currentVersion = info.version; // versionName, e.g. "1.0.0"
      final seen = prefs.getString(_kOnboardingVersionKey);
      if (mounted) setState(() => _needsOnboarding = seen != _currentVersion);
    } catch (_) {
      // If the check fails, default to showing onboarding (safe fallback).
      if (mounted) setState(() => _needsOnboarding = true);
    }
  }

  Future<void> _markOnboardingSeen() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final version = _currentVersion.isNotEmpty
          ? _currentVersion
          : (await PackageInfo.fromPlatform()).version;
      await prefs.setString(_kOnboardingVersionKey, version);
    } catch (_) {
      // Non-fatal — onboarding will simply show again next launch.
    }
  }

  // Age gate → onboarding (first run / after update) or straight to the quiz.
  void _advanceFromAgeGate() {
    setState(() =>
        _stage = _needsOnboarding ? _AppStage.onboarding : _AppStage.quiz);
  }

  // Onboarding finished → remember this version so it won't show again.
  void _completeOnboarding() {
    _markOnboardingSeen();
    setState(() => _stage = _AppStage.quiz);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Cellar Sage',
      debugShowCheckedModeBanner: false,
      theme: WwTheme.dark(),
      darkTheme: WwTheme.dark(),
      themeMode: ThemeMode.dark,
      home: switch (_stage) {
        _AppStage.ageGate => AgeGateScreen(onConfirmed: _advanceFromAgeGate),
        _AppStage.onboarding => OnboardingScreen(onComplete: _completeOnboarding),
        _AppStage.quiz => const QuizScreen(),
      },
    );
  }
}
