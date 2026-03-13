import 'package:flutter/material.dart';

import '../models/wine_recommendation.dart';
import '../screens/nearby_screen.dart';
import '../services/api_service.dart';
import '../widgets/conflict_alert.dart';
import '../widgets/palate_dial.dart';

class QuizScreen extends StatefulWidget {
  const QuizScreen({super.key});

  @override
  State<QuizScreen> createState() => _QuizScreenState();
}

class _QuizScreenState extends State<QuizScreen> {
  final PageController _controller = PageController();
  int _currentPage = 0;

  // --- Quiz state ---
  int _crispness = 3;
  int _weight = 3;
  int _texture = 3;
  int _flavor = 3;
  String _foodPairing = 'None';
  String _budgetLabel = '\$16 – \$25';

  // --- Results state ---
  List<WineRecommendation>? _results;
  bool _loading = false;
  String? _error;

  static const int _totalPages = 10;
  static const List<String> _foodOptions = [
    'None',
    'Chicken/Fish',
    'Red Meat',
    'Cheese',
    'Dessert',
  ];
  static const List<Map<String, Object>> _budgetOptions = [
    {'label': '\$5 – \$15',   'min': 5.0,   'max': 15.0},
    {'label': '\$16 – \$25',  'min': 16.0,  'max': 25.0},
    {'label': '\$26 – \$50',  'min': 26.0,  'max': 50.0},
    {'label': '\$51 – \$100', 'min': 51.0,  'max': 100.0},
    {'label': '\$101+',       'min': 101.0, 'max': 9999.0},
  ];

  Map<String, Object> get _selectedBudget =>
      _budgetOptions.firstWhere((b) => b['label'] == _budgetLabel);

  bool get _hasConflict => _weight <= 2 && _texture >= 4;

  // ---------------------------------------------------------------------------
  // Navigation
  // ---------------------------------------------------------------------------

