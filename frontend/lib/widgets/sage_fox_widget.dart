import 'dart:math';
import 'package:flutter/material.dart';

/// Geometric origami Sage Fox — the Cellar Sage mascot.
///
/// Sitting upright, rendered entirely in Electric Violet (#C3A5FF) line art
/// on the Charcoal-Grape background. Personality: calm, intelligent, observant.
///
/// Idle animation: gentle float + ambient sparkle pulse.
class SageFoxWidget extends StatefulWidget {
  final Duration delay;
  const SageFoxWidget({super.key, this.delay = Duration.zero});

  @override
  State<SageFoxWidget> createState() => _SageFoxWidgetState();
}

class _SageFoxWidgetState extends State<SageFoxWidget>
    with SingleTickerProviderStateMixin {
  late final AnimationController _idle;

  @override
  void initState() {
    super.initState();
    _idle = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 3200),
    );
    Future.delayed(widget.delay, () {
      if (mounted) _idle.repeat();
    });
  }

  @override
  void dispose() {
    _idle.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _idle,
      builder: (_, _) {
        final t = _idle.value;
        return SizedBox(
          width: 200,
          height: 220,
          child: CustomPaint(
            size: const Size(200, 220),
            painter: _FoxPainter(
              floatDy:   sin(t * 2 * pi) * 5.0,
              glowPhase: t,
            ),
          ),
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------
// Painter
// ---------------------------------------------------------------------------

class _FoxPainter extends CustomPainter {
  final double floatDy;
  final double glowPhase;

  _FoxPainter({required this.floatDy, required this.glowPhase});

  static const _violet = Color(0xFFC3A5FF);

  Paint _stroke(double w, {double a = 1.0}) => Paint()
    ..color = _violet.withValues(alpha: a)
    ..strokeWidth = w
    ..style = PaintingStyle.stroke
    ..strokeCap = StrokeCap.round
    ..strokeJoin = StrokeJoin.round;

  Paint _fill(double a) => Paint()
    ..color = _violet.withValues(alpha: a)
    ..style = PaintingStyle.fill;

  @override
  void paint(Canvas canvas, Size size) {
    final d = floatDy;
    _drawTail(canvas, d);
    _drawBody(canvas, d);
    _drawPaws(canvas, d);
    _drawHead(canvas, d);
    _drawEars(canvas, d);
    _drawFace(canvas, d);
    _drawSparkles(canvas, d);
  }

  // ── Head ──────────────────────────────────────────────────────────────────

  void _drawHead(Canvas canvas, double d) {
    final path = Path()
      ..moveTo(100, 40 + d)   // top of skull
      ..lineTo(124, 52 + d)   // right temple
      ..lineTo(128, 72 + d)   // right cheek
      ..lineTo(114, 86 + d)   // right jaw
      ..lineTo(100, 90 + d)   // chin
      ..lineTo(86,  86 + d)   // left jaw
      ..lineTo(72,  72 + d)   // left cheek
      ..lineTo(76,  52 + d)   // left temple
      ..close();
    canvas.drawPath(path, _fill(0.07));
    canvas.drawPath(path, _stroke(1.8));

    // Geometric forehead facet lines — suggests flat origami skull planes
    canvas.drawLine(Offset(76,  52 + d), Offset(100, 44 + d), _stroke(1.1, a: 0.28));
    canvas.drawLine(Offset(100, 44 + d), Offset(124, 52 + d), _stroke(1.1, a: 0.28));
  }

  // ── Ears ──────────────────────────────────────────────────────────────────

  void _drawEars(Canvas canvas, double d) {
    // Left outer ear
    final le = Path()
      ..moveTo(76, 52 + d)
      ..lineTo(90, 44 + d)
      ..lineTo(60, 15 + d)
      ..close();
    canvas.drawPath(le, _fill(0.07));
    canvas.drawPath(le, _stroke(1.8));

    // Left inner ear — brighter fill for warmth
    final lei = Path()
      ..moveTo(78, 49 + d)
      ..lineTo(87, 44 + d)
      ..lineTo(63, 20 + d)
      ..close();
    canvas.drawPath(lei, _fill(0.28));
    canvas.drawPath(lei, _stroke(1.1, a: 0.50));

    // Right outer ear
    final re = Path()
      ..moveTo(110, 44 + d)
      ..lineTo(124, 52 + d)
      ..lineTo(140, 15 + d)
      ..close();
    canvas.drawPath(re, _fill(0.07));
    canvas.drawPath(re, _stroke(1.8));

    // Right inner ear
    final rei = Path()
      ..moveTo(113, 44 + d)
      ..lineTo(122, 49 + d)
      ..lineTo(137, 20 + d)
      ..close();
    canvas.drawPath(rei, _fill(0.28));
    canvas.drawPath(rei, _stroke(1.1, a: 0.50));
  }

  // ── Face ──────────────────────────────────────────────────────────────────

  void _drawFace(Canvas canvas, double d) {
    // Eyebrows — angled inward-upward = attentive / intelligent
    canvas.drawLine(Offset(80, 55 + d), Offset(94, 51 + d), _stroke(1.5));
    canvas.drawLine(Offset(106, 51 + d), Offset(120, 55 + d), _stroke(1.5));

    // Left eye — geometric almond, inner corner lifted = observant expression
    final le = Path()
      ..moveTo(80, 64 + d)   // outer corner
      ..lineTo(87, 58 + d)   // top apex
      ..lineTo(94, 61 + d)   // inner corner (raised for knowing look)
      ..lineTo(87, 68 + d)   // bottom apex
      ..close();
    canvas.drawPath(le, _fill(0.88));
    canvas.drawPath(le, _stroke(1.6));
    canvas.drawCircle(Offset(87, 63 + d), 2.5,
        Paint()..color = const Color(0xFF0F0F14)..style = PaintingStyle.fill);
    canvas.drawCircle(Offset(88.5, 61 + d), 0.9,
        Paint()..color = Colors.white.withValues(alpha: 0.85)..style = PaintingStyle.fill);

    // Right eye — mirror
    final re = Path()
      ..moveTo(106, 61 + d)   // inner corner (raised)
      ..lineTo(113, 58 + d)   // top apex
      ..lineTo(120, 64 + d)   // outer corner
      ..lineTo(113, 68 + d)   // bottom apex
      ..close();
    canvas.drawPath(re, _fill(0.88));
    canvas.drawPath(re, _stroke(1.6));
    canvas.drawCircle(Offset(113, 63 + d), 2.5,
        Paint()..color = const Color(0xFF0F0F14)..style = PaintingStyle.fill);
    canvas.drawCircle(Offset(114.5, 61 + d), 0.9,
        Paint()..color = Colors.white.withValues(alpha: 0.85)..style = PaintingStyle.fill);

    // Muzzle — subtle geometric hexagonal snout
    final muzzle = Path()
      ..moveTo(88, 70 + d)
      ..lineTo(100, 67 + d)
      ..lineTo(112, 70 + d)
      ..lineTo(112, 81 + d)
      ..lineTo(100, 85 + d)
      ..lineTo(88,  81 + d)
      ..close();
    canvas.drawPath(muzzle, _fill(0.06));
    canvas.drawPath(muzzle, _stroke(1.0, a: 0.22));

    // Nose — small filled inverted triangle
    final nose = Path()
      ..moveTo(97, 74 + d)
      ..lineTo(103, 74 + d)
      ..lineTo(100, 78 + d)
      ..close();
    canvas.drawPath(nose, _fill(1.0));

    // Smile — five-point angular upturn, clearly readable
    final smile = Path()
      ..moveTo(91, 80 + d)
      ..lineTo(96, 83 + d)
      ..lineTo(100, 82 + d)
      ..lineTo(104, 83 + d)
      ..lineTo(109, 80 + d);
    canvas.drawPath(smile, _stroke(1.6));
  }

  // ── Body ──────────────────────────────────────────────────────────────────

  void _drawBody(Canvas canvas, double d) {
    // Upper chest trapezoid
    final chest = Path()
      ..moveTo(82,  92 + d)
      ..lineTo(118, 92 + d)
      ..lineTo(128, 118 + d)
      ..lineTo(72,  118 + d)
      ..close();
    canvas.drawPath(chest, _fill(0.08));
    canvas.drawPath(chest, _stroke(1.8));

    // Lower body — wider base for seated stability
    final lower = Path()
      ..moveTo(72,  118 + d)
      ..lineTo(128, 118 + d)
      ..lineTo(134, 162 + d)
      ..lineTo(66,  162 + d)
      ..close();
    canvas.drawPath(lower, _fill(0.05));
    canvas.drawPath(lower, _stroke(1.8));
  }

  // ── Tail ──────────────────────────────────────────────────────────────────

  void _drawTail(Canvas canvas, double d) {
    // Geometric tail curling up the right side of the body
    final tail = Path()
      ..moveTo(128, 150 + d)   // base at right hip
      ..lineTo(150, 134 + d)   // outer arc
      ..lineTo(158, 108 + d)   // outer peak
      ..lineTo(146, 90 + d)    // upper outer
      ..lineTo(136, 88 + d)    // tip outer
      ..lineTo(134, 93 + d)    // tip inner
      ..lineTo(144, 96 + d)    // upper inner
      ..lineTo(152, 112 + d)   // inner midpoint
      ..lineTo(144, 132 + d)   // inner arc
      ..lineTo(128, 146 + d)   // base inner
      ..close();
    canvas.drawPath(tail, _fill(0.08));
    canvas.drawPath(tail, _stroke(1.8));

    // Tail geometric facet divider — origami fold line
    canvas.drawLine(
      Offset(140, 96 + d), Offset(150, 124 + d), _stroke(1.1, a: 0.32));
  }

  // ── Paws ──────────────────────────────────────────────────────────────────

  void _drawPaws(Canvas canvas, double d) {
    // Left paw
    final lPaw = Path()
      ..moveTo(68, 162 + d)
      ..lineTo(68, 180 + d)
      ..lineTo(88, 180 + d)
      ..lineTo(88, 162 + d)
      ..close();
    canvas.drawPath(lPaw, _fill(0.07));
    canvas.drawPath(lPaw, _stroke(1.8));
    for (final x in [74.0, 79.0, 84.0]) {
      canvas.drawLine(
          Offset(x, 165 + d), Offset(x, 178 + d), _stroke(1.0, a: 0.40));
    }

    // Right paw
    final rPaw = Path()
      ..moveTo(112, 162 + d)
      ..lineTo(112, 180 + d)
      ..lineTo(132, 180 + d)
      ..lineTo(132, 162 + d)
      ..close();
    canvas.drawPath(rPaw, _fill(0.07));
    canvas.drawPath(rPaw, _stroke(1.8));
    for (final x in [118.0, 123.0, 128.0]) {
      canvas.drawLine(
          Offset(x, 165 + d), Offset(x, 178 + d), _stroke(1.0, a: 0.40));
    }
  }

  // ── Ambient sparkles ──────────────────────────────────────────────────────

  void _drawSparkles(Canvas canvas, double d) {
    const pts = [
      Offset(40,  60),
      Offset(162, 42),
      Offset(168, 150),
      Offset(34,  148),
      Offset(50,  196),
      Offset(158, 196),
    ];
    for (int i = 0; i < pts.length; i++) {
      final phase = (glowPhase + i / pts.length) % 1.0;
      final a = (sin(phase * 2 * pi) * 0.5 + 0.5) * 0.50;
      final r = (2.0 + sin(phase * 2 * pi + i) * 0.8).clamp(1.0, 4.0);
      canvas.drawCircle(Offset(pts[i].dx, pts[i].dy + d), r, _fill(a));
    }
  }

  @override
  bool shouldRepaint(_FoxPainter old) =>
      old.floatDy != floatDy || old.glowPhase != glowPhase;
}
