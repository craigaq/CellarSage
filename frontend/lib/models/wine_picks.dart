class WinePick {
  final int tier;
  final String tierLabel;
  final String name;
  final String? varietal;
  final String? country;
  final String? state;
  final String? region;
  final double price;
  final String url;
  final String retailer;
  final bool priceIsStale;
  final bool isMemberPrice;
  final double? rating;
  final int reviewCount;
  final double? criticScore;
  final double? vivinoRating;
  final int vivinoReviewCount;
  final String? vivinoUrl;
  final bool isSagePick;
  final double? body;
  final double? acidity;
  final double? tannin;
  final double? sweetness;
  final double? fruitIntensity;
  final List<String> flavorNotes;

  const WinePick({
    required this.tier,
    required this.tierLabel,
    required this.name,
    this.varietal,
    this.country,
    this.state,
    this.region,
    required this.price,
    required this.url,
    this.retailer = '',
    this.priceIsStale = false,
    this.isMemberPrice = false,
    this.rating,
    this.reviewCount = 0,
    this.criticScore,
    this.vivinoRating,
    this.vivinoReviewCount = 0,
    this.vivinoUrl,
    this.isSagePick = false,
    this.body,
    this.acidity,
    this.tannin,
    this.sweetness,
    this.fruitIntensity,
    this.flavorNotes = const [],
  });

  factory WinePick.fromJson(Map<String, dynamic> json) => WinePick(
        tier:               json['tier'] as int,
        tierLabel:          (json['tier_label'] as String?) ?? '',
        name:               json['name'] as String,
        varietal:           json['varietal'] as String?,
        country:            json['country'] as String?,
        state:              json['state'] as String?,
        region:             json['region'] as String?,
        price:              (json['price'] as num).toDouble(),
        url:                (json['url'] as String?) ?? '',
        retailer:           (json['retailer'] as String?) ?? '',
        priceIsStale:       (json['price_is_stale'] as bool?) ?? false,
        isMemberPrice:      (json['is_member_price'] as bool?) ?? false,
        rating:             json['rating'] != null ? (json['rating'] as num).toDouble() : null,
        reviewCount:        (json['review_count'] as int?) ?? 0,
        criticScore:        json['critic_score'] != null ? (json['critic_score'] as num).toDouble() : null,
        vivinoRating:       json['vivino_rating'] != null ? (json['vivino_rating'] as num).toDouble() : null,
        vivinoReviewCount:  (json['vivino_review_count'] as int?) ?? 0,
        vivinoUrl:          json['vivino_url'] as String?,
        isSagePick:         (json['is_sage_pick'] as bool?) ?? false,
        body:               json['body'] != null ? (json['body'] as num).toDouble() : null,
        acidity:            json['acidity'] != null ? (json['acidity'] as num).toDouble() : null,
        tannin:             json['tannin'] != null ? (json['tannin'] as num).toDouble() : null,
        sweetness:          json['sweetness'] != null ? (json['sweetness'] as num).toDouble() : null,
        fruitIntensity:     json['fruit_intensity'] != null ? (json['fruit_intensity'] as num).toDouble() : null,
        flavorNotes:        (json['flavor_notes'] as List?)?.map((e) => e as String).toList() ?? [],
      );
}

class WinePicksResponse {
  final String varietal;
  final List<WinePick> picks;

  const WinePicksResponse({required this.varietal, required this.picks});

  factory WinePicksResponse.fromJson(Map<String, dynamic> json) =>
      WinePicksResponse(
        varietal: json['varietal'] as String,
        picks: (json['picks'] as List)
            .map((p) => WinePick.fromJson(p as Map<String, dynamic>))
            .toList(),
      );
}
