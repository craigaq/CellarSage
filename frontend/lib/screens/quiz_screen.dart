import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/wine_recommendation.dart';
import '../models/beer_picks.dart';
import '../services/api_service.dart';
import '../services/location_service.dart';
import '../services/palate_prefs.dart';
import '../services/state_prefs.dart';
import '../screens/wine_picks_screen.dart';
import '../screens/beer_picks_screen.dart';
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
  int _crispness = 1;
  int _weight = 1;
  int _texture = 1;
  int _flavor = 1;
  String _foodPairing = 'none'; // stores the backend ID
  int _budgetIndex = 1; // index into CurrencyService.getBrackets()
  String _currencyCode = 'AUD'; // resolved from GPS in initState
  String? _userState; // AU state code resolved from GPS in initState
  double? _userLat;   // raw GPS lat — passed to geo-gated retailer filter
  double? _userLng;   // raw GPS lng
  bool _prefDry     = false;
  bool _prefOrganic = false;
  String _overrideMode = 'use_pairing_logic';
  String _pairingMode = 'congruent'; // 'congruent' | 'contrast' | 'brave'
  String _beverageType = 'wine'; // 'wine' | 'beer'
  final Set<String> _styleAnchors = {}; // beer styles the user already enjoys

  // Per-drink stock per beer budget band (aligned to getBeerBrackets), for
  // greying out empty options. Re-fetched when the style-anchor scope changes.
  List<int>? _beerBudgetCounts;
  String? _beerBudgetCountsKey;

  bool get _isBeer => _beverageType == 'beer';

  /// Beer style anchor chips shown on the welcome page in beer mode.
  static const List<Map<String, String>> _beerStyleOptions = [
    {'id': 'Lager', 'label': '🍺 Crisp Lager'},
    {'id': 'Pale Ale', 'label': '🍻 Pale Ale'},
    {'id': 'IPA', 'label': '🌲 Hoppy IPA'},
    {'id': 'Stout', 'label': '🌑 Dark & Roasty'},
    {'id': 'Wheat', 'label': '🍌 Wheat & Fruity'},
    {'id': 'Sour', 'label': '🍋 Sour & Tart'},
  ];

  // Style → typical dial profile [bitterness, body, carbonation, aroma] on the
  // 1-5 scale, mirroring the backend STYLE_TRAITS. Tapping a style chip
  // pre-fills the four beer dials from this (averaged across selected styles)
  // so the chip's effect is visible and the dials stay the single source of
  // truth — the backend no longer blends these axes behind the scenes.
  static const Map<String, List<int>> _beerStyleDialProfile = {
    'Lager':    [2, 3, 4, 2],
    'Pale Ale': [3, 3, 3, 3],
    'IPA':      [4, 3, 3, 4],
    'Stout':    [3, 4, 2, 2],
    'Wheat':    [2, 3, 4, 3],
    'Sour':     [1, 2, 4, 3],
  };

  /// Wine style anchor chips shown on the welcome page in wine mode — the
  /// parallel to the beer chips. A soft head-start (pre-fills the dials), NOT a
  /// filter: the user still gets recommendations across every varietal.
  /// Descriptive style names rather than grape names keep it discovery-friendly.
  static const List<Map<String, String>> _wineStyleOptions = [
    {'id': 'Crisp White', 'label': '🥂 Crisp White'},
    {'id': 'Rich White',  'label': '🧈 Rich White'},
    {'id': 'Rosé',        'label': '🌸 Rosé'},
    {'id': 'Light Red',   'label': '🍒 Light Red'},
    {'id': 'Bold Red',    'label': '🥩 Bold Red'},
  ];

  // Wine style → typical dial profile [acidity, body, tannin, flavour] on the
  // 1-5 scale. UI head-start only (the wine engine doesn't use style anchors),
  // so these ids stay descriptive and are never sent to the backend.
  static const Map<String, List<int>> _wineStyleDialProfile = {
    'Crisp White': [4, 2, 1, 3],
    'Rich White':  [3, 4, 1, 4],
    'Rosé':        [4, 2, 2, 3],
    'Light Red':   [4, 2, 2, 3],
    'Bold Red':    [3, 4, 4, 4],
  };

  /// Recompute the four dials as the rounded average of the currently selected
  /// style chips. No-op when nothing is selected (dials stay put). Uses the
  /// beverage-appropriate profile map; the dial state vars are shared (beer
  /// reads them as bitterness/body/carbonation/aroma, wine as
  /// acidity/body/tannin/flavour), so the positional mapping is identical.
  void _applyStyleAnchorsToDials() {
    if (_styleAnchors.isEmpty) return;
    final profileMap = _isBeer ? _beerStyleDialProfile : _wineStyleDialProfile;
    final profiles =
        _styleAnchors.map((id) => profileMap[id]).whereType<List<int>>().toList();
    if (profiles.isEmpty) return;
    int avg(int i) =>
        (profiles.map((p) => p[i]).reduce((a, b) => a + b) / profiles.length).round().clamp(1, 5);
    setState(() {
      _crispness = avg(0); // beer: bitterness · wine: acidity
      _weight    = avg(1); // body
      _texture   = avg(2); // beer: carbonation · wine: tannin
      _flavor    = avg(3); // beer: aroma · wine: flavour
    });
  }

  /// "Drink a style already?" chips on the welcome page — a soft head-start that
  /// pre-fills the dials from a recognisable style. Single-select. Shared by
  /// beer and wine; pass the beverage-appropriate options.
  Widget _buildStyleAnchorSection(List<Map<String, String>> options) {
    return Column(
      children: [
        Text(
          'Drink a style already? Tap it for a head start — (optional)',
          style: WwText.bodySmall(color: WwColors.textSecondary),
          textAlign: TextAlign.center,
        ),
        Text(
          "We'll set your dials to match; tweak them on the next steps.",
          style: WwText.bodySmall(color: WwColors.textDisabled),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          alignment: WrapAlignment.center,
          children: options.map((style) {
            final id = style['id']!;
            final selected = _styleAnchors.contains(id);
            return GestureDetector(
              onTap: () {
                // Single-select: a chip pre-fills the dials to ONE coherent
                // style profile. Tapping selects only that style (replacing any
                // previous); tapping it again clears it. Averaging two styles
                // would produce a blend that matches neither.
                setState(() {
                  _styleAnchors.clear();
                  if (!selected) _styleAnchors.add(id);
                });
                _applyStyleAnchorsToDials();
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: selected
                      ? WwColors.violet.withValues(alpha: 0.15)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: selected ? WwColors.violet : WwColors.borderMedium,
                  ),
                ),
                child: Text(
                  style['label']!,
                  style: WwText.bodySmall(
                    color: selected ? WwColors.violet : WwColors.textSecondary,
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }

  // --- Results state ---
  List<WineRecommendation>? _results;
  bool _loading = false;
  String? _error;
  ConflictAlert? _conflictAlert;
  int _fetchGeneration = 0;
  int _selectedResultIndex = 0; // which of the top-3 varietal tabs is active

  // --- Saved profiles ---
  List<PalateProfile> _savedProfiles = [];
  PalateProfile? _loadedProfile; // non-null when user launched from a saved profile card

  // Pages: 0 welcome · 1-4 dials · 5 food · 6 pairing philosophy · 7 budget
  //        · 8 summary · 9 results. Philosophy (6) is skipped when food=='none'.
  static const int _totalPages = 10;
  static const int _kFoodPage    = 5;
  static const int _kPhiloPage   = 6;
  static const int _kBudgetPage  = 7;
  static const int _kSummaryPage = 8;

  /// Each entry: label = UI text, id = backend key, emoji = grid icon,
  /// comment = fox commentary shown when the item is selected.
  static const List<Map<String, String>> _foodOptions = [
    {
      'label': 'Steak, Lamb, or Burgers',
      'id': 'red_meat',
      'emoji': '🥩',
      'comment': "Find a wine with grip to handle the richness.",
      'contrast_comment': "Find a bright, acid-driven wine to cut through the fat.",
      'brave_comment': "Let the Cellar Fox decide what pairs best here.",
    },
    {
      'label': 'Chicken, Turkey, or Pork',
      'id': 'poultry',
      'emoji': '🍗',
      'comment': "Find a wine that echoes this pairing.",
      'contrast_comment': "Find a richer wine to frame the delicacy.",
      'brave_comment': "Let the Cellar Fox decide what works here.",
    },
    {
      'label': 'White Fish or Shellfish',
      'id': 'white_fish',
      'emoji': '🐟',
      'comment': "Find a crisp wine that won't drown the fish.",
      'contrast_comment': "Find a textured wine to frame the delicacy.",
      'brave_comment': "Let the Cellar Fox decide what pairs best here.",
    },
    {
      'label': 'Salmon or Tuna',
      'id': 'rich_fish',
      'emoji': '🍣',
      'comment': "Find a wine with acidity to cut through richness.",
      'contrast_comment': "Find a full-bodied wine to match salmon's weight.",
      'brave_comment': "Let the Cellar Fox decide what works here.",
    },
    {
      'label': 'Spicy Curry or Tacos',
      'id': 'spicy_food',
      'emoji': '🌶️',
      'comment': "Find something fruity to cool the heat.",
      'contrast_comment': "Find something bold to amplify the fire.",
      'brave_comment': "Let the Cellar Fox decide what pairs best here.",
    },
    {
      'label': 'Tomato Pasta or Pizza',
      'id': 'tomato_sauce',
      'emoji': '🍕',
      'comment': "Find a wine with punch to keep up.",
      'contrast_comment': "Find a smooth wine to soften the tang.",
      'brave_comment': "Let the Cellar Fox decide what works here.",
    },
    {
      'label': 'Creamy or Cheesy Pasta',
      'id': 'creamy_sauce',
      'emoji': '🧀',
      'comment': "Find a heavyweight to match the richness.",
      'contrast_comment': "Find a sharp, high-acid wine to cut through.",
      'brave_comment': "Let the Cellar Fox decide what pairs best here.",
    },
    {
      'label': 'Salads or Green Veggies',
      'id': 'greens',
      'emoji': '🥗',
      'comment': "Find a crisp wine like a summer garden.",
      'contrast_comment': "Find an earthy wine to complement the greens.",
      'brave_comment': "Let the Cellar Fox decide what works here.",
    },
    {
      'label': 'Smoked BBQ or Grilled Meats',
      'id': 'smoked_bbq',
      'emoji': '🔥',
      'comment': "Find a bold, smoky red to match the char.",
      'contrast_comment': "Find a bright wine to cut through the sweetness and smoke.",
      'brave_comment': "Let the Cellar Fox decide what pairs best here.",
    },
    {
      'label': 'Mushrooms, Root Veg or Legumes',
      'id': 'earthy_veg',
      'emoji': '🍄',
      'comment': "Find an earthy wine to echo the roots and mushrooms.",
      'contrast_comment': "Find a crisp aromatic white to lift the earthiness.",
      'brave_comment': "Let the Cellar Fox decide what works here.",
    },
    {
      'label': 'Cheese & Charcuterie',
      'id': 'charcuterie',
      'emoji': '🍖',
      'comment': "Find a crowd-pleaser for the whole board.",
      'contrast_comment': "Find a punchy, high-acid wine to cut through.",
      'brave_comment': "Let the Cellar Fox decide what pairs best here.",
    },
    {
      'label': 'Dessert or Sweet Treats',
      'id': 'dessert',
      'emoji': '🍰',
      'comment': "Find something luscious to mirror the sweetness.",
      'contrast_comment': "Find a sharp wine to slice through the sweetness.",
      'brave_comment': "Let the Cellar Fox decide what works here.",
    },
    {
      'label': 'Just sipping (No food)',
      'id': 'none',
      'emoji': '🍷',
      'comment': "Let's find a wine that shines all on its own.",
      'contrast_comment': "Let's find a wine that shines all on its own.",
      'brave_comment': "Let's find a wine that shines all on its own.",
    },
  ];

  static const List<String> _wineAttrOrder = [
    'Crispness (Acidity)',
    'Weight (Body)',
    'Texture (Tannin)',
    'Flavor Intensity (Aromatics)',
  ];

  // Beer mode re-labels the four palate dials along Cicerone axes:
  // bitterness (IBU), body, carbonation, hop/flavour intensity.
  static const List<String> _beerAttrOrder = [
    'Bitterness',
    'Weight (Body)',
    'Carbonation (Fizz)',
    'Aroma',
  ];

  List<String> get _attrOrder => _isBeer ? _beerAttrOrder : _wineAttrOrder;

  // Beer budgets are per-drink (unit_price); wine budgets are per-bottle.
  List<BudgetBracket> get _budgetBrackets =>
      _isBeer ? CurrencyService.getBeerBrackets() : CurrencyService.getBrackets(_currencyCode);

  BudgetBracket get _selectedBracket => _budgetBrackets[_budgetIndex];

  /// Fetch per-band beer stock for greying out empty budget options. Scoped to
  /// the style anchor when exactly one is set, else the whole catalog. Idempotent
  /// per scope — safe to call on every budget-step build.
  void _ensureBeerBudgetCounts() {
    if (!_isBeer) return;
    final scope = _styleAnchors.length == 1 ? _styleAnchors.first : null;
    final key = scope ?? '*';
    if (_beerBudgetCountsKey == key) return; // already loaded/loading for this scope
    _beerBudgetCountsKey = key;
    // Upper edges of every band except the open-ended last one → "3,4,5,7".
    final brackets = CurrencyService.getBeerBrackets();
    final edges = brackets.take(brackets.length - 1).map((b) => b.max.toStringAsFixed(0)).join(',');
    ApiService().beerBudgetAvailability(edges: edges, style: scope).then((counts) {
      if (!mounted) return;
      setState(() {
        _beerBudgetCounts = counts;
        // If the current selection landed on an empty band, hop to the first
        // band with stock so the user never proceeds into a dead budget.
        if (_budgetIndex < counts.length && counts[_budgetIndex] == 0) {
          final firstStocked = counts.indexWhere((c) => c > 0);
          if (firstStocked != -1) _budgetIndex = firstStocked;
        }
      });
    }).catchError((_) {
      // Network/none — leave counts null so all bands stay enabled (fail open).
      if (mounted) setState(() => _beerBudgetCounts = null);
    });
  }

  String get _foodLabel =>
      _foodOptions.firstWhere((f) => f['id'] == _foodPairing)['label'] ??
      _foodPairing;

  String? get _foodComment {
    final option = _foodOptions.firstWhere(
      (f) => f['id'] == _foodPairing,
      orElse: () => {},
    );
    if (option.isEmpty) return null;
    final comment = switch (_pairingMode) {
      'contrast' => option['contrast_comment'] ?? option['comment'],
      'brave' => option['brave_comment'] ?? option['comment'],
      _ => option['comment'],
    };
    // Food comments are written for wine; swap the word in beer mode.
    return _isBeer ? comment?.replaceAll('wine', 'beer') : comment;
  }

  Map<String, int> get _userPrefs => {
    _attrOrder[0]: _crispness,
    _attrOrder[1]: _weight,
    _attrOrder[2]: _texture,
    _attrOrder[3]: _flavor,
  };

  // ---------------------------------------------------------------------------
  // Navigation
  // ---------------------------------------------------------------------------

  Future<void> _goNext() async {
    // Food page → check for gastro clash before advancing.
    // Wine only: the clash rules + Palate Paradox are wine concepts (acidity,
    // tannin, dry preference) and would surface wine terminology/advice in
    // beer mode. The beer engine handles food interactions in its own scoring.
    if (_currentPage == _kFoodPage && _foodPairing != 'none' && !_isBeer) {
      await _checkAndHandlePairingClash();
    }
    if (_currentPage == _kSummaryPage) {
      _fetchResults();
    }
    // No food selected → the Pairing Philosophy page is meaningless, skip it.
    if (_currentPage == _kFoodPage && _foodPairing == 'none') {
      _controller.animateToPage(
        _kBudgetPage,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
      return;
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
    } catch (e) {
      debugPrint('[checkPairing] skipped — $e');
    }
  }

  void _goBack() {
    // Budget page with no food → skip back over the hidden Philosophy page.
    if (_currentPage == _kBudgetPage && _foodPairing == 'none') {
      _controller.animateToPage(
        _kFoodPage,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeInOut,
      );
      return;
    }
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
      _crispness = 1;
      _weight = 1;
      _texture = 1;
      _flavor = 1;
      _foodPairing = 'none';
      _budgetIndex = 1;
      _prefDry     = false;
      _prefOrganic = false;
      _overrideMode = 'use_pairing_logic';
      _pairingMode = 'congruent';
      _results = null;
      _loading = false;
      _error = null;
      _conflictAlert = null;
      _loadedProfile = null;
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

  // Non-destructive: return to the welcome page (where the Saved Profiles list
  // lives) without resetting the current session, unlike Start Over.
  void _goToProfiles() {
    _controller.animateToPage(
      0,
      duration: const Duration(milliseconds: 400),
      curve: Curves.easeInOut,
    );
  }

  Future<void> _refreshProfiles() async {
    final profiles = await PalatePrefs.loadProfiles();
    if (mounted) setState(() => _savedProfiles = profiles);
  }

  void _loadProfileAndJump(PalateProfile profile) {
    setState(() {
      _crispness    = profile.crispness;
      _weight       = profile.weight;
      _texture      = profile.texture;
      _flavor       = profile.flavor;
      _foodPairing  = profile.foodPairing;
      _budgetIndex  = profile.budgetIndex;
      _prefDry      = profile.prefDry;
      _overrideMode = 'use_pairing_logic';
      _pairingMode  = 'congruent';
      _loadedProfile = profile;
    });
    _controller.animateToPage(
      _kSummaryPage, // jump straight here so user sees the full profile
      duration: const Duration(milliseconds: 400),
      curve: Curves.easeInOut,
    );
  }

  String _suggestProfileName() {
    final existing = _savedProfiles.map((p) => p.name).toSet();
    if (!existing.contains('My Profile')) return 'My Profile';
    int n = 2;
    while (existing.contains('My Profile $n')) {
      n++;
    }
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
    setState(() {
      _loading = true;
      _error = null;
      _results = null;
      _conflictAlert = null;
    });
    try {
      if (_beverageType == 'beer') {
        final result = await ApiService().recommendBeer(
          crispnessAcidity: _crispness,
          weightBody: _weight,
          textureTannin: _texture,
          flavorIntensity: _flavor,
          foodPairing: _foodPairing,
          prefDry: _prefDry,
          overrideMode: _overrideMode,
          pairingMode: _pairingMode,
          styleAnchors: _styleAnchors.toList(),
        );
        if (generation != _fetchGeneration || !mounted) return;
        // Mirror the wine flow's varietal-level results: group ranked beers
        // by STYLE (Amber Ale, IPA, …). The style becomes the recommendation;
        // the individual beers of that style become its "Top Picks" list —
        // the beer equivalent of wine's varietal → bottles drill-down.
        final styleOrder = <String>[];
        final byStyle = <String, List<BeerRecommendation>>{};
        for (final beer in result.recommendations) {
          if (!byStyle.containsKey(beer.beerStyle)) {
            styleOrder.add(beer.beerStyle);
            byStyle[beer.beerStyle] = [];
          }
          byStyle[beer.beerStyle]!.add(beer);
        }
        final wineResults = styleOrder.map((style) {
          final beers = byStyle[style]!;
          final top = beers.first; // best-scoring beer of this style
          return WineRecommendation(
            name: style,
            skuId: top.skuId,
            score: top.score,
            attributeScores: top.attributeScores,
            wineProfile: {
              _beerAttrOrder[0]: top.beerProfile['Bitterness'] ?? 3.0,
              _beerAttrOrder[1]: top.beerProfile['Weight'] ?? 3.0,
              _beerAttrOrder[2]: top.beerProfile['Carbonation'] ?? 3.0,
              _beerAttrOrder[3]: top.beerProfile['Flavor Intensity'] ?? 3.0,
            },
            rawMetrics: {
              'varietal': style,
              'beer_style': style,
              'pairing_explanation': top.pairingExplanation,
              'flavor_tags': top.flavorTags,
              // Where-to-Buy + View Recommendations both lazy-load from
              // /beer-picks (by style + budget) so they stay consistent —
              // no per-recommendation offers baked in here anymore.
            },
          );
        }).toList();
        setState(() {
          _results = wineResults;
          _loading = false;
          _selectedResultIndex = 0;
        });
      } else {
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
          _selectedResultIndex = 0;
        });
        // Palate conflict alert (shown after results load)
        if (result.alert != null && mounted) {
          await showConflictAlert(
            context,
            result.alert!,
            _applyConflictAdjustment,
          );
        }
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
    // Last-known / manually-chosen state first, so "Local Hero" works even
    // before (or without) a live GPS fix.
    StatePrefs.load().then((saved) {
      if (saved != null && mounted && _userState == null) {
        setState(() => _userState = saved);
      }
    });
    CurrencyService.detectCodeFromGps().then((code) {
      if (mounted) setState(() => _currencyCode = code);
      // State detection runs after currency so permission is already granted.
      // Only overwrite (and persist) when GPS actually resolves a state —
      // never clobber a saved/manual value with null.
      CurrencyService.detectAustralianStateFromGps().then((state) {
        if (state != null && mounted) {
          setState(() => _userState = state);
          StatePrefs.save(state);
        }
      });
      // Also capture raw lat/lng for geo-gated retailer filtering.
      LocationService().getCurrentPosition().then((pos) {
        if (mounted) setState(() { _userLat = pos.latitude; _userLng = pos.longitude; });
      }).catchError((_) {});
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
            child: (_currentPage >= 1 && _currentPage <= _kBudgetPage)
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
                  title: _attrOrder[0],
                  description: _isBeer
                      ? 'Smooth and malty, or a proper hoppy bite?'
                      : 'How much do you enjoy a fresh, zesty bite in your wine?',
                  value: _crispness,
                  onChanged: (v) => setState(() => _crispness = v),
                ),
                _buildAttributeStep(
                  title: _attrOrder[1],
                  description: _isBeer
                      ? 'An easy, light session beer or a rich, full-bodied pour?'
                      : 'A light, delicate sip or a rich, full-bodied experience?',
                  value: _weight,
                  onChanged: (v) => setState(() => _weight = v),
                ),
                _buildAttributeStep(
                  title: _attrOrder[2],
                  description: _isBeer
                      ? 'Velvety smooth, or lively scrubbing bubbles?'
                      : 'Do you like that dry, grippy sensation common in red wines?',
                  value: _texture,
                  onChanged: (v) => setState(() => _texture = v),
                ),
                _buildAttributeStep(
                  title: _attrOrder[3],
                  description: _isBeer
                      ? 'Clean and understated, or bursting with hop aroma?'
                      : 'Do you prefer subtle, understated flavors or bold, expressive ones?',
                  value: _flavor,
                  onChanged: (v) => setState(() => _flavor = v),
                ),
                _buildFoodPairingStep(),
                _buildPairingPhilosophyStep(),
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
                  SizedBox(
                    width: _currentPage == _kSummaryPage ? 170 : null,
                    child: FilledButton.icon(
                      onPressed: _goNext,
                      label: Text(_currentPage == _kSummaryPage
                          ? (_isBeer ? 'Find My Beer!' : 'Find My Wine!')
                          : 'Next'),
                      icon: const Icon(Icons.arrow_forward),
                      iconAlignment: IconAlignment.end,
                    ),
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
            if (_currentPage >= 4 && _currentPage <= _kBudgetPage) ...[
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
            // Results screen — save the palate that produced these matches, and
            // jump to the saved profiles list (tester request; wine + beer).
            if (_currentPage == _totalPages - 1) ...[
              const SizedBox(height: 4),
              Wrap(
                alignment: WrapAlignment.center,
                spacing: 8,
                children: [
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
                  if (_savedProfiles.isNotEmpty)
                    TextButton.icon(
                      onPressed: _goToProfiles,
                      icon: const Icon(Icons.bookmarks_outlined, size: 14),
                      label: const Text('My Profiles'),
                      style: TextButton.styleFrom(
                        foregroundColor: WwColors.violetMuted,
                        textStyle: WwText.bodySmall(),
                      ),
                    ),
                ],
              ),
            ],
            if (_currentPage == _kSummaryPage && _loadedProfile != null) ...[
              const SizedBox(height: 4),
              TextButton.icon(
                onPressed: _startOver,
                icon: const Icon(Icons.refresh, size: 14),
                label: const Text('Start Over'),
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
          Text(
            'Welcome to\nCellar Sage',
            style: WwText.displayLarge(),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 16),
          Text(
            'Answer 7 quick questions about your palate and we\'ll find ${_beverageType == 'wine' ? 'wines' : 'beers'} that actually match how you think.',
            style: WwText.bodyLarge(color: WwColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 32),
          // Beverage toggle
          Container(
            decoration: BoxDecoration(
              border: Border.all(color: WwColors.borderMedium),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() {
                      _beverageType = 'wine';
                      _styleAnchors.clear(); // avoid carrying a beer anchor into wine
                    }),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      decoration: BoxDecoration(
                        color: _beverageType == 'wine'
                          ? WwColors.violet.withValues(alpha: 0.1)
                          : Colors.transparent,
                        borderRadius: const BorderRadius.only(
                          topLeft: Radius.circular(12),
                          bottomLeft: Radius.circular(12),
                        ),
                      ),
                      child: Text(
                        '🍷 Wine',
                        style: WwText.bodyMedium(
                          color: _beverageType == 'wine'
                            ? WwColors.violet
                            : WwColors.textSecondary,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
                ),
                Container(width: 1, color: WwColors.borderMedium),
                Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() {
                      _beverageType = 'beer';
                      _styleAnchors.clear(); // avoid carrying a wine anchor into beer
                    }),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      decoration: BoxDecoration(
                        color: _beverageType == 'beer'
                          ? WwColors.violet.withValues(alpha: 0.1)
                          : Colors.transparent,
                        borderRadius: const BorderRadius.only(
                          topRight: Radius.circular(12),
                          bottomRight: Radius.circular(12),
                        ),
                      ),
                      child: Text(
                        '🍺 Beer',
                        style: WwText.bodyMedium(
                          color: _beverageType == 'beer'
                            ? WwColors.violet
                            : WwColors.textSecondary,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 32),
          // Style anchors — a soft head-start that pre-fills the dials. Shown
          // for both beverages (beer styles vs wine styles).
          _buildStyleAnchorSection(_isBeer ? _beerStyleOptions : _wineStyleOptions),
          const SizedBox(height: 24),
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
          // Wine-only preference toggles — dry drives the Palate Paradox and
          // organic filters the wine catalog; neither applies to beer.
          if (!_isBeer) ...[
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
            const SizedBox(height: 8),
            Card(
              child: SwitchListTile(
                secondary: const Text('🌿', style: TextStyle(fontSize: 22)),
                title: const Text('I prefer organic wines'),
                subtitle: const Text('Organic & preservative-free where possible, best available otherwise'),
                value: _prefOrganic,
                onChanged: (v) => setState(() => _prefOrganic = v),
              ),
            ),
            const SizedBox(height: 12),
          ],

          // "Just sipping" sits directly below the dry-wine toggle
          _FoodCard(
            // "Just sipping" shows the beverage emoji — swap to beer in beer mode.
            option: _isBeer ? {...soloOption, 'emoji': '🍺'} : soloOption,
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

          // Fox commentary — immediate feedback on the food choice.
          // (Pairing Philosophy now lives on its own page — see
          // _buildPairingPhilosophyStep — so this important lever isn't
          // buried below the food grid.)
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
  // Step 6 — Pairing Philosophy (only shown when a food is chosen)
  // ---------------------------------------------------------------------------

  Widget _buildPairingPhilosophyStep() {
    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Pairing Philosophy', style: WwText.headlineLarge()),
          const SizedBox(height: 8),
          Text(
            'How should your ${_isBeer ? 'beer' : 'wine'} play against ${_foodLabel.toLowerCase()}?',
            style: WwText.bodyMedium(),
          ),
          const SizedBox(height: 20),
          _PairingPhilosophyPicker(
            value: _pairingMode,
            onChanged: (v) => setState(() => _pairingMode = v),
            isBeer: _isBeer,
          ),
          const SizedBox(height: 16),
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 300),
            transitionBuilder: (child, animation) =>
                FadeTransition(opacity: animation, child: child),
            child: _foodComment != null
                ? _FoxComment(
                    key: ValueKey('philo:$_foodPairing:$_pairingMode'),
                    text: _foodComment!,
                  )
                : const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 7 — Budget
  // ---------------------------------------------------------------------------

  // "My Saved Wines/Beers" — a tappable list on a loaded profile. Each item
  // opens its varietal/style picks so the user can see details & where to buy.
  // Legacy saves (no ref) render as plain, non-tappable rows.
  Widget _savedDrinksSection(IconData icon, String label,
      List<SavedDrink> items, void Function(SavedDrink) onOpen) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Divider(height: 16, color: WwColors.borderSubtle),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 4),
          child: Row(
            children: [
              Icon(icon, size: 16, color: WwColors.violetMuted),
              const SizedBox(width: 8),
              Text(label, style: WwText.bodyMedium(color: WwColors.textPrimary)),
            ],
          ),
        ),
        ...items.map((d) {
          final tappable = d.ref.isNotEmpty;
          return InkWell(
            onTap: tappable ? () => onOpen(d) : null,
            borderRadius: BorderRadius.circular(8),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      d.name,
                      style: WwText.bodyMedium(color: WwColors.violet)
                          .copyWith(fontWeight: FontWeight.w600),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  if (tappable)
                    const Icon(Icons.chevron_right,
                        size: 18, color: WwColors.violetMuted),
                ],
              ),
            ),
          );
        }),
      ],
    );
  }

  void _openSavedWine(SavedDrink d) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => WinePicksScreen(
          varietal: d.ref,
          budgetMin: 0,
          budgetMax: 99999,
          userState: _userState,
          snapshot: _loadedProfile?.toSnapshot(),
        ),
      ),
    );
  }

  void _openSavedBeer(SavedDrink d) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => BeerPicksScreen(
          style: d.ref,
          budgetMin: 0,
          budgetMax: 99999,
          userState: _userState,
          snapshot: _loadedProfile?.toSnapshot(),
        ),
      ),
    );
  }

  Widget _buildBudgetStep() {
    if (_isBeer) _ensureBeerBudgetCounts();
    final counts = _isBeer ? _beerBudgetCounts : null;
    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_isBeer ? 'Your Budget (per drink)' : 'Your Budget (per bottle)',
              style: WwText.headlineLarge()),
          const SizedBox(height: 8),
          Text(
            _isBeer && _styleAnchors.length == 1
                ? 'Stock shown for ${_styleAnchors.first}. Greyed bands have none.'
                : 'The Cellar Fox respects all budgets. Even the modest ones.',
            style: WwText.bodyMedium(),
          ),
          const SizedBox(height: 32),
          Column(
            children: _budgetBrackets
                .asMap()
                .entries
                .map((entry) {
                  final index = entry.key;
                  final bracket = entry.value;
                  final label = bracket.label;
                  final selected = _budgetIndex == index;
                  final count = (counts != null && index < counts.length)
                      ? counts[index]
                      : null;
                  final disabled = count == 0; // empty band — grey out
                  return GestureDetector(
                    onTap: disabled
                        ? null
                        : () => setState(() => _budgetIndex = index),
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
                      child: Opacity(
                        opacity: disabled ? 0.4 : 1.0,
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
                                  color: WwColors.violet)
                            else if (count != null)
                              Text(
                                disabled ? 'None' : '$count',
                                style: WwText.bodySmall(
                                    color: WwColors.textDisabled),
                              ),
                          ],
                        ),
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
    // Rows in quiz-step order: dial 1 → dial 4. Labels follow the beverage —
    // beer mode re-purposes the acidity dial as bitterness and tannin as fizz.
    final activeAxis = const {1: 0, 2: 1, 3: 2, 4: 3}[_currentPage];
    final axisNames = _isBeer
        ? const ['Bitterness', 'Body', 'Fizz', 'Aroma']
        : const ['Acidity', 'Body', 'Tannin', 'Flavour'];
    final axisValues = [_crispness, _weight, _texture, _flavor];

    return Container(
      decoration: BoxDecoration(
        color: WwColors.bgDeep,
        border: Border(bottom: BorderSide(color: WwColors.borderSubtle, width: 1)),
      ),
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(4, (i) {
                final isActive = activeAxis == i;
                final val = axisValues[i];
                final barColor = isActive ? WwColors.violet : WwColors.textSecondary;
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 96,
                        child: Text(
                          axisNames[i],
                          maxLines: 1,
                          overflow: TextOverflow.visible,
                          softWrap: false,
                          style: WwText.bodySmall(
                            color: isActive ? WwColors.violet : WwColors.textSecondary,
                          ).copyWith(
                            fontWeight: isActive ? FontWeight.w700 : FontWeight.normal,
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Row(
                          children: List.generate(5, (j) {
                            final filled = j < val;
                            return Expanded(
                              child: Padding(
                                padding: const EdgeInsets.symmetric(horizontal: 1.5),
                                child: Container(
                                  height: 7,
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(4),
                                    color: filled
                                        ? barColor.withValues(alpha: isActive ? 1.0 : 0.5)
                                        : WwColors.borderSubtle,
                                  ),
                                ),
                              ),
                            );
                          }),
                        ),
                      ),
                      const SizedBox(width: 8),
                      SizedBox(
                        width: 14,
                        child: Text(
                          '$val',
                          textAlign: TextAlign.right,
                          style: WwText.bodySmall(
                            color: isActive ? WwColors.violet : WwColors.textSecondary,
                          ).copyWith(fontWeight: FontWeight.w700),
                        ),
                      ),
                    ],
                  ),
                );
              }),
            ),
          ),
          const SizedBox.shrink(),
        ],
      ),
    );
  }

  // ---------------------------------------------------------------------------
  // Step 7 — Summary (was Step 8; standalone Palate Dial step removed)
  // ---------------------------------------------------------------------------

  void _jumpToPage(int page) {
    _controller.animateToPage(
      page,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeInOut,
    );
  }

  Widget _summaryRow({
    required String label,
    required Widget trailing,
    required int targetPage,
  }) {
    return InkWell(
      onTap: () => _jumpToPage(targetPage),
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Text(label, style: WwText.bodyMedium(color: WwColors.textPrimary)),
            ),
            const SizedBox(width: 8),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 180),
              child: trailing,
            ),
            const SizedBox(width: 6),
            const Icon(Icons.edit_outlined, size: 14, color: WwColors.textDisabled),
          ],
        ),
      ),
    );
  }

  Widget _buildSummaryStep() {
    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_loadedProfile != null) ...[
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: WwColors.violet.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: WwColors.violet.withValues(alpha: 0.3)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.account_circle_outlined, size: 14, color: WwColors.violet),
                  const SizedBox(width: 6),
                  Text(
                    _loadedProfile!.name,
                    style: WwText.bodySmall(color: WwColors.violet)
                        .copyWith(fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
          ],
          Text('Your Profile', style: WwText.headlineLarge()),
          const SizedBox(height: 8),
          Text(
            'Looking good. Hit "Find My ${_isBeer ? 'Beer' : 'Wine'}!" when you\'re ready.',
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
                labels: _isBeer
                    ? const [
                        'Bitterness',
                        'Weight\n(Body)',
                        'Aroma',
                        'Carbonation\n(Fizz)',
                      ]
                    : null,
              ),
            ),
          ),
          const SizedBox(height: 40),
          Container(
            decoration: WwDecorations.card(),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Column(
              children: [
                _summaryRow(
                  label: _attrOrder[0],
                  trailing: _ScoreDots(value: _crispness),
                  targetPage: 1,
                ),
                _summaryRow(
                  label: _attrOrder[1],
                  trailing: _ScoreDots(value: _weight),
                  targetPage: 2,
                ),
                _summaryRow(
                  label: _attrOrder[2],
                  trailing: _ScoreDots(value: _texture),
                  targetPage: 3,
                ),
                _summaryRow(
                  label: _attrOrder[3],
                  trailing: _ScoreDots(value: _flavor),
                  targetPage: 4,
                ),
                const Divider(height: 16, color: WwColors.borderSubtle),
                _summaryRow(
                  label: 'Food Pairing',
                  trailing: Text(
                    _foodLabel,
                    style: WwText.bodyMedium(color: WwColors.violet)
                        .copyWith(fontWeight: FontWeight.w600),
                    textAlign: TextAlign.right,
                  ),
                  targetPage: _kFoodPage,
                ),
                if (_foodPairing != 'none')
                  _summaryRow(
                    label: 'Pairing Style',
                    trailing: Text(
                      switch (_pairingMode) {
                        'contrast' => 'Contrast',
                        'brave' => "I'm Brave",
                        _ => 'Harmonise',
                      },
                      style: WwText.bodyMedium(color: WwColors.violet)
                          .copyWith(fontWeight: FontWeight.w600),
                    ),
                    targetPage: _kPhiloPage,
                  ),
                _summaryRow(
                  label: _isBeer ? 'Budget (per drink)' : 'Budget (per bottle)',
                  trailing: Text(
                    _selectedBracket.label,
                    style: WwText.bodyMedium(color: WwColors.violet)
                        .copyWith(fontWeight: FontWeight.w600),
                  ),
                  targetPage: _kBudgetPage,
                ),
                // Region — drives the "Local Hero" tier. Auto-detected from GPS
                // (and remembered), but settable here so it works without a fix.
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 2, horizontal: 4),
                  child: Row(
                    children: [
                      Expanded(child: Text('Local picks for', style: WwText.bodyMedium())),
                      DropdownButton<String>(
                        value: _userState,
                        hint: Text('Set state',
                            style: WwText.bodyMedium(color: WwColors.violet)
                                .copyWith(fontWeight: FontWeight.w600)),
                        underline: const SizedBox.shrink(),
                        dropdownColor: WwColors.bgElevated,
                        isDense: true,
                        items: [
                          for (final s in StatePrefs.auStates)
                            DropdownMenuItem(
                              value: s,
                              child: Text(s,
                                  style: WwText.bodyMedium(color: WwColors.violet)
                                      .copyWith(fontWeight: FontWeight.w600)),
                            ),
                        ],
                        onChanged: (v) {
                          if (v != null) {
                            setState(() => _userState = v);
                            StatePrefs.save(v);
                          }
                        },
                      ),
                    ],
                  ),
                ),
                if (_loadedProfile != null && _loadedProfile!.savedWines.isNotEmpty)
                  _savedDrinksSection(Icons.wine_bar_outlined, 'My Saved Wines',
                      _loadedProfile!.savedWines, _openSavedWine),
                if (_loadedProfile != null && _loadedProfile!.savedBeers.isNotEmpty)
                  _savedDrinksSection(Icons.sports_bar_outlined, 'My Saved Beers',
                      _loadedProfile!.savedBeers, _openSavedBeer),
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

    // Top 3 varietals for the carousel tabs; remaining shown below as weaker matches.
    final top3   = _results!.take(3).toList();
    final others = _results!.skip(3).toList();
    final idx    = _selectedResultIndex.clamp(0, top3.length - 1);
    final sel    = top3[idx];

    // Detect near-tie: show note when #1 and #2 are within 5% of each other.
    final nearTie = top3.length >= 2 &&
        (top3[0].score - top3[1].score).abs() / top3[0].score < 0.05;

    Widget card(WineRecommendation wine, int rank) => _WineResultCard(
      key: ValueKey(wine.varietal),
      rank: rank,
      wine: wine,
      userPrefs: _userPrefs,
      attrOrder: _attrOrder,
      budgetMin: _selectedBracket.min,
      budgetMax: _selectedBracket.max,
      currencyCode: _currencyCode,
      prefDry: _prefDry,
      prefOrganic: _prefOrganic,
      userState: _userState,
      userLat: _userLat,
      userLng: _userLng,
      foodPairing: _foodPairing,
      pairingMode: _pairingMode,
      isBeer: _isBeer,
      snapshot: PalateSnapshot(
        crispness:   _crispness,
        weight:      _weight,
        texture:     _texture,
        flavor:      _flavor,
        foodPairing: _foodPairing,
        budgetIndex: _budgetIndex,
        prefDry:     _prefDry,
      ),
    );

    return _stepShell(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Your Top Matches', style: WwText.headlineLarge()),
          const SizedBox(height: 4),
          Text(
            'The Cellar Fox found your top ${top3.length} ${_isBeer ? 'beer styles' : 'varietals'}. Tap to explore each.',
            style: WwText.bodyMedium(),
          ),
          if (nearTie) ...[
            const SizedBox(height: 6),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: WwColors.violet.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SvgPicture.asset('assets/images/sage_fox_new_dark.svg', width: 36, height: 36),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Very close call — #1 and #2 are nearly tied. Both worth exploring.',
                      style: WwText.bodySmall(color: WwColors.violet),
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 14),

          // ── Varietal tab chips ──────────────────────────────────────────
          Row(
            children: [
              for (int i = 0; i < top3.length; i++) ...[
                if (i > 0) const SizedBox(width: 8),
                Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() => _selectedResultIndex = i),
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
                      decoration: BoxDecoration(
                        color: i == idx ? WwColors.violet : WwColors.bgSurface,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(
                          color: i == idx ? WwColors.violet : WwColors.borderSubtle,
                          width: 1.5,
                        ),
                      ),
                      child: Column(
                        children: [
                          Text(
                            '#${i + 1}',
                            style: WwText.bodySmall(
                              color: i == idx ? Colors.black : WwColors.textSecondary,
                            ).copyWith(fontWeight: FontWeight.w700),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            top3[i].name,
                            textAlign: TextAlign.center,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: WwText.bodySmall(
                              color: i == idx ? Colors.black : WwColors.textPrimary,
                            ).copyWith(fontSize: 11, fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            '${(top3[i].score * 100).round()}%',
                            style: WwText.bodySmall(
                              color: i == idx
                                  ? Colors.black.withValues(alpha: 0.75)
                                  : WwColors.textSecondary,
                            ).copyWith(fontSize: 10),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),

          const SizedBox(height: 16),

          // ── Selected varietal card ──────────────────────────────────────
          card(sel, idx + 1),

          // ── Other varietals (weaker matches) ───────────────────────────
          if (others.isNotEmpty) ...[
            Padding(
              padding: const EdgeInsets.only(top: 16, bottom: 12),
              child: Row(
                children: [
                  Expanded(child: Divider(color: WwColors.textDisabled.withValues(alpha: 0.4))),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: Text('Other matches', style: WwText.bodySmall(color: WwColors.textDisabled)),
                  ),
                  Expanded(child: Divider(color: WwColors.textDisabled.withValues(alpha: 0.4))),
                ],
              ),
            ),
            for (int i = 0; i < others.length; i++) card(others[i], top3.length + i + 1),
          ],
        ],
      ),
    );
  }

  Widget _stepShell({required Widget child}) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
      child: child,
    );
  }
}

