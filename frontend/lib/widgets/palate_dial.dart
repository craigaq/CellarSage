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
            // Zero anchor — forces the chart minimum to 0 so the scale is always 0–5.
            // Without this, fl_chart sets the minimum from the lowest data value,
            // causing the rings to show e.g. 2.0–4.4 instead of 1–5.
            RadarDataSet(
              dataEntries: const [
                RadarEntry(value: 0),
                RadarEntry(value: 0),
                RadarEntry(value: 0),
                RadarEntry(value: 0),
              ],
              fillColor: Colors.transparent,
              borderColor: Colors.transparent,
              borderWidth: 0,
              entryRadius: 0,
            ),
            // Five anchor — forces the chart maximum to 5.
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
          // Make the outer boundary ring visible — it sits at max value (5),
          // so a score of 5 lands exactly on this ring instead of outside it.
          radarBorderData: BorderSide(color: Colors.grey.shade300, width: 0.8),
          tickCount: 5,
          // Hide tick number labels — they show 0–4 (not 1–5) and mislead.
          ticksTextStyle: const TextStyle(fontSize: 0, color: Colors.transparent),
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
            return RadarChartTitle(
              text: titles[index],
              angle: 0,
              positionPercentageOffset: compact ? 0.08 : 0.2,
            );
          },
        ),
      ),
    );
  }
}
