import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/wine_recommendation.dart';
import '../services/api_service.dart';
import '../services/palate_prefs.dart';
import '../screens/wine_picks_screen.dart';
import '../services/currency_service.dart';
import '../theme/app_theme.dart';
import '../widgets/conflict_alert.dart';
import '../widgets/magic_palette_step.dart';
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
  String _foodPairing = 'none'; // stores the backend ID
  int _budgetIndex = 1; // index into CurrencyService.getBrackets()
  String _currencyCode = 'AUD'; // resolved from GPS in initState
  bool _prefDry = false;
  String _overrideMode = 'use_pairing_logic';
  String _pairingMode = 'congruent'; // 'congruent' | 'contrast'

  // --- Results state ---
  List<WineRecommendation>? _results;
  bool _loading = false;
  String? _error;
  ConflictAlert? _conflictAlert;
  int _fetchGeneration = 0;

  // --- Saved profiles ---
  List<PalateProfile> _savedProfiles = [];

  static const int _totalPages = 9;

  /// Each entry: label = UI text, id = backend key, emoji = grid icon,
  /// comment = fox commentary shown when the item is selected.
  static const List<Map<String, String>> _foodOptions = [
    {
      'label': 'Steak, Lamb, or Burgers',
      'id': 'red_meat',
      'emoji': '🥩',
      'comment':
          "Steak nights are the best! We'll hunt for a wine with enough 'grip' (Tannin) to handle all that richness.",
      'contrast_comment':
          "Bold move — we'll find a bright, acid-driven wine to cut through the fat instead. Think Pinot Noir over Cabernet.",
    },
    {
      'label': 'Chicken, Turkey, or Pork',
      'id': 'poultry',
      'emoji': '🍗',
      'comment':
          "Chicken or pork? A versatile choice! Let's find a wine that's supportive but still brings its own personality to the party.",
      'contrast_comment':
          "Rather than mirroring the delicacy, we'll find a richer, more expressive wine to frame the dish. Viognier energy.",
    },
    {
      'label': 'White Fish or Shellfish',
      'id': 'white_fish',
      'emoji': '🐟',
      'comment':
          "Delicate flavors! We'll keep things light and 'crisp' (Acidity) so the wine doesn't drown out the fish.",
      'contrast_comment':
          "We'll look for a more textured, expressive wine to frame the delicacy — think skin-contact or fuller whites. Tannin still off-limits.",
    },
    {
      'label': 'Salmon or Tuna',
      'id': 'rich_fish',
      'emoji': '🍣',
      'comment':
          "Salmon has some weight to it! We need a wine with enough 'zing' (Acidity) to cut through the richness.",
      'contrast_comment':
          "Instead of cutting through the richness, we'll match salmon's weight with a full-bodied wine. Richness meets richness.",
    },
    {
      'label': 'Spicy Curry or Tacos',
      'id': 'spicy_food',
      'emoji': '🌶️',
      'comment':
          "Ooh, a spicy one! We'll look for something 'fruity' (Aromatics) to act like a fire extinguisher for your tongue.",
      'contrast_comment':
          "Dangerous choice — we'll amplify the fire instead of fighting it. Maximum aromatics to match the dish's intensity.",
    },
    {
      'label': 'Tomato Pasta or Pizza',
      'id': 'tomato_sauce',
      'emoji': '🍕',
      'comment':
          "Zesty tomato sauce! We need a wine with enough 'punch' (Acidity) to keep up with that tangy energy.",
      'contrast_comment':
          "Instead of matching the tang, we'll find a smooth, round wine to soften it. The velvet glove to the tomato's fist.",
    },
    {
      'label': 'Creamy or Cheesy Pasta',
      'id': 'creamy_sauce',
      'emoji': '🧀',
      'comment':
          "Rich and buttery? We'll find a 'heavyweight' (Full-bodied) wine that feels just as luxurious as the sauce.",
      'contrast_comment':
          "Classic sommelier move — a razor-sharp, high-acid wine to cut straight through all that dairy fat. Chablis would approve.",
    },
    {
      'label': 'Salads or Green Veggies',
      'id': 'greens',
      'emoji': '🥗',
      'comment':
          "Fresh and light! Let's pick a 'crisp' (Acidity) wine that tastes like a summer garden in a glass.",
      'contrast_comment':
          "Rather than mirroring the freshness, we'll find an earthy, more expressive wine to complement those green notes.",
    },
    {
      'label': 'Cheese & Charcuterie',
      'id': 'charcuterie',
      'emoji': '🍖',
      'comment':
          "The ultimate snack pack! We'll find a crowd-pleaser that can handle everything from creamy brie to salty salami.",
      'contrast_comment':
          "We'll go lean and punchy — high acid to cut aggressively through all that fat and salt. A wine with something to say.",
    },
    {
      'label': 'Just sipping (No food)',
      'id': 'none',
      'emoji': '🍷',
      'comment':
          "Just a glass and some good vibes? Perfection. Let's find a wine that's a star all on its own.",
      'contrast_comment':
          "Just a glass and some good vibes? Perfection. Let's find a wine that's a star all on its own.",
    },
  ];

  static const List<String> _attrOrder = [
    'Crispness (Acidity)',
    'Weight (Body)',
    'Texture (Tannin)',
    'Flavor Intensity (Aromatics)',
  ];

  BudgetBracket get _selectedBracket =>
      CurrencyService.getBrackets(_currencyCode)[_budgetIndex];

  String get _foodLabel =>
      _foodOptions.firstWhere((f) => f['id'] == _foodPairing)['label'] ??
      _foodPairing;

  String? get _foodComment {
    final option = _foodOptions.firstWhere(
      (f) => f['id'] == _foodPairing,
      orElse: () => {},
    );
    if (option.isEmpty) return null;
    return _pairingMode == 'contrast'
        ? (option['contrast_comment'] ?? option['comment'])
        : option['comment'];
  }

  Map<String, int> get _userPrefs => {
    'Crispness (Acidity)': _crispness,
    'Weight (Body)': _weight,
    'Texture (Tannin)': _texture,
    'Flavor Intensity (Aromatics)': _flavor,
  };

  bool get _hasConflict =>
      (_weight <= 2 && _texture >= 4) ||       // Light body + high tannin
      (_flavor <= 1 && _crispness >= 4) ||      // Near-zero flavour + razor acidity
      (_texture >= 5 && _crispness >= 5);       // Maximum tannin + maximum acidity

  // ---------------------------------------------------------------------------
  // Navigation
  // ---------------------------------------------------------------------------

  Future<void> _goNext() async {
    // Food page (5) → check for gastro clash before advancing
    if (_currentPage == 5 && _foodPairing != 'none') {
      await _checkAndHandlePairingClash();
    }
    if (_currentPage == 7) {
      _fetchResults();
    }
    if (_currentPage < _totalPages - 1) {
      _controller.nextPage(
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
    }
  }

  /// Calls the lightweight GET /check-pairing endpoint and surfaces:
  ///   • Gastro-Clash alert  — food/palate attribute mismatch
  ///   • Palate Paradox sheet — dry preference vs sweet-pairing food
  Future<void> _checkAndHandlePairingClash() async {
    try {
      final result = await ApiService().checkPairing(
        foodType: _foodPairing,
        crispnessAcidity: _crispness,
        weightBody: _weight,
        textureTannin: _texture,
        flavorIntensity: _flavor,
        prefDry: _prefDry,
      );
      if (!mounted) return;
      if (result.gastroClash != null) {
        await showGastroClashAlert(
          context,
          result.gastroClash!,
          _applyGastroAdjustment,
        );
      }
      if (!mounted) return;
      if (result.palateParadox != null) {
        await showPalateParadoxSheet(
          context,
          result.palateParadox!,
          (action) => setState(() => _overrideMode = action),
        );
      }
    } catch (_) {
      // Non-critical — proceed without blocking navigation
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

  void _skipToSip() {
    setState(() {
      _foodPairing = 'none';
      _overrideMode = 'use_pairing_logic';
      _pairingMode = 'congruent';
    });
    _fetchResults();
    _controller.animateToPage(
      _totalPages - 1,
      duration: const Duration(milliseconds: 500),
      curve: Curves.easeInOut,
    );
  }

  void _startOver() {
    setState(() {
      _crispness = 3;
      _weight = 3;
      _texture = 3;
      _flavor = 3;
      _foodPairing = 'none';
      _budgetIndex = 1;
      _prefDry = false;
      _overrideMode = 'use_pairing_logic';
      _pairingMode = 'congruent';
      _results = null;
      _loading = false;
      _error = null;
      _conflictAlert = null;
    });
    _controller.animateToPage(
      0,
      duration: const Duration(milliseconds: 500),
      curve: Curves.easeInOut,
    );
  }

  // ---------------------------------------------------------------------------
  // Saved profiles
  // ---------------------------------------------------------------------------

  Future<void> _refreshProfiles() async {
    final profiles = await PalatePrefs.loadProfiles();
    if (mounted) setState(() => _savedProfiles = profiles);
  }

  void _loadProfileAndJump(PalateProfile profile) {
    setState(() {
      _crispness   = profile.crispness;
      _weight      = profile.weight;
      _texture     = profile.texture;
      _flavor      = profile.flavor;
      _foodPairing = profile.foodPairing;
      _budgetIndex = profile.budgetIndex;
      _prefDry     = profile.prefDry;
      _overrideMode = 'use_pairing_logic';
      _pairingMode  = 'congruent';
    });
    _controller.animateToPage(
      7, // summary page
      duration: const Duration(milliseconds: 400),
      curve: Curves.easeInOut,
    );
  }

  String _suggestProfileName() {
    final existing = _savedProfiles.map((p) => p.name).toSet();
    if (!existing.contains('My Profile')) return 'My Profile';
    int n = 2;
    while (existing.contains('My Profile $n')) n++;
    return 'My Profile $n';
  }

  Future<void> _showSaveProfileDialog() async {
    String name = _suggestProfileName();

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setLocal) => AlertDialog(
          backgroundColor: WwColors.bgElevated,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: WwColors.borderSubtle),
          ),
          title: Text('Save Profile', style: WwText.titleMedium()),
          content: TextFormField(
            initialValue: name,
            autofocus: true,
            maxLength: 24,
            style: WwText.bodyMedium(),
            decoration: const InputDecoration(
              labelText: 'Profile name',
              hintText: 'e.g. Friday Night Reds',
            ),
            onChanged: (v) => name = v,
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Save'),
            ),
          ],
        ),
      ),
    );

    if (confirmed != true || name.trim().isEmpty || !mounted) return;

    final snap = PalateSnapshot(
      crispness:   _crispness,
      weight:      _weight,
      texture:     _texture,
      flavor:      _flavor,
      foodPairing: _foodPairing,
      budgetIndex: _budgetIndex,
      prefDry:     _prefDry,
    );
    final saved = await PalatePrefs.saveProfile(name.trim(), snap);
    await _refreshProfiles();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(saved
              ? 'Profile "${name.trim()}" saved'
              : 'Profile limit reached — delete one first'),
        ),
      );
    }
  }

  Future<void> _confirmDeleteProfile(PalateProfile profile) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: WwColors.bgElevated,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: WwColors.borderSubtle),
        ),
        title: Text('Delete Profile?', style: WwText.titleMedium()),
        content: Text(
          'Remove "${profile.name}"? This cannot be undone.',
          style: WwText.bodyMedium(),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: WwColors.error),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      await PalatePrefs.deleteProfile(profile.id);
      await _refreshProfiles();
    }
  }

  Future<void> _fetchResults() async {
    final generation = ++_fetchGeneration;
    PalatePrefs.save(
      crispness:   _crispness,
      weight:      _weight,
      texture:     _texture,
      flavor:      _flavor,
      foodPairing: _foodPairing,
      budgetIndex: _budgetIndex,
      prefDry:     _prefDry,
    );
    setState(() {
      _loading = true;
      _error = null;
      _results = null;
      _conflictAlert = null;
    });
    try {
      final result = await ApiService().recommend(
        crispnessAcidity: _crispness,
        weightBody: _weight,
        textureTannin: _texture,
        flavorIntensity: _flavor,
        foodPairing: _foodPairing,
        prefDry: _prefDry,
        overrideMode: _overrideMode,
        pairingMode: _pairingMode,
      );
      if (generation != _fetchGeneration || !mounted) return;
      setState(() {
        _results = result.recommendations;
        _conflictAlert = result.alert;
        _loading = false;
      });
      // Palate conflict alert (shown after results load)
      if (result.alert != null && mounted) {
        await showConflictAlert(
          context,
          result.alert!,
          _applyConflictAdjustment,
        );
      }
    } catch (e) {
      if (generation != _fetchGeneration || !mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  /// Updates palate dial state from a Gastro-Clash override.
  /// Does NOT fetch results — the search runs later when the quiz completes.
  void _applyGastroAdjustment(Map<String, int> newValues) {
    setState(() {
      for (final entry in newValues.entries) {
        switch (entry.key) {
          case 'texture_tannin':
            _texture = entry.value;
          case 'weight_body':
            _weight = entry.value;
          case 'crispness_acidity':
            _crispness = entry.value;
          case 'flavor_intensity':
            _flavor = entry.value;
        }
      }
    });
  }

  void _applyConflictAdjustment(int value) {
    setState(() {
      switch (_conflictAlert?.field) {
        case 'texture_tannin':
          _texture = value;
        case 'weight_body':
          _weight = value;
        case 'crispness_acidity':
          _crispness = value;
        case 'flavor_intensity':
          _flavor = value;
      }
    });
    _fetchResults();
  }

  // ---------------------------------------------------------------------------
  // Build
  // ---------------------------------------------------------------------------

  @override
  void initState() {
    super.initState();
    CurrencyService.detectCodeFromGps().then((code) {
      if (mounted) setState(() => _currencyCode = code);
    });
    PalatePrefs.load().then((snap) {
      if (snap != null && mounted) {
        setState(() {
          _crispness   = snap.crispness;
          _weight      = snap.weight;
          _texture     = snap.texture;
          _flavor      = snap.flavor;
          _foodPairing = snap.foodPairing;
          _budgetIndex = snap.budgetIndex;
          _prefDry     = snap.prefDry;
        });
      }
    });
    _refreshProfiles();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Cellar Sage', style: WwText.titleLarge()),
        centerTitle: true,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(3),
          child: LinearProgressIndicator(
            value: (_currentPage + 1) / _totalPages,
            backgroundColor: WwColors.borderSubtle,
            valueColor: const AlwaysStoppedAnimation<Color>(WwColors.violet),
          ),
        ),
      ),
      body: Column(
        children: [
          AnimatedSize(
            duration: const Duration(milliseconds: 250),
            curve: Curves.easeInOut,
            child: (_currentPage >= 1 && _currentPage <= 6)
                ? _buildLivingPalate()
                : const SizedBox.shrink(),
          ),
          Expanded(
            child: PageView(
              controller: _controller,
              physics: const NeverScrollableScrollPhysics(),
              onPageChanged: (p) => setState(() => _currentPage = p),
              children: [
                _buildWelcome(),
                _buildAttributeStep(
                  title: 'Crispness (Acidity)',
                  description:
                      'How much do you enjoy a fresh, zesty bite in your wine?',
                  value: _crispness,
                  onChanged: (v) => setState(() => _crispness = v),
                ),
                _buildAttributeStep(
                  title: 'Weight (Body)',
                  description:
                      'Do you prefer a light, delicate sip or a rich, full-bodied experience?',
                  value: _weight,
                  onChanged: (v) => setState(() => _weight = v),
                ),
                _buildAttributeStep(
                  title: 'Texture (Tannin)',
                  description:
                      'How do you feel about that dry, grippy sensation common in red wines?',
                  value: _texture,
                  onChanged: (v) => setState(() => _texture = v),
                ),
                _buildAttributeStep(
                  title: 'Flavor Intensity (Aromatics)',
                  description:
                      'Do you prefer subtle, understated flavors or bold, expressive ones?',
                  value: _flavor,
                  onChanged: (v) => setState(() => _flavor = v),
                ),
                _buildFoodPairingStep(),
                _buildBudgetStep(),
                _buildSummaryStep(),
                _buildResultsStep(),
              ],
            ),
          ),
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
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
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
                if (isLast)
                  TextButton.icon(
                    onPressed: _startOver,
                    icon: const Icon(Icons.refresh),
                    label: const Text('Start Over'),
                  )
                else
                  FilledButton.icon(
                    onPressed: _goNext,
                    label: Text(_currentPage == 7 ? 'Find My Wine!' : 'Next'),
                    icon: const Icon(Icons.arrow_forward),
                    iconAlignment: IconAlignment.end,
                  ),
              ],
            ),
            if (_currentPage == 4) ...[
              const SizedBox(height: 4),
              TextButton(
                onPressed: _skipToSip,
                child: Text(
                  'Skip to Sip →',
                  style: WwText.bodySmall().copyWith(color: WwColors.violetMuted),
                ),
              ),
            ],
            if (_currentPage >= 4 && _currentPage < 7) ...[
              const SizedBox(height: 4),
              TextButton.icon(
                onPressed: _savedProfiles.length < PalatePrefs.maxProfiles
                    ? _showSaveProfileDialog
                    : null,
                icon: const Icon(Icons.bookmark_add_outlined, size: 14),
                label: const Text('Save Profile'),
                style: TextButton.styleFrom(
                  foregroundColor: WwColors.violetMuted,
                  textStyle: WwText.bodySmall(),
                ),
              ),
            ],
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
            'Welcome to\nCellar Sage',
            style: WwText.displayLarge(),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          Text(
            'Answer 7 quick questions about your palate and we\'ll find wines that actually match how you think.',
            style: WwText.bodyLarge(color: WwColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: _goNext,
              label: const Text('Let\'s Begin'),
              icon: const Icon(Icons.wine_bar),
            ),
          ),
          if (_savedProfiles.isNotEmpty) ...[
            const SizedBox(height: 28),
            Row(
              children: [
                const Expanded(child: Divider()),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  child: Text(
                    'Saved Profiles',
                    style: WwText.bodySmall(color: WwColors.textSecondary),
                  ),
                ),
                const Expanded(child: Divider()),
              ],
            ),
            const SizedBox(height: 12),
            ..._savedProfiles.map((p) {
              final foodLabel = _foodOptions.firstWhere(
                (f) => f['id'] == p.foodPairing,
                orElse: () => {'label': p.foodPairing},
              )['label'] ?? p.foodPairing;
              return _ProfileCard(
                profile: p,
                foodLabel: foodLabel,
                onTap: () => _loadProfileAndJump(p),
                onDelete: () => _confirmDeleteProfile(p),
              );
            }),
          ],
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Steps 1–4 — Attribute selectors
  // ---------------------------------------------------------------------------

  Widget _buildAttributeStep({
    required String title,
    required String description,
    required int value,
    required ValueChanged<int> onChanged,
  }) {
    return _stepShell(
      child: MagicPaletteStep(
        title: title,
        description: description,
        value: value,
        onChanged: onChanged,
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 5 — Food Pairing
  // ---------------------------------------------------------------------------

  Widget _buildFoodPairingStep() {
    // "Just sipping" sits below the dry toggle; remaining options fill the grid.
    final soloOption = _foodOptions.last;
    final gridOptions = _foodOptions.sublist(0, _foodOptions.length - 1);

    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Food Pairing', style: WwText.headlineLarge()),
          const SizedBox(height: 8),
          Text(
            "What's on the table tonight? The Cellar Fox will fine-tune your match.",
            style: WwText.bodyMedium(),
          ),
          const SizedBox(height: 16),
          // Dry preference toggle — activates Palate Paradox detection
          Card(
            child: SwitchListTile(
              secondary: const Text('🍷', style: TextStyle(fontSize: 22)),
              title: const Text('I prefer dry wines'),
              subtitle: const Text('The Cellar Fox will flag sweet-pairing conflicts'),
              value: _prefDry,
              onChanged: (v) => setState(() {
                _prefDry = v;
                _overrideMode = 'use_pairing_logic';
              }),
            ),
          ),
          const SizedBox(height: 12),

          // "Just sipping" sits directly below the dry-wine toggle
          _FoodCard(
            option: soloOption,
            selected: _foodPairing == soloOption['id'],
            onTap: () => setState(() {
              _foodPairing = soloOption['id']!;
              _pairingMode = 'congruent'; // reset when food becomes none
            }),
            fullWidth: true,
          ),

          const SizedBox(height: 20),

          // 2-column icon grid for food items
          GridView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: gridOptions.length,
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              childAspectRatio: 1.35,
            ),
            itemBuilder: (context, i) => _FoodCard(
              option: gridOptions[i],
              selected: _foodPairing == gridOptions[i]['id'],
              onTap: () => setState(() => _foodPairing = gridOptions[i]['id']!),
            ),
          ),

          const SizedBox(height: 16),

          // Pairing Philosophy — animated reveal once a food is chosen
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 320),
            transitionBuilder: (child, animation) => FadeTransition(
              opacity: animation,
              child: SlideTransition(
                position: Tween<Offset>(
                  begin: const Offset(0, 0.08),
                  end: Offset.zero,
                ).animate(animation),
                child: child,
              ),
            ),
            child: _foodPairing != 'none'
                ? Padding(
                    key: const ValueKey('philosophy'),
                    padding: const EdgeInsets.only(bottom: 16),
                    child: _PairingPhilosophyPicker(
                      value: _pairingMode,
                      onChanged: (v) => setState(() => _pairingMode = v),
                    ),
                  )
                : const SizedBox.shrink(key: ValueKey('philosophy-hidden')),
          ),

          // Fox commentary — fades in/out as the selection changes
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            transitionBuilder: (child, animation) =>
                FadeTransition(opacity: animation, child: child),
            child: _foodComment != null
                ? _FoxComment(
                    key: ValueKey('$_foodPairing:$_pairingMode'),
                    text: _foodComment!,
                  )
                : const SizedBox.shrink(),
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
          Text('Your Budget (per bottle)', style: WwText.headlineLarge()),
          const SizedBox(height: 8),
          Text(
            'The Cellar Fox respects all budgets. Even the modest ones.',
            style: WwText.bodyMedium(),
          ),
          const SizedBox(height: 32),
          Column(
            children: CurrencyService.getBrackets(_currencyCode)
                .asMap()
                .entries
                .map((entry) {
                  final index = entry.key;
                  final bracket = entry.value;
                  final label = bracket.label;
                  final selected = _budgetIndex == index;
                  return GestureDetector(
                    onTap: () => setState(() => _budgetIndex = index),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      margin: const EdgeInsets.only(bottom: 12),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: 16,
                      ),
                      decoration: BoxDecoration(
                        color: selected
                            ? WwColors.bgElevated
                            : WwColors.bgSurface,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: selected
                              ? WwColors.violet
                              : WwColors.borderSubtle,
                          width: selected ? 2 : 1,
                        ),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            label,
                            style: WwText.bodyLarge(
                              color: selected
                                  ? WwColors.textPrimary
                                  : WwColors.textSecondary,
                            ).copyWith(
                              fontWeight: selected
                                  ? FontWeight.w600
                                  : FontWeight.w400,
                            ),
                          ),
                          if (selected)
                            const Icon(Icons.check_circle,
                                color: WwColors.violet),
                        ],
                      ),
                    ),
                  );
                })
                .toList(),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Living Palate — persistent radar chart header (steps 1–6)
  // ---------------------------------------------------------------------------

  Widget _buildLivingPalate() {
    return Container(
      decoration: BoxDecoration(
        color: WwColors.bgDeep,
        border: Border(bottom: BorderSide(color: WwColors.borderSubtle, width: 1)),
      ),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          SizedBox(
            width: 144,
            height: 144,
            child: PalateDial(
              crispness: _crispness,
              weight: _weight,
              flavorIntensity: _flavor,
              texture: _texture,
              compact: true,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 300),
              child: _hasConflict
                  ? Container(
                      key: const ValueKey('conflict'),
                      padding: const EdgeInsets.all(10),
                      margin: const EdgeInsets.only(left: 36),
                      decoration: WwDecorations.witCallout(),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Text('🦊', style: TextStyle(fontSize: 20)),
                          const SizedBox(height: 4),
                          Text(
                            'That\'s a spiky palate —\nthe Cellar Fox has a few thoughts.',
                            style: WwText.bodySmall(),
                          ),
                        ],
                      ),
                    )
                  : const SizedBox.shrink(key: ValueKey('ok')),
            ),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 7 — Summary (was Step 8; standalone Palate Dial step removed)
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
          Text('Your Profile', style: WwText.headlineLarge()),
          const SizedBox(height: 8),
          Text(
            'Looking good. Hit "Find My Wine!" when you\'re ready.',
            style: WwText.bodyMedium(),
          ),
          const SizedBox(height: 40),
          Center(
            child: SizedBox(
              height: 200,
              width: 200,
              child: PalateDial(
                crispness: _crispness,
                weight: _weight,
                flavorIntensity: _flavor,
                texture: _texture,
              ),
            ),
          ),
          const SizedBox(height: 40),
          Container(
            decoration: WwDecorations.card(),
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                ...rows.map(
                  (r) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 6),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(r.$1, style: WwText.bodyMedium(color: WwColors.textPrimary)),
                        _ScoreDots(value: r.$2),
                      ],
                    ),
                  ),
                ),
                const Divider(height: 24, color: WwColors.borderSubtle),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Food Pairing', style: WwText.bodyMedium(color: WwColors.textPrimary)),
                    Text(
                      _foodLabel,
                      style: WwText.bodyMedium(color: WwColors.violet)
                          .copyWith(fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Budget (per bottle)', style: WwText.bodyMedium(color: WwColors.textPrimary)),
                    Text(
                      _selectedBracket.label,
                      style: WwText.bodyMedium(color: WwColors.violet)
                          .copyWith(fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          if (_savedProfiles.length < PalatePrefs.maxProfiles)
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _showSaveProfileDialog,
                icon: const Icon(Icons.bookmark_add_outlined, size: 16),
                label: const Text('Save Profile'),
              ),
            )
          else
            Text(
              'Profile limit reached (${PalatePrefs.maxProfiles}/${PalatePrefs.maxProfiles}). Delete a profile to save a new one.',
              style: WwText.bodySmall(color: WwColors.textDisabled),
              textAlign: TextAlign.center,
            ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 9 — Results
  // ---------------------------------------------------------------------------

  Widget _buildResultsStep() {
    if (_loading) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(color: WwColors.violet),
            const SizedBox(height: 16),
            Text('Consulting the cellar…', style: WwText.bodyMedium()),
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
            Text(
              'Something went wrong:',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(_error!, style: WwText.bodyMedium(color: WwColors.error)),
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
          Text('Your Recommendations', style: WwText.headlineLarge()),
          const SizedBox(height: 4),
          Text(
            'Tap a card to see how each wine matches your palate.',
            style: WwText.bodyMedium(),
          ),
          const SizedBox(height: 16),
          ..._results!.asMap().entries.map((entry) {
            final rank = entry.key + 1;
            final wine = entry.value;
            return _WineResultCard(
              rank: rank,
              wine: wine,
              userPrefs: _userPrefs,
              attrOrder: _attrOrder,
              budgetMin: _selectedBracket.min,
              budgetMax: _selectedBracket.max,
              currencyCode: _currencyCode,
              prefDry: _prefDry,
            );
          }),
        ],
      ),
    );
  }

  Widget _stepShell({required Widget child}) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: child,
    );
  }
}

