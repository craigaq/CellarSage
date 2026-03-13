import 'package:flutter_test/flutter_test.dart';
import 'package:wine_wizard/main.dart';

void main() {
  testWidgets('App renders smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const WineWizardApp());
    expect(find.text('Wine Wizard'), findsOneWidget);
  });
}
