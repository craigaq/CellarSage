/// Beer picks — the drill-down list of buyable beers for a style, one row per
/// retailer offer. Beer analogue of WinePick (deliberately simpler: no tiers,
/// Vivino, or critic scores — beer offers are price + retailer only).
class BeerPick {
  final String name;
  final String beerStyle;
  final double abvPercentage;
  final double price;
  final String retailer;
  final String url;
  final String packageInfo;
  final int packCount;
  final double unitPrice;

  const BeerPick({
    required this.name,
    required this.beerStyle,
    required this.abvPercentage,
    required this.price,
    required this.retailer,
    this.url = '',
    this.packageInfo = '',
    this.packCount = 1,
    this.unitPrice = 0.0,
  });

  factory BeerPick.fromJson(Map<String, dynamic> json) => BeerPick(
        name:          json['name'] as String,
        beerStyle:     (json['beer_style'] as String?) ?? '',
        abvPercentage: (json['abv_percentage'] as num?)?.toDouble() ?? 0.0,
        price:         (json['price'] as num).toDouble(),
        retailer:      (json['retailer'] as String?) ?? '',
        url:           (json['url'] as String?) ?? '',
        packageInfo:   (json['package_info'] as String?) ?? '',
        packCount:     (json['pack_count'] as num?)?.toInt() ?? 1,
        unitPrice:     (json['unit_price'] as num?)?.toDouble() ?? 0.0,
      );
}

class BeerPicksResponse {
  final String style;
  final List<BeerPick> picks;

  const BeerPicksResponse({required this.style, required this.picks});

  factory BeerPicksResponse.fromJson(Map<String, dynamic> json) =>
      BeerPicksResponse(
        style: (json['style'] as String?) ?? '',
        picks: ((json['picks'] as List?) ?? const [])
            .map((p) => BeerPick.fromJson(p as Map<String, dynamic>))
            .toList(),
      );
}