// ---------------------------------------------------------------------------
// Expandable wine result card
// ---------------------------------------------------------------------------

class _WineResultCard extends StatefulWidget {
  final int rank;
  final WineRecommendation wine;
  final Map<String, int> userPrefs;
  final List<String> attrOrder;
  final double budgetMin;
  final double budgetMax;
  final String currencyCode;
  final bool prefDry;

  const _WineResultCard({
    required this.rank,
    required this.wine,
    required this.userPrefs,
    required this.attrOrder,
    required this.budgetMin,
    required this.budgetMax,
    this.currencyCode = 'AUD',
    this.prefDry = false,
  });

  @override
  State<_WineResultCard> createState() => _WineResultCardState();
}

class _WineResultCardState extends State<_WineResultCard> {
  bool _expanded = false;
  List<BuyOption>? _buyOptions;
  bool _buyLoading = false;
  String? _buyError;

  Future<void> _loadBuyOptions() async {
    if (_buyOptions != null || _buyLoading) return;
    final varietal = widget.wine.varietal;
    if (varietal.isEmpty) return;
    setState(() { _buyLoading = true; _buyError = null; });
    try {
      final options = await ApiService().buyOptions(
        varietal: varietal,
        budgetMin: widget.budgetMin,
        budgetMax: widget.budgetMax,
      );
      if (mounted) setState(() { _buyOptions = options; _buyLoading = false; });
    } catch (e) {
      if (mounted) setState(() { _buyError = e.toString(); _buyLoading = false; });
    }
  }

