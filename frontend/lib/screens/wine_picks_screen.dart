import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/wine_picks.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

const _tierColors = {
  1: WwColors.tierLocal,
  2: WwColors.tierNational,
  3: WwColors.tierGlobal,
  4: WwColors.tierDeal,
};

const _tierIcons = {
  1: Icons.home_outlined,
  2: Icons.flag_outlined,
  3: Icons.public,
  4: Icons.local_offer_outlined,
};

class WinePicksScreen extends StatefulWidget {
  final String varietal;
  final double budgetMin;
  final double budgetMax;
  final bool prefDry;
  final String? userState;

  const WinePicksScreen({
    super.key,
    required this.varietal,
    this.budgetMin = 0.0,
    this.budgetMax = 9999.0,
    this.prefDry = false,
    this.userState,
  });

  @override
  State<WinePicksScreen> createState() => _WinePicksScreenState();
}

class _WinePicksScreenState extends State<WinePicksScreen> {
  WinePicksResponse? _response;
  bool _loading = true;
  String? _error;
  int _loadGeneration = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final generation = ++_loadGeneration;
    setState(() {
      _loading = true;
      _error   = null;
    });
    try {
      final response = await ApiService().winePicks(
        varietal: widget.varietal,
        budgetMin: widget.budgetMin,
        budgetMax: widget.budgetMax,
        prefDry: widget.prefDry,
        userState: widget.userState,
      );
      if (generation != _loadGeneration || !mounted) return;
      setState(() { _response = response; _loading = false; });
    } catch (e) {
      if (generation != _loadGeneration || !mounted) return;
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: WwColors.bgDeep,
      appBar: AppBar(
        title: Text(
          widget.varietal,
          style: WwText.headlineMedium(),
        ),
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
            Text('Finding the best picks…', style: WwText.bodyMedium()),
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
              const Text('🦊', style: TextStyle(fontSize: 48)),
              const SizedBox(height: 16),
              Text(
                'The Cellar Fox couldn\'t find picks right now.',
                style: WwText.titleMedium(),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(_error!, textAlign: TextAlign.center, style: WwText.bodySmall()),
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
              const Text('😬', style: TextStyle(fontSize: 48)),
              const SizedBox(height: 16),
              Text(
                'No ${widget.varietal} listings found right now.',
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
                ? 'One pick for your palate.'
                : '${picks.length} picks — one for every palate.',
            style: WwText.bodyMedium(),
            textAlign: TextAlign.center,
          ),
        ),
        for (final pick in picks) _PickCard(pick: pick),
      ],
    );
  }
}

class _PickCard extends StatelessWidget {
  final WinePick pick;
  const _PickCard({required this.pick});

