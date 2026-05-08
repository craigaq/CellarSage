import 'dart:math';
import 'dart:ui' show ImageFilter;
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

/// Sage Fox mascot — renders the brand SVG with a gentle float-bob animation.
class SageFoxWidget extends StatefulWidget {
  final double size;
  final Duration delay;
  const SageFoxWidget({super.key, this.size = 200, this.delay = Duration.zero});

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
        final dy = sin(_idle.value * 2 * pi) * 5.0;
        return Transform.translate(
          offset: Offset(0, dy),
          child: Stack(
            alignment: Alignment.center,
            children: [
              // White glow layer: fox silhouette blurred outward behind the original.
              ImageFiltered(
                imageFilter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                child: ColorFiltered(
                  colorFilter: const ColorFilter.matrix([
                    0, 0, 0, 0, 255,
                    0, 0, 0, 0, 255,
                    0, 0, 0, 0, 255,
                    0, 0, 0, 0.55, 0,
                  ]),
                  child: SvgPicture.asset(
                    'assets/images/sage_fox_nobg.svg',
                    width: widget.size,
                    height: widget.size,
                  ),
                ),
              ),
              SvgPicture.asset(
                'assets/images/sage_fox_nobg.svg',
                width: widget.size,
                height: widget.size,
              ),
            ],
          ),
        );
      },
    );
  }
}