  Color _rankColor() {
    return switch (widget.rank) {
      1 => WwColors.violet,
      2 => WwColors.textSecondary,
      3 => WwColors.violetMuted,
      _ => WwColors.borderMedium,
    };
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: WwDecorations.card(
        borderColor: widget.rank == 1 ? WwColors.violet : null,
      ).copyWith(
        border: widget.rank == 1
            ? Border.all(color: WwColors.violet, width: 1.5)
            : Border.all(color: WwColors.borderSubtle),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: () {
          setState(() => _expanded = !_expanded);
          if (_expanded) _loadBuyOptions();
        },
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // --- Header row ---
              Row(
                children: [
                  CircleAvatar(
                    radius: 20,
                    backgroundColor: _rankColor().withValues(alpha: 0.18),
                    child: Text(
                      '${widget.rank}',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 14,
                        color: _rankColor(),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                widget.wine.name,
                                style: WwText.headlineMedium(),
                              ),
                            ),
                            if (widget.rank == 1)
                              const Text('🍷', style: TextStyle(fontSize: 18)),
                          ],
                        ),
                        Text(
                          'Match: ${(widget.wine.score * 100).toStringAsFixed(1)}%',
                          style: WwText.bodySmall(color: WwColors.violetMuted),
                        ),
                      ],
                    ),
                  ),
                  Icon(
                    _expanded ? Icons.expand_less : Icons.expand_more,
                    color: WwColors.textSecondary,
                  ),
                ],
              ),

              // --- Expanded: attribute comparison + Find Nearby ---
              if (_expanded) ...[
                const SizedBox(height: 16),
                const Divider(height: 1),
                const SizedBox(height: 12),
                // Column headers
                Row(
                  children: [
                    const Expanded(child: SizedBox()),
                    Text(
                      'You',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: Colors.grey.shade500,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'Wine',
                      style: WwText.bodySmall(color: WwColors.violet)
                          .copyWith(fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                ...widget.attrOrder.map((attr) {
                  final userVal = widget.userPrefs[attr] ?? 3;
                  final wineVal = (widget.wine.wineProfile[attr] ?? 0)
                      .round()
                      .clamp(1, 5);
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 5),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            attr,
                            style: WwText.bodySmall(),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        _ScoreDots(value: userVal, color: WwColors.textDisabled),
                        const SizedBox(width: 8),
                        _ScoreDots(value: wineVal, color: WwColors.violet),
                      ],
                    ),
                  );
                }),
                const SizedBox(height: 14),
                const Divider(height: 1),
                const SizedBox(height: 12),
                Row(
                  children: [
                    const Text('🛒', style: TextStyle(fontSize: 16)),
                    const SizedBox(width: 6),
                    Text('Where to Buy', style: WwText.titleMedium()),
                  ],
                ),
                const SizedBox(height: 8),
                _WhereToBuySection(
                  buyLoading: _buyLoading,
                  buyError: _buyError,
                  buyOptions: _buyOptions,
                  varietal: widget.wine.varietal,
                  onRetry: _loadBuyOptions,
                ),
                if (widget.wine.varietal.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  const Divider(height: 1),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => WinePicksScreen(
                            varietal: widget.wine.varietal,
                            budgetMin: widget.budgetMin,
                            budgetMax: widget.budgetMax,
                            prefDry: widget.prefDry,
                          ),
                        ),
                      ),
                      icon: const Icon(Icons.wine_bar_outlined, size: 16),
                      label: const Text('View Wine Picks'),
                    ),
                  ),
                ],
              ],
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Where to Buy section (lazy-loaded inside wine result card)
// ---------------------------------------------------------------------------

