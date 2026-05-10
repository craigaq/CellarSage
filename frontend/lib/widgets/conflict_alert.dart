import 'package:flutter/material.dart';
import '../models/wine_recommendation.dart';
import '../theme/app_theme.dart';

// ---------------------------------------------------------------------------
// Palate Paradox alert (dry preference vs sweet-pairing food) — bottom sheet
// ---------------------------------------------------------------------------

Future<void> showPalateParadoxSheet(
  BuildContext context,
  PalateParadox paradox,
  void Function(String action) onResolved,
) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: Colors.transparent,
    isDismissible: false,
    enableDrag: false,
    isScrollControlled: true,
    builder: (context) {
      return Container(
        decoration: const BoxDecoration(
          color: WwColors.bgElevated,
          borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
          border: Border(
            top: BorderSide(color: WwColors.borderMedium, width: 1),
          ),
        ),
        padding: const EdgeInsets.fromLTRB(24, 24, 24, 36),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Drag handle
            Container(
              width: 40,
              height: 4,
              margin: const EdgeInsets.only(bottom: 20),
              decoration: BoxDecoration(
                color: WwColors.borderMedium,
                borderRadius: BorderRadius.circular(2),
              ),
            ),

            const Text('🦊', style: TextStyle(fontSize: 40)),
            const SizedBox(height: 10),

            Text(
              'Palate Paradox',
              style: WwText.headlineMedium(color: WwColors.violet),
            ),
            const SizedBox(height: 12),

            Text(
              paradox.message,
              textAlign: TextAlign.center,
              style: WwText.bodyMedium(),
            ),
            const SizedBox(height: 24),

            ...paradox.options.map((opt) {
              final action = opt['action']!;
              final label  = opt['label']!;
              final isRecommended = action == 'use_pairing_logic';
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: SizedBox(
                  width: double.infinity,
                  child: isRecommended
                      ? Container(
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(12),
                            boxShadow: WwDecorations.violetGlow(),
                          ),
                          child: FilledButton(
                            onPressed: () {
                              Navigator.of(context).pop();
                              onResolved(action);
                            },
                            child: Text(label,
                                style: WwText.labelLarge(color: Colors.black)),
                          ),
                        )
                      : OutlinedButton(
                          onPressed: () {
                            Navigator.of(context).pop();
                            onResolved(action);
                          },
                          child: Text(label),
                        ),
                ),
              );
            }),
          ],
        ),
      );
    },
  );
}

// ---------------------------------------------------------------------------
// Palate conflict alert (attribute-level mismatch) — dialog
// ---------------------------------------------------------------------------

Future<void> showConflictAlert(
  BuildContext context,
  ConflictAlert alert,
  void Function(int) onAdjust,
) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (context) {
      return AlertDialog(
        backgroundColor: WwColors.bgElevated,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: const BorderSide(color: WwColors.borderMedium),
        ),
        title: Text(alert.title, style: WwText.titleLarge()),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('🦊', style: TextStyle(fontSize: 56)),
            const SizedBox(height: 15),
            Text(
              alert.message,
              textAlign: TextAlign.center,
              style: WwText.bodyMedium(),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(
              "No, I'm Stubborn",
              style: WwText.bodyMedium(color: WwColors.textSecondary),
            ),
          ),
          FilledButton(
            onPressed: () {
              onAdjust(alert.suggestedValue);
              Navigator.of(context).pop();
            },
            child: Text(
              'Trust the Cellar Fox',
              style: WwText.labelLarge(color: Colors.black),
            ),
          ),
        ],
      );
    },
  );
}

// ---------------------------------------------------------------------------
// Gastro-clash alert (food + palate mismatch) — bottom sheet
// ---------------------------------------------------------------------------

Future<void> showGastroClashAlert(
  BuildContext context,
  GastroClash clash,
  void Function(Map<String, int>) onApply,
) {
  return showModalBottomSheet<void>(
    context: context,
    backgroundColor: Colors.transparent,
    isDismissible: false,
    enableDrag: false,
    isScrollControlled: true,
    builder: (context) {
      final bottomPad = MediaQuery.of(context).padding.bottom;
      return ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.85,
        ),
        child: Container(
          decoration: const BoxDecoration(
            color: WwColors.bgElevated,
            borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
            border: Border(
              top: BorderSide(color: WwColors.borderMedium, width: 1),
            ),
          ),
          padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + bottomPad),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Drag handle
                Container(
                  width: 40,
                  height: 4,
                  margin: const EdgeInsets.only(bottom: 20),
                  decoration: BoxDecoration(
                    color: WwColors.borderMedium,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),

                Text(
                  clash.title,
                  textAlign: TextAlign.center,
                  style: WwText.headlineMedium(color: WwColors.violet),
                ),
                const SizedBox(height: 12),

                Text(
                  clash.message,
                  textAlign: TextAlign.center,
                  style: WwText.bodyMedium(),
                ),
                const SizedBox(height: 24),

                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Text("I'll risk it!"),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Container(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(12),
                          boxShadow: WwDecorations.violetGlow(),
                        ),
                        child: FilledButton(
                          onPressed: () {
                            onApply(clash.newValues);
                            Navigator.of(context).pop();
                          },
                          child: Text(
                            'Trust the Cellar Fox',
                            style: WwText.labelLarge(color: Colors.black),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
      );
    },
  );
}
