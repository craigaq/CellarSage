import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

class PalateDial extends StatelessWidget {
  final int crispness;
  final int weight;
  final int flavorIntensity;
  final int texture;

  final bool compact;

  const PalateDial({
    super.key,
    required this.crispness,
    required this.weight,
    required this.flavorIntensity,
    required this.texture,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return AspectRatio(
      aspectRatio: 1,
      child: RadarChart(
        RadarChartData(
          dataSets: [
            // Invisible anchor — forces the radar scale to always top out at 5,
            // matching the quiz slider range regardless of actual user values.
            RadarDataSet(
              dataEntries: const [
                RadarEntry(value: 5),
                RadarEntry(value: 5),
                RadarEntry(value: 5),
                RadarEntry(value: 5),
              ],
              fillColor: Colors.transparent,
              borderColor: Colors.transparent,
              borderWidth: 0,
              entryRadius: 0,
            ),
            RadarDataSet(
              dataEntries: [
                RadarEntry(value: crispness.toDouble()),
                RadarEntry(value: weight.toDouble()),
                RadarEntry(value: flavorIntensity.toDouble()),
                RadarEntry(value: texture.toDouble()),
              ],
              fillColor: color.withValues(alpha: 0.25),
              borderColor: color,
              borderWidth: 2.5,
              entryRadius: 5,
            ),
          ],
          radarBackgroundColor: Colors.transparent,
          borderData: FlBorderData(show: false),
          radarBorderData: const BorderSide(color: Colors.transparent),
          tickCount: 5,
          ticksTextStyle: TextStyle(fontSize: 9, color: Colors.grey.shade500),
          tickBorderData: BorderSide(color: Colors.grey.shade300, width: 0.8),
          gridBorderData: BorderSide(color: Colors.grey.shade300, width: 0.8),
          titleTextStyle: TextStyle(
            fontSize: compact ? 9 : 11,
            fontWeight: FontWeight.w600,
          ),
          getTitle: (index, angle) {
            final titles = compact
                ? const ['A', 'B', 'F', 'T']
                : const [
                    'Crispness\n(Acidity)',
                    'Weight\n(Body)',
                    'Flavor Intensity\n(Aromatics)',
                    'Texture\n(Tannin)',
                  ];
            return RadarChartTitle(text: titles[index], angle: 0);
          },
        ),
      ),
    );
  }
}