// ---------------------------------------------------------------------------
// Expandable wine result card
// ---------------------------------------------------------------------------

String _beerRetailerLabel(String retailer) => switch (retailer) {
      'liquorland' => 'Liquorland',
      'boozeit'    => 'Boozeit',
      _            => retailer.isNotEmpty ? retailer : 'retailer',
    };

class _WineResultCard extends StatefulWidget {
  final int rank;
  final WineRecommendation wine;
  final Map<String, int> userPrefs;
  final List<String> attrOrder;
  final PalateSnapshot? snapshot;
  final double budgetMin;
  final double budgetMax;
  final String currencyCode;
  final bool prefDry;
  final bool prefOrganic;
  final String? userState;
  final double? userLat;
  final double? userLng;
  final String foodPairing;
  final String pairingMode;
  final bool isBeer;

  const _WineResultCard({
    super.key,
    required this.rank,
    required this.wine,
    required this.userPrefs,
    required this.attrOrder,
    required this.budgetMin,
    required this.budgetMax,
    this.currencyCode = 'AUD',
    this.prefDry = false,
    this.prefOrganic = false,
    this.userState,
    this.userLat,
    this.userLng,
    this.snapshot,
    this.foodPairing = 'none',
    this.pairingMode = 'congruent',
    this.isBeer = false,
  });