class _WhereToBuySection extends StatelessWidget {
  final bool buyLoading;
  final String? buyError;
  final List<BuyOption>? buyOptions;
  final String varietal;
  final VoidCallback onRetry;

  const _WhereToBuySection({
    required this.buyLoading,
    required this.buyError,
    required this.buyOptions,
    required this.varietal,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    if (varietal.isEmpty) {
      return Text(
        'No varietal data — try a different recommendation.',
        style: WwText.bodySmall(color: WwColors.textDisabled),
      );
    }

    if (buyLoading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: Center(
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(strokeWidth: 2, color: WwColors.violet),
          ),
        ),
      );
    }

    if (buyError != null) {
      return Row(
        children: [
          Text(
            'Could not load listings.',
            style: WwText.bodySmall(color: WwColors.error),
          ),
          const SizedBox(width: 8),
          GestureDetector(
            onTap: onRetry,
            child: Text(
              'Retry',
              style: WwText.bodySmall(color: WwColors.violet)
                  .copyWith(decoration: TextDecoration.underline),
            ),
          ),
        ],
      );
    }

    if (buyOptions == null || buyOptions!.isEmpty) {
      return Text(
        'No listings found in our catalogue for $varietal.',
        style: WwText.bodySmall(color: WwColors.textDisabled),
      );
    }

