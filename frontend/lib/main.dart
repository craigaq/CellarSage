import 'package:flutter/material.dart';
import 'screens/quiz_screen.dart';

void main() => runApp(const WineWizardApp());

class WineWizardApp extends StatelessWidget {
  const WineWizardApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Wine Wizard',
      theme: ThemeData(colorSchemeSeed: Colors.deepPurple, useMaterial3: true),
      home: const QuizScreen(),
    );
  }
}