  static String _foodLabel(String id) => switch (id) {
    'red_meat'     => 'red meat',
    'poultry'      => 'chicken',
    'white_fish'   => 'white fish',
    'rich_fish'    => 'salmon',
    'spicy_food'   => 'spicy food',
    'tomato_sauce' => 'tomato pasta',
    'creamy_sauce' => 'creamy pasta',
    'greens'       => 'salad',
    'charcuterie'  => 'the cheese board',
    'dessert'      => 'dessert',
    _              => 'the dish',
  };

  static String whyThisPick({
    required WineRecommendation wine,
    required Map<String, int> userPrefs,
    required String foodPairing,
    required String pairingMode,
  }) {
    // Beer results carry a Cicerone pairing explanation from the backend —
    // use it verbatim rather than the wine-attribute heuristics below.
    final beerWhy = wine.rawMetrics['pairing_explanation'] as String?;
    if (beerWhy != null && beerWhy.isNotEmpty) return beerWhy;

    if (wine.attributeScores.isEmpty) return '';

    final topAttr = wine.attributeScores.entries
        .reduce((a, b) => a.value > b.value ? a : b)
        .key;

    final wineVal = (wine.wineProfile[topAttr] ?? 3.0).round().clamp(1, 5);
    final bool high    = wineVal >= 4;
    final bool low     = wineVal <= 2;
    final bool hasFood = foodPairing != 'none';
    final bool contrast = pairingMode == 'contrast';
    final String food  = _foodLabel(foodPairing);

    return switch (topAttr) {
      'Crispness (Acidity)' => hasFood && contrast
          ? "Its bright acidity cuts right through the $food — a classic sommelier move."
          : hasFood && high
              ? "Its crisp, zesty finish is exactly what the $food needs."
              : hasFood && low
                  ? "Its soft, rounded finish sits gently alongside the $food."
                  : high
                      ? "Its lively, mouth-watering crispness lines up perfectly with your palate."
                      : "Its gentle, rounded finish matches your preference for a softer style.",

      'Weight (Body)' => hasFood && contrast && high
          ? "Its full, rich weight pushes back against the lighter character of $food — bold contrast on the plate."
          : hasFood && contrast && !high
              ? "Its lighter frame creates a refreshing contrast against the richness of $food."
              : hasFood && high
                  ? "Its rich, full weight is built to match the heartiness of $food."
                  : hasFood && low
                      ? "Its delicate body won't overwhelm the $food."
                      : high
                          ? "Its full, generous body matches exactly how you like your wine to feel."
                          : "Its light, elegant weight lines up with your preference for a delicate style.",

      'Texture (Tannin)' => hasFood && contrast && high
          ? "Its firm, structured grip pushes back against the richness of $food — tension that makes the whole thing better."
          : hasFood && contrast && !high
              ? "Its smooth, gripless texture provides a silky contrast to the intensity of $food."
              : hasFood && high
                  ? "Its firm, structured texture is built to cut through the fat of $food."
                  : hasFood && low
                      ? "Its silky-smooth texture won't get in the way of the $food."
                      : high
                          ? "Its firm grip matches your taste for a wine with real structure."
                          : "Its silky-smooth texture matches your preference for a soft, easy-drinking style.",

      _ => hasFood && contrast
          ? "Its powerful aromatics push back against the $food — this wine leads the pairing, not the dish."
          : hasFood && high
              ? "Its bold, aromatic personality mirrors the big flavours of $food."
              : hasFood && low
                  ? "Its subtle character lets the $food do the talking."
                  : high
                      ? "Its bold, expressive character matches your love of wines that make a statement."
                      : "Its subtle, refined character matches your preference for understated elegance.",
    };
  }

