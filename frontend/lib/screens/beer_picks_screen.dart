import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/beer_picks.dart';
import '../services/api_service.dart';
import '../services/palate_prefs.dart';
import '../theme/app_theme.dart';

// Origin tiers (parallel to wine): Local Hero → The Interstater → The
// Internationalist. Reuses the shared tier palette.
const _beerTierColors = {
  1: WwColors.tierLocal,
  2: WwColors.tierNational,
  3: WwColors.tierGlobal,
};
const _beerTierIcons = {
  1: Icons.home_outlined,
  2: Icons.flag_outlined,
  3: Icons.public,
};

/// Beer drill-down: every buyable beer of a style with its retailer offers.
/// Beer analogue of WinePicksScreen, opened from the result card's
/// "View Recommendations" button.
class BeerPicksScreen extends StatefulWidget {
  final String style;
  final double budgetMin;
  final double budgetMax;
  final String? userState;
  final PalateSnapshot? snapshot; // current palate, for "Save to profile"
  const BeerPicksScreen({
    super.key,
    required this.style,
    this.budgetMin = 0.0,
    this.budgetMax = 99999.0,
    this.userState,
    this.snapshot,
  });

  @override
  State<BeerPicksScreen> createState() => _BeerPicksScreenState();
}

class _BeerPicksScreenState extends State<BeerPicksScreen> {
  BeerPicksResponse? _response;
  bool _loading = true;
  String? _error;
  List<PalateProfile> _profiles = [];

  @override
  void initState() {
    super.initState();
    _load();
    _loadProfiles();
  }

  Future<void> _loadProfiles() async {
    final profiles = await PalatePrefs.loadProfiles();
    if (mounted) setState(() => _profiles = profiles);
  }

  void _showSaveSheet(BeerPick pick) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => _BeerSaveToProfileSheet(
        beerName: pick.name,
        profiles: _profiles,
        snapshot: widget.snapshot,
        onSaveToProfile: (profile) async {
          Navigator.of(context).pop();
          await PalatePrefs.saveProfile(
            profile.name,
            profile.toSnapshot(),
            savedBeerName: pick.name,
          );
          await _loadProfiles();
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text('"${pick.name}" saved to ${profile.name}'),
            ));
          }
        },
        onCreateProfile: (name) async {
          Navigator.of(context).pop();
          if (widget.snapshot == null) return;
          final ok = await PalatePrefs.saveProfile(
            name,
            widget.snapshot!,
            savedBeerName: pick.name,
          );
          await _loadProfiles();
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text(ok
                  ? '"${pick.name}" saved to new profile "$name"'
                  : 'Profile limit reached — delete a profile first'),
            ));
          }
        },
      ),
    );
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await ApiService().beerPicks(
        style: widget.style,
        budgetMin: widget.budgetMin,
        budgetMax: widget.budgetMax,
        userState: widget.userState,
      );
      if (!mounted) return;
      setState(() {
        _response = response;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: WwColors.bgDeep,
      appBar: AppBar(
        title: Text(widget.style, style: WwText.headlineMedium()),
        centerTitle: true,
        backgroundColor: Colors.transparent,
        elevation: 0,
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const CircularProgressIndicator(color: WwColors.violet),
            const SizedBox(height: 16),
            Text('Finding the best pours…', style: WwText.bodyMedium()),
          ],
        ),
      );
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              SvgPicture.asset('assets/images/sage_fox_new_dark.svg', width: 72, height: 72),
              const SizedBox(height: 16),
              Text(
                "The Cellar Fox couldn't load these beers right now.",
                style: WwText.titleMedium(),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _load,
                icon: const Icon(Icons.refresh, size: 16),
                label: const Text('Try Again'),
              ),
            ],
          ),
        ),
      );
    }

    final picks = _response?.picks ?? [];

    if (picks.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text('🍺', style: TextStyle(fontSize: 48)),
              const SizedBox(height: 16),
              Text(
                'No ${widget.style} found in your budget '
                '(A\$${widget.budgetMin.toStringAsFixed(0)}–${widget.budgetMax.toStringAsFixed(0)} per drink).\n'
                'Try widening your budget on the previous step.',
                textAlign: TextAlign.center,
                style: WwText.bodyMedium(),
              ),
            ],
          ),
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: Text(
            picks.length == 1
                ? 'One ${widget.style} pick — matched to your taste.'
                : '${picks.length} ${widget.style} picks — local hero to global icon.',
            style: WwText.bodyMedium(),
            textAlign: TextAlign.center,
          ),
        ),
        for (final pick in picks)
          _BeerPickCard(pick: pick, onSave: () => _showSaveSheet(pick)),
        const SizedBox(height: 16),
        Text(
          'Please drink responsibly. CellarSage promotes responsible alcohol consumption.',
          textAlign: TextAlign.center,
          style: WwText.bodySmall(color: WwColors.textDisabled),
        ),
      ],
    );
  }
}