    return Column(
      children: buyOptions!.map((opt) => _BuyOptionRow(option: opt)).toList(),
    );
  }
}

class _BuyOptionRow extends StatelessWidget {
  final BuyOption option;
  const _BuyOptionRow({required this.option});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  option.name,
                  style: WwText.bodySmall(),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                Row(
                  children: [
                    Text(
                      'A\$${option.price.toStringAsFixed(2)}',
                      style: WwText.bodySmall(color: WwColors.violet)
                          .copyWith(fontWeight: FontWeight.w600),
                    ),
                    if (option.priceIsStale) ...[
                      const SizedBox(width: 4),
                      Tooltip(
                        message: 'Price may be outdated',
                        child: Icon(Icons.schedule, size: 12, color: WwColors.textDisabled),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
          if (option.url.isNotEmpty)
            TextButton(
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                minimumSize: Size.zero,
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              onPressed: () async {
                final uri = Uri.tryParse(option.url);
                if (uri != null && await canLaunchUrl(uri)) {
                  await launchUrl(uri, mode: LaunchMode.externalApplication);
                }
              },
              child: Text(
                _retailerShortName(option.retailer),
                style: WwText.labelLarge(color: WwColors.violet),
              ),
            ),
        ],
      ),
    );
  }

  String _retailerShortName(String retailer) => switch (retailer) {
    'liquorland'     => 'Liquorland',
    'cellarbrations' => 'Cellarbrations',
    'danmurphys'     => "Dan Murphy's",
    _                => 'Buy',
  };
}