  Future<void> _goNext() async {
    if (_currentPage == 5 && _hasConflict) {
      await showConflictAlert(
        context,
        onIncreaseWeight: () => setState(() => _weight = 3),
        onReduceTexture: () => setState(() => _texture = 2),
      );
    }
    if (_currentPage == 8) {
      _fetchResults();
    }
    if (_currentPage < _totalPages - 1) {
      _controller.nextPage(
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
    }
  }

  void _goBack() {
    if (_currentPage > 0) {
      _controller.previousPage(
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
    }
  }

  Future<void> _fetchResults() async {
    setState(() {
      _loading = true;
      _error = null;
      _results = null;
    });
    try {
      final results = await ApiService().recommend(
        crispnessAcidity: _crispness,
        weightBody: _weight,
        textureTannin: _texture,
        flavorIntensity: _flavor,
        foodPairing: _foodPairing,
      );
      setState(() {
        _results = results;
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Build
  // ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Wine Wizard'),
        centerTitle: true,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(4),
          child: LinearProgressIndicator(
            value: (_currentPage + 1) / _totalPages,
            backgroundColor: Colors.deepPurple.shade100,
          ),
        ),
      ),
      body: PageView(
        controller: _controller,
        physics: const NeverScrollableScrollPhysics(),
        onPageChanged: (p) => setState(() => _currentPage = p),
        children: [
          _buildWelcome(),
          _buildAttributeStep(
            title: 'Crispness (Acidity)',
            description:
                'How much do you enjoy a fresh, zesty bite in your wine?',
            lowLabel: 'Smooth & Mellow',
            highLabel: 'Sharp & Zesty',
            value: _crispness,
            onChanged: (v) => setState(() => _crispness = v),
          ),
          _buildAttributeStep(
            title: 'Weight (Body)',
            description:
                'Do you prefer a light, delicate sip or a rich, full-bodied experience?',
            lowLabel: 'Light & Delicate',
            highLabel: 'Rich & Full',
            value: _weight,
            onChanged: (v) => setState(() => _weight = v),
          ),
          _buildAttributeStep(
            title: 'Texture (Tannin)',
            description:
                'How do you feel about that dry, grippy sensation common in red wines?',
            lowLabel: 'Silky & Smooth',
            highLabel: 'Grippy & Bold',
            value: _texture,
            onChanged: (v) => setState(() => _texture = v),
          ),
          _buildAttributeStep(
            title: 'Flavor Intensity (Aromatics)',
            description:
                'Do you prefer subtle, understated flavors or bold, expressive ones?',
            lowLabel: 'Subtle & Quiet',
            highLabel: 'Bold & Expressive',
            value: _flavor,
            onChanged: (v) => setState(() => _flavor = v),
          ),
          _buildFoodPairingStep(),
          _buildBudgetStep(),
          _buildPalateDialStep(),
          _buildSummaryStep(),
          _buildResultsStep(),
        ],
      ),
      bottomNavigationBar: _buildNavBar(),
    );
  }

  // ---------------------------------------------------------------------------
  // Nav bar
  // ---------------------------------------------------------------------------

  Widget _buildNavBar() {
    final isFirst = _currentPage == 0;
    final isLast = _currentPage == _totalPages - 1;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            if (!isFirst)
              OutlinedButton.icon(
                onPressed: _goBack,
                icon: const Icon(Icons.arrow_back),
                label: const Text('Back'),
              )
            else
              const SizedBox.shrink(),
            if (!isLast)
              FilledButton.icon(
                onPressed: _goNext,
                label: Text(_currentPage == 8 ? 'Find My Wine!' : 'Next'),
                icon: const Icon(Icons.arrow_forward),
                iconAlignment: IconAlignment.end,
              ),
          ],
        ),
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 0 — Welcome
  // ---------------------------------------------------------------------------

  Widget _buildWelcome() {
    return _stepShell(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text('🍷', style: TextStyle(fontSize: 72)),
          const SizedBox(height: 24),
          Text(
            'Welcome to Wine Wizard',
            style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          Text(
            'Answer 8 quick questions about your palate and we\'ll find wines that actually match how you think.',
            style: Theme.of(context).textTheme.bodyLarge,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          FilledButton.icon(
            onPressed: _goNext,
            label: const Text('Let\'s Begin'),
            icon: const Icon(Icons.wine_bar),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Steps 1–4 — Attribute sliders
  // ---------------------------------------------------------------------------

  Widget _buildAttributeStep({
    required String title,
    required String description,
    required String lowLabel,
    required String highLabel,
    required int value,
    required ValueChanged<int> onChanged,
  }) {
    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 8),
          Text(description, style: Theme.of(context).textTheme.bodyMedium),
          const SizedBox(height: 40),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: List.generate(5, (i) {
              final v = i + 1;
              final selected = value == v;
              return GestureDetector(
                onTap: () => onChanged(v),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(
                    color: selected
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context).colorScheme.surfaceContainerHighest,
                    shape: BoxShape.circle,
                    boxShadow: selected
                        ? [
                            BoxShadow(
                              color: Theme.of(context)
                                  .colorScheme
                                  .primary
                                  .withValues(alpha: 0.4),
                              blurRadius: 8,
                              spreadRadius: 1,
                            ),
                          ]
                        : [],
                  ),
                  child: Center(
                    child: Text(
                      '$v',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 18,
                        color: selected
                            ? Colors.white
                            : Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ),
              );
            }),
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                lowLabel,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: Colors.grey),
              ),
              Text(
                highLabel,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: Colors.grey),
              ),
            ],
          ),
          const SizedBox(height: 40),
          Center(
            child: SizedBox(
              width: 200,
              height: 200,
              child: PalateDial(
                crispness: _crispness,
                weight: _weight,
                flavorIntensity: _flavor,
                texture: _texture,
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 5 — Food Pairing
  // ---------------------------------------------------------------------------

  Widget _buildFoodPairingStep() {
    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Food Pairing',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'What are you planning to eat? We\'ll fine-tune your recommendations.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 32),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: _foodOptions.map((option) {
              final selected = _foodPairing == option;
              return ChoiceChip(
                label: Text(option),
                selected: selected,
                onSelected: (_) => setState(() => _foodPairing = option),
                selectedColor: Theme.of(context).colorScheme.primaryContainer,
                labelStyle: TextStyle(
                  fontWeight:
                      selected ? FontWeight.bold : FontWeight.normal,
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 6 — Budget
  // ---------------------------------------------------------------------------

  Widget _buildBudgetStep() {
    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Your Budget (per bottle)',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'The Wizard respects all budgets. Even the modest ones.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 32),
          Column(
            children: _budgetOptions.map((option) {
              final label = option['label'] as String;
              final selected = _budgetLabel == label;
              return GestureDetector(
                onTap: () => setState(() => _budgetLabel = label),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  margin: const EdgeInsets.only(bottom: 12),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 20, vertical: 16),
                  decoration: BoxDecoration(
                    color: selected
                        ? Theme.of(context).colorScheme.primaryContainer
                        : Theme.of(context).colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: selected
                          ? Theme.of(context).colorScheme.primary
                          : Colors.transparent,
                      width: 2,
                    ),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        label,
                        style: TextStyle(
                          fontWeight: selected
                              ? FontWeight.bold
                              : FontWeight.normal,
                          fontSize: 16,
                        ),
                      ),
                      if (selected)
                        Icon(
                          Icons.check_circle,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 7 — Palate Dial
  // ---------------------------------------------------------------------------

  Widget _buildPalateDialStep() {
    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            'Your Palate Dial',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Here\'s a snapshot of your palate. Looking good.',
            style: Theme.of(context).textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          PalateDial(
            crispness: _crispness,
            weight: _weight,
            flavorIntensity: _flavor,
            texture: _texture,
          ),
          if (_hasConflict) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.amber.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.amber.shade300),
              ),
              child: const Row(
                children: [
                  Text('🧙‍♂️'),
                  SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      'Hmm. Light Weight with High Texture — the Wizard has thoughts. Tap Next.',
                      style: TextStyle(fontSize: 13, fontStyle: FontStyle.italic),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 7 — Summary
  // ---------------------------------------------------------------------------

  Widget _buildSummaryStep() {
    final rows = [
      ('Crispness (Acidity)', _crispness),
      ('Weight (Body)', _weight),
      ('Texture (Tannin)', _texture),
      ('Flavor Intensity (Aromatics)', _flavor),
    ];
    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Your Profile',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Looking good. Hit "Find My Wine!" when you\'re ready.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 24),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  ...rows.map(
                    (r) => Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(r.$1,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w500)),
                          _ScoreDots(value: r.$2),
                        ],
                      ),
                    ),
                  ),
                  const Divider(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Food Pairing',
                          style: TextStyle(fontWeight: FontWeight.w500)),
                      Text(_foodPairing,
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.primary,
                              fontWeight: FontWeight.w600)),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Budget (per bottle)',
                          style: TextStyle(fontWeight: FontWeight.w500)),
                      Text(_budgetLabel,
                          style: TextStyle(
                              color: Theme.of(context).colorScheme.primary,
                              fontWeight: FontWeight.w600)),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 8 — Results
  // ---------------------------------------------------------------------------

  Widget _buildResultsStep() {
    if (_loading) {
      return const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Consulting the cellar...'),
          ],
        ),
      );
    }
    if (_error != null) {
      return _stepShell(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('😬', style: TextStyle(fontSize: 48)),
            const SizedBox(height: 16),
            Text('Something went wrong:', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(_error!, style: const TextStyle(color: Colors.red)),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _fetchResults,
              child: const Text('Try Again'),
            ),
          ],
        ),
      );
    }
    if (_results == null) {
      return const Center(child: Text('No results yet.'));
    }
    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Your Recommendations',
            style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
          ),
          const SizedBox(height: 8),
          Text(
            'Ranked by how well they match your palate.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 16),
          ..._results!.asMap().entries.map((entry) {
            final rank = entry.key + 1;
            final wine = entry.value;
            return Card(
              margin: const EdgeInsets.only(bottom: 12),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: rank == 1
                        ? Colors.amber.shade300
                        : rank == 2
                            ? Colors.grey.shade300
                            : Colors.brown.shade200,
                    child: Text(
                      '$rank',
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                  ),
                  title: Text(wine.name,
                      style: const TextStyle(fontWeight: FontWeight.bold)),
                  subtitle: Text(
                      'Match score: ${(wine.score * 100).toStringAsFixed(1)}%'),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (rank == 1)
                        const Padding(
                          padding: EdgeInsets.only(right: 8),
                          child: Text('🍷', style: TextStyle(fontSize: 20)),
                        ),
                      OutlinedButton.icon(
                        onPressed: () => Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (_) => NearbyScreen(
                              wineName: wine.name,
                              budgetMin: (_selectedBudget['min'] as double),
                              budgetMax: (_selectedBudget['max'] as double),
                            ),
                          ),
                        ),
                        icon: const Icon(Icons.place, size: 16),
                        label: const Text('Find Nearby'),
                        style: OutlinedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 4),
                          textStyle: const TextStyle(fontSize: 12),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          }),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Shared scaffold wrapper
  // ---------------------------------------------------------------------------

  Widget _stepShell({required Widget child}) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: child,
    );
  }
}

// ---------------------------------------------------------------------------
// Score dot indicator widget
// ---------------------------------------------------------------------------

class _ScoreDots extends StatelessWidget {
  final int value;
  const _ScoreDots({required this.value});

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return Row(
      children: List.generate(5, (i) {
        return Container(
          margin: const EdgeInsets.only(left: 4),
          width: 10,
          height: 10,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: i < value ? color : Colors.grey.shade300,
          ),
        );
      }),
    );
  }
}