  @override
  Widget build(BuildContext context) {
    final color = _tierColors[pick.tier] ?? WwColors.violetMuted;
    final icon  = _tierIcons[pick.tier]  ?? Icons.wine_bar_outlined;
    final origin = _originLabel(pick);

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: WwDecorations.card(),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Tier header strip
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: WwDecorations.tierHeader(color),
            child: Row(
              children: [
                Icon(icon, color: Colors.white, size: 15),
                const SizedBox(width: 8),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      pick.tierLabel.toUpperCase(),
                      style: WwText.badgeLabel(),
                    ),
                    if (pick.tier == 4)
                      Text(
                        'Lowest price found',
                        style: WwText.badgeLabel().copyWith(
                          fontSize: 9,
                          fontWeight: FontWeight.w400,
                          color: Colors.white70,
                        ),
                      ),
                  ],
                ),
              ],
            ),
          ),

          // Card body
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(pick.name, style: WwText.headlineMedium()),
                if (origin.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(origin, style: WwText.bodySmall()),
                ],
                if (pick.isSagePick) ...[
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: WwColors.violetMuted.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(5),
                      border: Border.all(color: WwColors.violetMuted.withValues(alpha: 0.4)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.auto_awesome, size: 11, color: WwColors.violetMuted),
                        const SizedBox(width: 4),
                        Text(
                          'Cellar Sage Pick',
                          style: WwText.badgeLabel().copyWith(
                            fontSize: 10,
                            color: WwColors.violetMuted,
                            letterSpacing: 0.3,
                          ),
                        ),
                      ],
                    ),
                  ),
                ] else if (pick.vivinoRating != null || pick.rating != null) ...[
                  const SizedBox(height: 6),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      const Icon(Icons.star_rounded, size: 14, color: Color(0xFFFFCC00)),
                      const SizedBox(width: 4),
                      if (pick.vivinoRating != null) ...[
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '${pick.vivinoRating!.toStringAsFixed(1)}  ·  ${pick.vivinoReviewCount} reviews',
                                style: WwText.bodySmall(),
                              ),
                              Text(
                                'Community data via Vivino',
                                style: WwText.bodySmall().copyWith(
                                  color: WwColors.textDisabled,
                                  fontSize: 10,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ] else ...[
                        Text(
                          '${pick.rating!.toStringAsFixed(1)}  ·  ${pick.reviewCount} review${pick.reviewCount == 1 ? '' : 's'}',
                          style: WwText.bodySmall(),
                        ),
                      ],
                    ],
                  ),
                ],
                if (pick.isHighlyVerified) ...[
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1A5C2A).withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(5),
                      border: Border.all(
                        color: const Color(0xFF1A5C2A).withValues(alpha: 0.35),
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.workspace_premium, size: 11, color: Color(0xFF2E7D32)),
                        const SizedBox(width: 4),
                        Text(
                          'Expert + Community Verified',
                          style: WwText.badgeLabel().copyWith(
                            fontSize: 10,
                            color: const Color(0xFF2E7D32),
                            letterSpacing: 0.3,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                if (pick.criticScore != null) ...[
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: const Color(0xFF8B1A1A).withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(5),
                      border: Border.all(
                        color: const Color(0xFF8B1A1A).withValues(alpha: 0.35),
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.verified_outlined, size: 11, color: Color(0xFFC0392B)),
                        const SizedBox(width: 4),
                        Text(
                          '${pick.criticScore!.toStringAsFixed(0)} pts · Wine Enthusiast',
                          style: WwText.badgeLabel().copyWith(
                            fontSize: 10,
                            color: const Color(0xFFC0392B),
                            letterSpacing: 0.3,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 12),
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Text(
                      'A\$${pick.price.toStringAsFixed(2)}',
                      style: WwText.priceHero(),
                    ),
                    if (pick.isMemberPrice) ...[
                      const SizedBox(width: 8),
                      Tooltip(
                        message: 'Members price — sign up free at ${_retailerLabel(pick.retailer)}',
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: WwColors.violet.withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: WwColors.violet.withValues(alpha: 0.4)),
                          ),
                          child: Text(
                            'MEMBERS',
                            style: WwText.badgeLabel().copyWith(
                              fontSize: 8,
                              color: WwColors.violet,
                              letterSpacing: 0.6,
                            ),
                          ),
                        ),
                      ),
                    ],
                    if (pick.priceIsStale) ...[
                      const SizedBox(width: 6),
                      Tooltip(
                        message: 'Price may be outdated — check retailer for current pricing',
                        child: Icon(Icons.schedule, size: 14, color: WwColors.textDisabled),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: pick.url.isNotEmpty
                      ? FilledButton.icon(
                          onPressed: () => _launch(pick.url),
                          icon: const Icon(Icons.open_in_new, size: 15),
                          label: Text('Buy on ${_retailerLabel(pick.retailer)}'),
                        )
                      : OutlinedButton.icon(
                          onPressed: () => _launch(_retailerUrl(pick)),
                          icon: const Icon(Icons.search, size: 15),
                          label: Text('Browse ${_retailerLabel(pick.retailer)}'),
                        ),
                ),
                if (pick.vivinoUrl != null) ...[
                  const SizedBox(height: 8),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => _launchVivino(pick.vivinoUrl!),
                      icon: const Icon(Icons.star_outline_rounded, size: 15),
                      label: const Text('View on Vivino'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: WwColors.violetMuted,
                        side: BorderSide(color: WwColors.violetMuted.withValues(alpha: 0.5)),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _originLabel(WinePick pick) {
    // For Australian wines, show state if known (e.g. "South Australia").
    // For international wines, show country only.
    if (pick.country == 'Australia') {
      if (pick.state != null && pick.state!.isNotEmpty) {
        return _stateLabel(pick.state!);
      }
      return 'Australia';
    }
    return pick.country ?? '';
  }

  String _stateLabel(String code) => switch (code) {
    'SA'  => 'South Australia',
    'VIC' => 'Victoria',
    'NSW' => 'New South Wales',
    'WA'  => 'Western Australia',
    'TAS' => 'Tasmania',
    'QLD' => 'Queensland',
    'NT'  => 'Northern Territory',
    'ACT' => 'ACT',
    _     => code,
  };

  String _retailerLabel(String retailer) => switch (retailer) {
    'liquorland'     => 'Liquorland',
    'cellarbrations' => 'Cellarbrations',
    'portersliquor'  => 'Porters Liquor',
    'bottleo'        => 'The Bottle-O',
    'danmurphys'     => 'Dan Murphy\'s',
    'laithwaites'    => 'Laithwaites',
    _                => retailer.isNotEmpty ? retailer : 'retailer',
  };

  String _retailerUrl(WinePick pick) {
    if (pick.retailer == 'cellarbrations') {
      final term = Uri.encodeQueryComponent(
        (pick.varietal ?? 'wine').toLowerCase(),
      );
      return 'https://www.cellarbrations.com.au/results?q=$term';
    }
    if (pick.retailer == 'portersliquor') {
      final term = Uri.encodeQueryComponent(
        (pick.varietal ?? 'wine').toLowerCase(),
      );
      return 'https://www.portersliquor.com.au/search?q=$term';
    }
    if (pick.retailer == 'bottleo') {
      final term = Uri.encodeQueryComponent(
        (pick.varietal ?? 'wine').toLowerCase(),
      );
      return 'https://www.thebottle-o.com.au/search?q=$term';
    }
    return switch (pick.retailer) {
      'danmurphys'   => 'https://www.danmurphys.com.au',
      'laithwaites'  => 'https://www.laithwaites.com.au/wine',
      'liquorland'   => 'https://www.liquorland.com.au/search?q=${Uri.encodeQueryComponent((pick.varietal ?? 'wine').toLowerCase())}',
      _              => 'https://www.liquorland.com.au',
    };
  }

  Future<void> _launch(String url) async {
    final uri = Uri.parse(url);
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      debugPrint('Could not launch $url');
    }
  }

  Future<void> _launchVivino(String url) async {
    final uri = Uri.parse(url);
    // In-app browser keeps the user in the Cellar Sage ecosystem while
    // giving Vivino their page view — opens Vivino app if installed.
    if (!await launchUrl(uri, mode: LaunchMode.inAppBrowserView)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }
}
