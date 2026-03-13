class Merchant {
  final String name;
  final String address;
  final String brand;
  final double distanceKm;
  final double priceUsd;
  final double score;

  Merchant({
    required this.name,
    required this.address,
    required this.brand,
    required this.distanceKm,
    required this.priceUsd,
    required this.score,
  });

  factory Merchant.fromJson(Map<String, dynamic> json) {
    return Merchant(
      name: json['name'] as String,
      address: json['address'] as String,
      brand: json['brand'] as String,
      distanceKm: (json['distance_km'] as num).toDouble(),
      priceUsd: (json['price_usd'] as num).toDouble(),
      score: (json['score'] as num).toDouble(),
    );
  }
}
