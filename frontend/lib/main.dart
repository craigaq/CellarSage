import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'screens/age_gate_screen.dart';
import 'screens/onboarding_screen.dart';
import 'screens/quiz_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  runApp(const WineWizardApp());
}

enum _AppStage { ageGate, onboarding, quiz }

class WineWizardApp extends StatefulWidget {
  const WineWizardApp({super.key});

  @override
  State<WineWizardApp> createState() => _WineWizardAppState();
}

class _WineWizardAppState extends State<WineWizardApp> {
  ThemeMode _themeMode = ThemeMode.system;
  _AppStage _stage = _AppStage.ageGate;

  void _toggleTheme() {
    setState(() {
      _themeMode =
          _themeMode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
    });
  }

  void _advance() {
    setState(() {
      _stage = _AppStage.values[_stage.index + 1];
    });
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wine Wizard',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: Colors.deepPurple,
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorSchemeSeed: Colors.deepPurple,
        brightness: Brightness.dark,
        useMaterial3: true,
      ),
      themeMode: _themeMode,
      home: switch (_stage) {
        _AppStage.ageGate => AgeGateScreen(onConfirmed: _advance),
        _AppStage.onboarding => OnboardingScreen(onComplete: _advance),
        _AppStage.quiz => QuizScreen(
            themeMode: _themeMode,
            onToggleTheme: _toggleTheme,
          ),
      },
    );
  }
}
