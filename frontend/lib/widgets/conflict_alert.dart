import 'package:flutter/material.dart';

Future<void> showConflictAlert(
  BuildContext context, {
  required VoidCallback onIncreaseWeight,
  required VoidCallback onReduceTexture,
}) {
  return showDialog(
    context: context,
    barrierDismissible: false,
    builder: (_) => _ConflictAlertDialog(
      onIncreaseWeight: onIncreaseWeight,
      onReduceTexture: onReduceTexture,
    ),
  );
}

class _ConflictAlertDialog extends StatelessWidget {
  final VoidCallback onIncreaseWeight;
  final VoidCallback onReduceTexture;

  const _ConflictAlertDialog({
    required this.onIncreaseWeight,
    required this.onReduceTexture,
  });

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Row(
        children: [
          Text('🧙‍♂️', style: TextStyle(fontSize: 24)),
          SizedBox(width: 8),
          Flexible(child: Text('Your Wizard Senses a Disturbance')),
        ],
      ),
      content: const Text(
        'Ah — a Light Weight (Body) with High Texture (Tannin). Bold choice. '
        'Genuinely rare in the wild, like a featherweight boxer with an iron grip.\n\n'
        'Most light-bodied wines keep their tannins low and their manners impeccable. '
        'Your palate is... unconventional. I respect it.\n\n'
        'That said, if you\'d like the cellar to have more options for you, '
        'I can tweak one of these:',
      ),
      actions: [
        TextButton(
          onPressed: () {
            Navigator.of(context).pop();
            onIncreaseWeight();
          },
          child: const Text('Bulk up the Weight (Body)'),
        ),
        TextButton(
          onPressed: () {
            Navigator.of(context).pop();
            onReduceTexture();
          },
          child: const Text('Soften the Texture (Tannin)'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text("I know what I like, Wizard"),
        ),
      ],
    );
  }
}