// ---------------------------------------------------------------------------
// Fox commentary bubble (food pairing step)
// ---------------------------------------------------------------------------

class _FoxComment extends StatelessWidget {
  final String text;
  const _FoxComment({super.key, required this.text});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: WwDecorations.witCallout(),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('🦊', style: TextStyle(fontSize: 22)),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text, style: WwText.witQuote()),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Food selection card
// ---------------------------------------------------------------------------

class _FoodCard extends StatelessWidget {
  final Map<String, String> option;
  final bool selected;
  final VoidCallback onTap;
  final bool fullWidth;

  const _FoodCard({
    required this.option,
    required this.selected,
    required this.onTap,
    this.fullWidth = false,
  });

  @override
  Widget build(BuildContext context) {
    final label = option['label']!;
    final emoji = option['emoji']!;

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        decoration: BoxDecoration(
          color: selected ? WwColors.bgElevated : WwColors.bgSurface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: selected ? WwColors.violet : WwColors.borderSubtle,
            width: selected ? 2 : 1,
          ),
          boxShadow: selected
              ? [
                  BoxShadow(
                    color: WwColors.violet.withValues(alpha: 0.15),
                    blurRadius: 10,
                    offset: const Offset(0, 2),
                  ),
                ]
              : [],
        ),
        padding: EdgeInsets.symmetric(
          horizontal: fullWidth ? 20 : 12,
          vertical: 14,
        ),
        child: fullWidth
            ? Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(emoji, style: const TextStyle(fontSize: 28)),
                  const SizedBox(width: 12),
                  Text(
                    label,
                    style: WwText.bodyMedium(
                      color: selected
                          ? WwColors.textPrimary
                          : WwColors.textSecondary,
                    ).copyWith(
                      fontWeight:
                          selected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ],
              )
            : Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(emoji, style: const TextStyle(fontSize: 30)),
                  const SizedBox(height: 8),
                  Text(
                    label,
                    textAlign: TextAlign.center,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: WwText.bodySmall(
                      color: selected
                          ? WwColors.textPrimary
                          : WwColors.textSecondary,
                    ).copyWith(
                      fontWeight:
                          selected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Score dot indicator
// ---------------------------------------------------------------------------

class _ScoreDots extends StatelessWidget {
  final int value;
  final Color? color;
  const _ScoreDots({required this.value, this.color});

  @override
  Widget build(BuildContext context) {
    final dotColor = color ?? WwColors.violet;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(5, (i) {
        return Container(
          margin: const EdgeInsets.only(left: 3),
          width: 9,
          height: 9,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: i < value ? dotColor : WwColors.borderMedium,
          ),
        );
      }),
    );
  }
}

// ---------------------------------------------------------------------------
// Pairing Philosophy binary card picker
// ---------------------------------------------------------------------------

class _PairingPhilosophyPicker extends StatelessWidget {
  final String value; // 'congruent' | 'contrast'
  final ValueChanged<String> onChanged;

