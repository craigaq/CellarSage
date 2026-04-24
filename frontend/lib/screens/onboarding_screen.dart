import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import '../widgets/palate_dial.dart';
import '../widgets/sage_fox_widget.dart';

class OnboardingScreen extends StatefulWidget {
  final VoidCallback onComplete;
  const OnboardingScreen({super.key, required this.onComplete});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final PageController _controller = PageController();
  int _currentPage = 0;

  void _next() {
    if (_currentPage < 2) {
      _controller.nextPage(
        duration: const Duration(milliseconds: 400),
        curve: Curves.easeInOut,
      );
    } else {
      widget.onComplete();
    }
  }

  @override
  void initState() {
    super.initState();
    _controller.addListener(() {
      final p = _controller.page?.round() ?? 0;
      if (p != _currentPage) setState(() => _currentPage = p);
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: WwColors.bgDeep,
      body: Column(
        children: [
          Expanded(
            child: PageView.builder(
              controller: _controller,
              itemCount: 3,
              onPageChanged: (p) => setState(() => _currentPage = p),
              itemBuilder: (context, index) => switch (index) {
                0 => const _CardIntroduction(),
                1 => const _CardPalatePromise(),
                _ => const _CardLocalLegend(),
              },
            ),
          ),

          // Button row — outside PageView to avoid Android 16 inset issues
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(32, 12, 32, 28),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Dot indicators
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: List.generate(3, (i) {
                      final active = i == _currentPage;
                      return AnimatedContainer(
                        duration: const Duration(milliseconds: 250),
                        margin: const EdgeInsets.symmetric(horizontal: 4),
                        width: active ? 24 : 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: active
                              ? WwColors.violet
                              : WwColors.borderMedium,
                          borderRadius: BorderRadius.circular(4),
                        ),
                      );
                    }),
                  ),

                  const SizedBox(height: 20),

                  // CTA button with gold glow
                  Container(
                    width: double.infinity,
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(12),
                      boxShadow: WwDecorations.violetGlow(),
                    ),
                    child: FilledButton(
                      onPressed: _next,
                      child: Text(
                        _currentPage == 2 ? "Let's Begin" : 'Next',
                        style: WwText.labelLarge(color: Colors.black),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Card 1 — The Introduction
// ---------------------------------------------------------------------------

class _CardIntroduction extends StatelessWidget {
  const _CardIntroduction();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [WwColors.bgDeep, WwColors.bgSurface],
        ),
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(32, 48, 32, 24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const SageFoxWidget(),

              const SizedBox(height: 44),

              Text(
                'Welcome to the\nInner Circle.',
                textAlign: TextAlign.center,
                style: WwText.displayLarge(),
              ),

              const SizedBox(height: 18),

              Text(
                "I'm the Sage Fox — your algorithmic guide to finding the right bottle, every time.",
                textAlign: TextAlign.center,
                style: WwText.bodyLarge(color: WwColors.textSecondary),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Card 2 — The Palate Promise
// ---------------------------------------------------------------------------

class _CardPalatePromise extends StatelessWidget {
  const _CardPalatePromise();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [WwColors.bgDeep, WwColors.bgSurface],
        ),
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(32, 48, 32, 24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              SizedBox(
                width: 220,
                height: 220,
                child: PalateDial(
                  crispness: 3,
                  weight: 3,
                  flavorIntensity: 4,
                  texture: 2,
                ),
              ),

              const SizedBox(height: 36),

              Text(
                "I'll help you speak\n'Wine' like a pro.",
                textAlign: TextAlign.center,
                style: WwText.headlineLarge(),
              ),

              const SizedBox(height: 16),

              RichText(
                textAlign: TextAlign.center,
                text: TextSpan(
                  style: WwText.bodyLarge(color: WwColors.textSecondary),
                  children: [
                    const TextSpan(text: 'Whether you like it '),
                    TextSpan(
                      text: 'Zingy (High Acidity)',
                      style: WwText.bodyLarge(color: WwColors.violet)
                          .copyWith(fontStyle: FontStyle.italic),
                    ),
                    const TextSpan(text: ' or '),
                    TextSpan(
                      text: 'Grippy (High Tannin)',
                      style: WwText.bodyLarge(color: WwColors.violet)
                          .copyWith(fontStyle: FontStyle.italic),
                    ),
                    TextSpan(
                      text: ", we'll find your perfect match.",
                      style: WwText.bodyLarge(color: WwColors.textSecondary),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Card 3 — The Local Legend
// ---------------------------------------------------------------------------

class _CardLocalLegend extends StatefulWidget {
  const _CardLocalLegend();

  @override
  State<_CardLocalLegend> createState() => _CardLocalLegendState();
}

class _CardLocalLegendState extends State<_CardLocalLegend>
    with SingleTickerProviderStateMixin {
  late final AnimationController _anim;
  late final Animation<double> _glow;

  @override
  void initState() {
    super.initState();
    _anim = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _glow = Tween<double>(begin: 0.2, end: 0.65)
        .animate(CurvedAnimation(parent: _anim, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _anim.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topRight,
          end: Alignment.bottomLeft,
          colors: [WwColors.bgDeep, WwColors.bgSurface],
        ),
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(32, 48, 32, 24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              // Pulsing gold map pin
              AnimatedBuilder(
                animation: _glow,
                builder: (context, child) => Container(
                  width: 110,
                  height: 110,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: WwColors.violet.withValues(alpha: _glow.value),
                        blurRadius: 44,
                        spreadRadius: 8,
                      ),
                    ],
                  ),
                  child: child,
                ),
                child: const Center(
                  child: Icon(
                    Icons.location_on_rounded,
                    size: 80,
                    color: WwColors.violet,
                  ),
                ),
              ),

              const SizedBox(height: 44),

              Text(
                'Best of all?',
                textAlign: TextAlign.center,
                style: WwText.headlineLarge(),
              ),

              const SizedBox(height: 16),

              Text(
                "I'll show you exactly which shop down the street is holding your bottle.\n\nReady to begin your quest?",
                textAlign: TextAlign.center,
                style: WwText.bodyLarge(color: WwColors.textSecondary),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
