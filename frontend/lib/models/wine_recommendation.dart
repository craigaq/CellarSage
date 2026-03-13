class WineRecommendation {
  final String name;
  final double score;
  final Map<String, double> attributeScores;

  WineRecommendation({
    required this.name,
    required this.score,
    required this.attributeScores,
  });

  factory WineRecommendation.fromJson(Map<String, dynamic> json) {
    return WineRecommendation(
      name: json['name'] as String,
      score: (json['score'] as num).toDouble(),
      attributeScores: (json['attribute_scores'] as Map<String, dynamic>)
          .map((k, v) => MapEntry(k, (v as num).toDouble())),
    );
  }
}
