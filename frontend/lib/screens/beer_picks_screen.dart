import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/beer_picks.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

/// Beer drill-down: every buyable beer of a style with its retailer offers.
/// Beer analogue of WinePicksScreen, opened from the result card's
/// "View Recommendations" button.
class BeerPicksScreen extends StatefulWidget {
  final String style;
  const BeerPicksScreen({super.key, required this.style});

  @override
  State<BeerPicksScreen> createState() => _BeerPicksScreenState();
}

class _BeerPicksScreenState extends State<BeerPicksScreen> {
  BeerPicksResponse? _response;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final response = await ApiService().beerPicks(style: widget.style);
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
                'No ${widget.style} listings found right now.',
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
                ? 'One ${widget.style} to buy right now.'
                : '${picks.length} ${widget.style} options — cheapest first.',
            style: WwText.bodyMedium(),
            textAlign: TextAlign.center,
          ),
        ),
        for (final pick in picks) _BeerPickCard(pick: pick),
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
  const _BeerPickCard({required this.pick});

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
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: WwDecorations.card(),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(pick.name, style: WwText.headlineMedium()),
            const SizedBox(height: 4),
            Text(
              '${pick.beerStyle}'
              '${pick.abvPercentage > 0 ? '  ·  ${pick.abvPercentage.toStringAsFixed(1)}% ABV' : ''}',
              style: WwText.bodySmall(),
            ),
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
    );
  }
}