  @override
  State<_WineResultCard> createState() => _WineResultCardState();
}

class _WineResultCardState extends State<_WineResultCard> {
  bool _expanded = false;
  List<BuyOption>? _buyOptions;
  bool _buyLoading = false;
  String? _buyError;

  // Beer "Where to Buy" — uses the same /beer-picks source as the
  // "View Recommendations" screen so the two are always consistent (the old
  // approach filtered representative packs and could empty out while View
  // Recommendations still found in-budget offers).
  List<BeerPick>? _beerPicks;
  bool _beerPicksLoading = false;
  String? _beerPicksError;

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
        userLat: widget.userLat,
        userLng: widget.userLng,
      );
      if (mounted) setState(() { _buyOptions = options; _buyLoading = false; });
    } catch (e) {
      if (mounted) setState(() { _buyError = e.toString(); _buyLoading = false; });
    }
  }

  Future<void> _loadBeerPicks() async {
    if (_beerPicks != null || _beerPicksLoading) return;
    final style = widget.wine.varietal; // carries the beer style
    if (style.isEmpty) return;
    setState(() { _beerPicksLoading = true; _beerPicksError = null; });
    try {
      final resp = await ApiService().beerPicks(
        style: style,
        budgetMin: widget.budgetMin,
        budgetMax: widget.budgetMax,
        userState: widget.userState,
        mode: 'all', // Where to Buy lists every buyable offer
      );
      if (mounted) setState(() { _beerPicks = resp.picks; _beerPicksLoading = false; });
    } catch (e) {
      if (mounted) setState(() { _beerPicksError = e.toString(); _beerPicksLoading = false; });
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
          if (_expanded) {
            widget.isBeer ? _loadBeerPicks() : _loadBuyOptions();
          }
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
                              const Text('🎯', style: TextStyle(fontSize: 18)),
                          ],
                        ),
                        Text(
                          'Match: ${(widget.wine.score.clamp(0.0, 1.0) * 100).toStringAsFixed(1)}%',
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
                // Column headers — aligned over their respective dot columns
                Row(
                  children: [
                    const Expanded(child: SizedBox()),
                    SizedBox(
                      width: 60,
                      child: Text(
                        'You',
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: Colors.white,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 60,
                      child: Text(
                        widget.isBeer ? 'Beer' : 'Wine',
                        textAlign: TextAlign.center,
                        style: WwText.bodySmall(color: WwColors.violet)
                            .copyWith(fontWeight: FontWeight.w600),
                      ),
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
                        _ScoreDots(value: userVal, color: Colors.white),
                        const SizedBox(width: 8),
                        _ScoreDots(value: wineVal, color: WwColors.violet),
                      ],
                    ),
                  );
                }),
                // Why this pick callout
                Builder(builder: (_) {
                  final why = _WineResultCard.whyThisPick(
                    wine: widget.wine,
                    userPrefs: widget.userPrefs,
                    foodPairing: widget.foodPairing,
                    pairingMode: widget.pairingMode,
                  );
                  if (why.isEmpty) return const SizedBox.shrink();
                  return Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      decoration: BoxDecoration(
                        color: WwColors.violet.withValues(alpha: 0.08),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: WwColors.violet.withValues(alpha: 0.22),
                        ),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SvgPicture.asset(
                            'assets/images/sage_fox_new_dark.svg',
                            width: 18,
                            height: 18,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              why,
                              style: WwText.bodySmall(
                                color: WwColors.textSecondary,
                              ).copyWith(fontStyle: FontStyle.italic),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }),
                // Wine-only: varietal explorer + retailer listings. Beer mode
                // has no merchant offers yet (MVP) — hide to avoid dead ends.
                if (!widget.isBeer && widget.wine.varietal.isNotEmpty) ...[
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
                            prefOrganic: widget.prefOrganic,
                            userState: widget.userState,
                            snapshot: widget.snapshot,
                          ),
                        ),
                      ),
                      icon: const Icon(Icons.wine_bar_outlined, size: 16),
                      label: const Text('View Recommendations'),
                    ),
                  ),
                ],
                if (!widget.isBeer) ...[
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
                ] else ...[
                  // Beer mirrors wine: a "View Recommendations" drill-down to
                  // all beers of this style, then a "Where to Buy" list with
                  // the retailer named beside each listing.
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (_) => BeerPicksScreen(
                            style: widget.wine.varietal,
                            budgetMin: widget.budgetMin,
                            budgetMax: widget.budgetMax,
                            userState: widget.userState,
                            snapshot: widget.snapshot,
                          ),
                        ),
                      ),
                      icon: const Icon(Icons.sports_bar_outlined, size: 16),
                      label: const Text('View Recommendations'),
                    ),
                  ),
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
                  _BeerWhereToBuy(
                    loading: _beerPicksLoading,
                    error: _beerPicksError,
                    picks: _beerPicks,
                    budgetMin: widget.budgetMin,
                    budgetMax: widget.budgetMax,
                    onRetry: _loadBeerPicks,
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
// Beer "Where to Buy" — lazy-loaded from /beer-picks (same source as the
// View Recommendations screen, so the two are always consistent)
// ---------------------------------------------------------------------------

class _BeerWhereToBuy extends StatelessWidget {
  final bool loading;
  final String? error;
  final List<BeerPick>? picks;
  final double budgetMin;
  final double budgetMax;
  final VoidCallback onRetry;

  const _BeerWhereToBuy({
    required this.loading,
    required this.error,
    required this.picks,
    required this.budgetMin,
    required this.budgetMax,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    if (loading) {
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

    if (error != null) {
      return Row(
        children: [
          Text('Could not load listings.', style: WwText.bodySmall(color: WwColors.error)),
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

    final list = picks ?? const [];
    if (list.isEmpty) {
      return Text(
        'No listings in your A\$${budgetMin.toStringAsFixed(0)}–${budgetMax.toStringAsFixed(0)} '
        'per-drink budget. Tap "View Recommendations" or widen your budget.',
        style: WwText.bodySmall(color: WwColors.textDisabled),
      );
    }

    return Column(
      children: list.take(5).map((p) {
        final pkg = p.packageInfo;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: p.url.isEmpty
              ? null
              : () => launchUrl(Uri.parse(p.url), mode: LaunchMode.externalApplication),
          child: Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        p.name,
                        style: WwText.bodySmall(),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      Text(
                        'A\$${p.price.toStringAsFixed(2)}${pkg.isNotEmpty ? '  ·  $pkg' : ''}',
                        style: WwText.bodySmall(color: WwColors.violet)
                            .copyWith(fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ),
                Text(
                  _beerRetailerLabel(p.retailer),
                  style: WwText.labelLarge(
                    color: p.url.isEmpty ? WwColors.textDisabled : WwColors.violet,
                  ),
                ),
              ],
            ),
          ),
        );
      }).toList(),
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

  String get _effectiveUrl {
    if (option.url.isNotEmpty) return option.url;
    return switch (option.retailer) {
      'liquorland'     => 'https://www.liquorland.com.au/search?q=${Uri.encodeQueryComponent(option.name)}',
      'cellarbrations' => 'https://www.cellarbrations.com.au/results?q=wine',
      _                => '',
    };
  }

  Future<void> _launch() async {
    final url = _effectiveUrl;
    if (url.isEmpty) return;
    final uri = Uri.tryParse(url);
    if (uri != null && await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    final canLaunch = _effectiveUrl.isNotEmpty;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: _launch,
      child: Padding(
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
            Text(
              _retailerShortName(option.retailer),
              style: WwText.labelLarge(
                color: canLaunch ? WwColors.violet : WwColors.textDisabled,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _retailerShortName(String retailer) => switch (retailer) {
    'liquorland'             => 'Liquorland',
    'cellarbrations'         => 'Cellarbrations',
    'cellarbrations_sunbury' => 'Cellarbrations',
    'danmurphys'             => "Dan Murphy's",
    'laithwaites'            => 'Laithwaites',
    'portersliquor'          => 'Porters Liquor',
    'bottleo'                => 'The Bottle-O',
    'boozeit'                => 'Boozeit',
    _                        => 'Buy',
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
          SvgPicture.asset('assets/images/sage_fox_new_dark.svg', width: 32, height: 32),
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
  final String value; // 'congruent' | 'contrast' | 'brave'
  final ValueChanged<String> onChanged;
  final bool isBeer;

  const _PairingPhilosophyPicker({
    required this.value,
    required this.onChanged,
    this.isBeer = false,
  });

  static const _options = [
    (
      id: 'congruent',
      icon: '🤝',
      label: 'Harmonise',
      description: 'Attempt to mirror the dish.',
    ),
    (
      id: 'contrast',
      icon: '⚡',
      label: 'Contrast',
      description: 'Challenge the dish - tension makes it sing!',
    ),
  ];

  static const braveOption = (
    id: 'brave',
    icon: '🙏',
    label: "I'm Brave",
    description: "Let the Cellar Fox decide. Your palate steps aside — the food picks the wine.",
  );

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Pairing Philosophy', style: WwText.titleMedium()),
        const SizedBox(height: 10),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (int i = 0; i < _options.length; i++) ...[
              if (i > 0) const SizedBox(width: 10),
              Expanded(child: _PhilosophyCard(
                option: _options[i],
                selected: value == _options[i].id,
                onTap: () => onChanged(_options[i].id),
                compact: true,
              )),
            ],
          ],
        ),
        const SizedBox(height: 10),
        _PhilosophyCard(
          option: isBeer
              ? (
                  id: braveOption.id,
                  icon: braveOption.icon,
                  label: braveOption.label,
                  description:
                      "Let the Cellar Fox decide. Your palate steps aside — the food picks the beer.",
                )
              : braveOption,
          selected: value == braveOption.id,
          onTap: () => onChanged(braveOption.id),
          fullWidth: true,
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
    final subtitleText = profile.prefDry ? '$foodLabel · Dry' : foodLabel;
    final wineCount = profile.savedWines.length;
    final beerCount = profile.savedBeers.length;

    Widget savedRow(IconData icon, String text) => Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Row(
            children: [
              Icon(icon, size: 12, color: WwColors.violetMuted),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  text,
                  style: WwText.bodySmall(color: WwColors.violetMuted),
                  overflow: TextOverflow.ellipsis,
                  maxLines: 1,
                ),
              ),
            ],
          ),
        );

    // Card shows a saved-count summary; the tappable list lives on the profile.
    final subtitleWidget = (wineCount > 0 || beerCount > 0)
        ? Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(subtitleText, style: WwText.bodySmall(color: WwColors.textSecondary)),
              if (wineCount > 0)
                savedRow(Icons.wine_bar_outlined,
                    '$wineCount saved wine${wineCount == 1 ? '' : 's'}'),
              if (beerCount > 0)
                savedRow(Icons.sports_bar_outlined,
                    '$beerCount saved beer${beerCount == 1 ? '' : 's'}'),
            ],
          )
        : Text(subtitleText, style: WwText.bodySmall(color: WwColors.textSecondary));

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
        subtitle: subtitleWidget,
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
  final bool fullWidth;
  final bool compact;

  const _PhilosophyCard({
    required this.option,
    required this.selected,
    required this.onTap,
    this.fullWidth = false,
    this.compact = false,
  });

  static TextStyle _titleStyle(bool selected) => WwText.bodySmall().copyWith(
        fontSize: 13,
        fontWeight: FontWeight.w600,
        color: selected ? WwColors.violet : WwColors.textSecondary,
      );

  @override
  Widget build(BuildContext context) {
    final content = fullWidth
        ? Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Text(option.icon, style: const TextStyle(fontSize: 20)),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(option.label, style: _titleStyle(selected)),
                    const SizedBox(height: 3),
                    Text(
                      option.description,
                      style: WwText.bodySmall(
                        color: selected ? WwColors.textSecondary : WwColors.textDisabled,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          )
        : compact
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(option.icon, style: const TextStyle(fontSize: 15)),
                  const SizedBox(height: 4),
                  Text(option.label, style: _titleStyle(selected)),
                  const SizedBox(height: 3),
                  Text(
                    option.description,
                    style: WwText.bodySmall(
                      color: selected ? WwColors.textSecondary : WwColors.textDisabled,
                    ),
                  ),
                ],
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(option.icon, style: const TextStyle(fontSize: 30)),
                  const SizedBox(height: 10),
                  Text(option.label, style: _titleStyle(selected)),
                  const SizedBox(height: 6),
                  Text(
                    option.description,
                    style: WwText.bodySmall(
                      color: selected ? WwColors.textSecondary : WwColors.textDisabled,
                    ),
                  ),
                ],
              );

    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
        width: fullWidth ? double.infinity : null,
        padding: fullWidth
            ? const EdgeInsets.symmetric(horizontal: 10, vertical: 10)
            : compact
                ? const EdgeInsets.symmetric(horizontal: 12, vertical: 10)
                : const EdgeInsets.fromLTRB(14, 16, 14, 16),
        decoration: BoxDecoration(
          color: selected ? WwColors.violetTint : WwColors.bgSurface,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: selected ? WwColors.violet : WwColors.borderSubtle,
            width: selected ? 2 : 1,
          ),
          boxShadow: selected ? WwDecorations.violetGlow() : null,
        ),
        child: content,
      ),
    );
  }
}