  const _PairingPhilosophyPicker({
    required this.value,
    required this.onChanged,
  });

  static const _options = [
    (
      id: 'congruent',
      icon: '🎵',
      label: 'Harmonise',
      description: 'Find a wine that mirrors the dish — flavour meeting flavour.',
    ),
    (
      id: 'contrast',
      icon: '⚡',
      label: 'Contrast',
      description: 'Find a wine that challenges the dish — tension makes it sing.',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Pairing Philosophy', style: WwText.titleMedium()),
        const SizedBox(height: 4),
        Text(
          'Should your wine mirror the dish, or push back against it?',
          style: WwText.bodySmall(),
        ),
        const SizedBox(height: 14),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (int i = 0; i < _options.length; i++) ...[
              if (i > 0) const SizedBox(width: 10),
              Expanded(child: _PhilosophyCard(
                option: _options[i],
                selected: value == _options[i].id,
                onTap: () => onChanged(_options[i].id),
              )),
            ],
          ],
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Saved profile card (welcome screen)
// ---------------------------------------------------------------------------

class _ProfileCard extends StatelessWidget {
  final PalateProfile profile;
  final String foodLabel;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  const _ProfileCard({
    required this.profile,
    required this.foodLabel,
    required this.onTap,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final subtitle = profile.prefDry ? '$foodLabel · Dry' : foodLabel;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      decoration: WwDecorations.card(),
      child: ListTile(
        onTap: onTap,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        leading: const Icon(Icons.account_circle_outlined, color: WwColors.violet),
        title: Text(
          profile.name,
          style: WwText.bodyMedium(color: WwColors.textPrimary)
              .copyWith(fontWeight: FontWeight.w600),
        ),
        subtitle: Text(subtitle, style: WwText.bodySmall(color: WwColors.textSecondary)),
        trailing: IconButton(
          icon: const Icon(Icons.delete_outline, size: 18, color: WwColors.textDisabled),
          tooltip: 'Delete profile',
          onPressed: onDelete,
        ),
      ),
    );
  }
}

class _PhilosophyCard extends StatelessWidget {
  final ({String id, String icon, String label, String description}) option;
  final bool selected;
  final VoidCallback onTap;

  const _PhilosophyCard({
    required this.option,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
        padding: const EdgeInsets.fromLTRB(14, 16, 14, 16),
        decoration: BoxDecoration(
          color: selected ? WwColors.violetTint : WwColors.bgSurface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: selected ? WwColors.violet : WwColors.borderSubtle,
            width: selected ? 2 : 1,
          ),
          boxShadow: selected ? WwDecorations.violetGlow() : null,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Icon
            Text(option.icon, style: const TextStyle(fontSize: 30)),
            const SizedBox(height: 10),
            // Label
            Text(
              option.label,
              style: WwText.titleMedium(
                color: selected ? WwColors.violet : WwColors.textSecondary,
              ),
            ),
            const SizedBox(height: 6),
            // Description
            Text(
              option.description,
              style: WwText.bodySmall(
                color: selected
                    ? WwColors.textSecondary
                    : WwColors.textDisabled,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
