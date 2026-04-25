import 'dart:math';
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
      builder: (_, __) {
        final dy = sin(_idle.value * 2 * pi) * 5.0;
        return Transform.translate(
          offset: Offset(0, dy),
          child: SvgPicture.asset(
            'assets/images/sage_fox.svg',
            width: widget.size,
            height: widget.size,
          ),
        );
      },
    );
  }
}