class _BeerPickCard extends StatelessWidget {
  final BeerPick pick;
  final VoidCallback? onSave;
  const _BeerPickCard({required this.pick, this.onSave});

  static String _retailerLabel(String retailer) => switch (retailer) {
        'liquorland' => 'Liquorland',
        'boozeit'    => 'Boozeit',
        _            => retailer.isNotEmpty ? retailer : 'retailer',
      };

  String get _effectiveUrl {
    if (pick.url.isNotEmpty) return pick.url;
    return switch (pick.retailer) {
      'liquorland' => 'https://www.liquorland.com.au/search?q=${Uri.encodeQueryComponent(pick.name)}',
      'boozeit'    => 'https://www.boozeit.com.au/search?q=${Uri.encodeQueryComponent(pick.name)}',
      _            => '',
    };
  }

  Future<void> _launch() async {
    final url = _effectiveUrl;
    if (url.isEmpty) return;
    final uri = Uri.tryParse(url);
    if (uri != null) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    final tierColor = _beerTierColors[pick.tier] ?? WwColors.tierNational;
    final tierIcon = _beerTierIcons[pick.tier] ?? Icons.flag_outlined;
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: WwDecorations.card(),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Origin tier strip
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: WwDecorations.tierHeader(tierColor),
            child: Row(
              children: [
                Icon(tierIcon, color: Colors.white, size: 15),
                const SizedBox(width: 8),
                Text(pick.tierLabel.toUpperCase(), style: WwText.badgeLabel()),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(child: Text(pick.name, style: WwText.headlineMedium())),
                    if (onSave != null)
                      IconButton(
                        onPressed: onSave,
                        icon: const Icon(Icons.bookmark_add_outlined, size: 20),
                        color: WwColors.violet,
                        tooltip: 'Save to profile',
                        visualDensity: VisualDensity.compact,
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                      ),
                  ],
                ),
            const SizedBox(height: 4),
            Text(
              '${pick.beerStyle}'
              '${pick.abvPercentage > 0 ? '  ·  ${pick.abvPercentage.toStringAsFixed(1)}% ABV' : ''}',
              style: WwText.bodySmall(),
            ),
            if (pick.untappdRating != null) ...[
              const SizedBox(height: 6),
              Row(
                children: [
                  const Icon(Icons.star_rounded, size: 15, color: Color(0xFFFFC000)),
                  const SizedBox(width: 4),
                  Text('${pick.untappdRating!.toStringAsFixed(2)}  ·  Untappd',
                      style: WwText.bodySmall()),
                  if (pick.highlyRated) ...[
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                      decoration: BoxDecoration(
                        color: WwColors.tierLocal.withValues(alpha: 0.18),
                        borderRadius: BorderRadius.circular(5),
                        border: Border.all(color: WwColors.tierLocal.withValues(alpha: 0.5)),
                      ),
                      child: Text('HIGHLY RATED',
                          style: WwText.badgeLabel().copyWith(
                            fontSize: 9,
                            color: const Color(0xFF4CAF82),
                            letterSpacing: 0.4,
                          )),
                    ),
                  ],
                ],
              ),
            ],
            const SizedBox(height: 12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text('A\$${pick.price.toStringAsFixed(2)}', style: WwText.priceHero()),
                if (pick.packageInfo.isNotEmpty) ...[
                  const SizedBox(width: 8),
                  Text(pick.packageInfo, style: WwText.bodySmall(color: WwColors.textSecondary)),
                ],
              ],
            ),
            if (pick.packCount > 1 && pick.unitPrice > 0) ...[
              const SizedBox(height: 2),
              Text(
                'A\$${pick.unitPrice.toStringAsFixed(2)} per drink',
                style: WwText.bodySmall(color: WwColors.violetMuted),
              ),
            ],
            const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton.icon(
                    onPressed: _launch,
                    icon: const Icon(Icons.open_in_new, size: 15),
                    label: Text('Buy on ${_retailerLabel(pick.retailer)}'),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Bottom sheet to save a beer to a named palate profile. Beer analogue of
/// wine's _SaveToProfileSheet — stores the beer name against the profile.
class _BeerSaveToProfileSheet extends StatefulWidget {
  final String beerName;
  final List<PalateProfile> profiles;
  final PalateSnapshot? snapshot;
  final void Function(PalateProfile) onSaveToProfile;
  final void Function(String name) onCreateProfile;

  const _BeerSaveToProfileSheet({
    required this.beerName,
    required this.profiles,
    required this.snapshot,
    required this.onSaveToProfile,
    required this.onCreateProfile,
  });

  @override
  State<_BeerSaveToProfileSheet> createState() => _BeerSaveToProfileSheetState();
}

class _BeerSaveToProfileSheetState extends State<_BeerSaveToProfileSheet> {
  bool _showCreate = false;
  final _nameCtrl = TextEditingController();

  @override
  void dispose() {
    _nameCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottomPad = MediaQuery.of(context).padding.bottom;
    final keyboardPad = MediaQuery.of(context).viewInsets.bottom;
    final canCreate = widget.snapshot != null &&
        widget.profiles.length < PalatePrefs.maxProfiles;

    return Container(
      decoration: const BoxDecoration(
        color: WwColors.bgElevated,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
        border: Border(top: BorderSide(color: WwColors.borderMedium)),
      ),
      padding: EdgeInsets.fromLTRB(24, 20, 24, 24 + bottomPad + keyboardPad),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Center(
            child: Container(
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: WwColors.borderMedium,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('Save to Profile', style: WwText.headlineMedium()),
          const SizedBox(height: 4),
          Text(
            widget.beerName,
            style: WwText.bodySmall(color: WwColors.textSecondary),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 20),
          if (widget.profiles.isEmpty || _showCreate) ...[
            if (widget.profiles.isEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Text(
                  "You don't have any profiles yet. Create one to save your picks.",
                  style: WwText.bodyMedium(),
                ),
              ),
            TextField(
              controller: _nameCtrl,
              autofocus: true,
              decoration: const InputDecoration(
                labelText: 'Profile name',
                hintText: 'e.g. Friday Night',
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: () {
                  final name = _nameCtrl.text.trim();
                  if (name.isNotEmpty) widget.onCreateProfile(name);
                },
                child: const Text('Create & Save'),
              ),
            ),
            if (_showCreate) ...[
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: TextButton(
                  onPressed: () => setState(() => _showCreate = false),
                  child: const Text('Back to profiles'),
                ),
              ),
            ],
          ] else ...[
            ...widget.profiles.map(
              (p) => ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(p.name, style: WwText.bodyMedium(color: WwColors.textPrimary)),
                subtitle: p.savedBeerName != null
                    ? Text('Saved: ${p.savedBeerName}', style: WwText.bodySmall())
                    : null,
                trailing: FilledButton(
                  onPressed: () => widget.onSaveToProfile(p),
                  child: const Text('Save'),
                ),
              ),
            ),
            if (canCreate) ...[
              const Divider(height: 24, color: WwColors.borderSubtle),
              SizedBox(
                width: double.infinity,
                child: OutlinedButton.icon(
                  onPressed: () => setState(() => _showCreate = true),
                  icon: const Icon(Icons.add, size: 16),
                  label: const Text('Create new profile'),
                ),
              ),
            ],
          ],
        ],
      ),
    );
  }
}
