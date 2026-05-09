import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class AgeGateScreen extends StatelessWidget {
  final VoidCallback onConfirmed;
  const AgeGateScreen({super.key, required this.onConfirmed});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: WwColors.bgDeep,
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [WwColors.bgDeep, WwColors.bgSurface],
          ),
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              children: [
                const Spacer(flex: 2),

                // Crest — gold ring with wine glass
                Container(
                  width: 104,
                  height: 104,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: WwColors.violet, width: 2),
                    boxShadow: WwDecorations.violetGlow(),
                  ),
                  child: const Center(
                    child: Text('🍷', style: TextStyle(fontSize: 50)),
                  ),
                ),

                const SizedBox(height: 36),

                Text(
                  'Welcome to\nCellar Sage',
                  textAlign: TextAlign.center,
                  style: WwText.displayLarge(),
                ),

                const SizedBox(height: 20),

                Text(
                  'This service is reserved for adults.\nPlease confirm your age before entering.',
                  textAlign: TextAlign.center,
                  style: WwText.bodyLarge(color: WwColors.textSecondary),
                ),

                const Spacer(flex: 2),

                // Confirm CTA
                Container(
                  width: double.infinity,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: WwDecorations.violetGlow(),
                  ),
                  child: FilledButton(
                    onPressed: onConfirmed,
                    child: Text(
                      "Yes, I'm of Legal Drinking Age",
                      style: WwText.labelLarge(color: Colors.black),
                    ),
                  ),
                ),

                const SizedBox(height: 14),

                // Decline
                SizedBox(
                  width: double.infinity,
                  child: TextButton(
                    style: TextButton.styleFrom(
                      foregroundColor: WwColors.textDisabled,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                    onPressed: () => _showUnderageDialog(context),
                    child: const Text("No, I'm Under Age"),
                  ),
                ),

                const SizedBox(height: 24),

                Text(
                  'Legal drinking age varies by country.\nDrink responsibly.',
                  textAlign: TextAlign.center,
                  style: WwText.bodySmall(color: WwColors.textDisabled),
                ),

                const SizedBox(height: 16),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _showUnderageDialog(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: WwColors.bgElevated,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: WwColors.borderSubtle),
        ),
        title: Text('Come Back Later', style: WwText.titleMedium()),
        content: Text(
          "The Cellar Sage will be here when you're ready. "
          "Until then, stay curious! 🦊",
          style: WwText.bodyMedium(),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text('OK', style: WwText.labelLarge(color: WwColors.violet)),
          ),
        ],
      ),
    );
  }
}
