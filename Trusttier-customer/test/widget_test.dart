import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:trusttier_customer/main.dart';

void main() {
  setUp(() => store.apiEnabled = false);
  test('Worker model calculations and edge cases', () {
    final w = Worker('test1', '  John   Doe  ', 'Plumber', 'Gwadar', [
      JobEvent('Past job', Tier.signed, true, DateTime.now()),
      JobEvent('Past job', Tier.nfc, true, DateTime.now()),
      JobEvent('Past job', Tier.self, false, DateTime.now()),
    ]);

    expect(w.initials, 'JD');
    expect(w.signedPercent, greaterThan(0));
    expect(w.score, inInclusiveRange(0.0, 1.0));

    // Single name edge case
    final singleNamed = Worker('test2', 'Rahim', 'Rider', 'Turbat', []);
    expect(singleNamed.initials, 'R');
    expect(singleNamed.signedPercent, 0);
  });

  testWidgets('shows worker list and filters by trade chip', (tester) async {
    await tester.pumpWidget(const TrustTierApp());
    await tester.pumpAndSettle();

    expect(find.text('Find a worker'), findsOneWidget);
    expect(find.text('Hina Rasheed'), findsOneWidget);

    // Filter by Electrician
    await tester.tap(find.widgetWithText(ChoiceChip, 'Electrician'));
    await tester.pumpAndSettle();

    expect(find.text('Zahid Hussain'), findsOneWidget);
    expect(find.text('Hina Rasheed'), findsNothing);

    // Switch back to All
    await tester.tap(find.widgetWithText(ChoiceChip, 'All'));
    await tester.pumpAndSettle();

    expect(find.text('Hina Rasheed'), findsOneWidget);
  });

  testWidgets('searches workers by name or trade', (tester) async {
    await tester.pumpWidget(const TrustTierApp());
    await tester.pumpAndSettle();

    final searchField = find.byType(TextField);
    await tester.enterText(searchField, 'Plumber');
    await tester.pumpAndSettle();

    expect(find.text('Shabir Ahmed'), findsOneWidget);
    expect(find.text('Hina Rasheed'), findsNothing);

    // Clear search
    await tester.enterText(searchField, '');
    await tester.pumpAndSettle();
    expect(find.text('Hina Rasheed'), findsOneWidget);
  });

  testWidgets(
      'customer books a job and confirms after rider workflow completes',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(const TrustTierApp());
    await tester.pumpAndSettle();

    // Tap on first worker card
    await tester.tap(find.text('Rahim Baloch'));
    await tester.pumpAndSettle();

    // Verify Worker Detail Page
    expect(find.text('How this score is built'), findsOneWidget);
    expect(find.text('Request this worker'), findsOneWidget);

    // Request worker
    await tester.tap(find.text('Request this worker'));
    await tester.pumpAndSettle();

    // Fill request form
    final titleField = find.widgetWithText(TextField, 'What do you need done?');
    final addressField = find.widgetWithText(TextField, 'Address or landmark');

    await tester.enterText(titleField, 'Deliver document package');
    await tester.enterText(addressField, 'Main Bazaar, Turbat');
    await tester.pumpAndSettle();

    // Submit request
    await tester.tap(find.text('Send request'));
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();

    // Should now be on "My jobs" tab
    expect(find.text('Deliver document package'), findsOneWidget);

    // Open Job Detail Page
    await tester.tap(find.text('Deliver document package'));
    await tester.pumpAndSettle();

    expect(find.text('Job #1'), findsOneWidget);
    expect(find.text('Demo: worker badge event'), findsNothing);
    expect(find.text('Report a problem'), findsNothing);

    // Rider actions belong to the rider app; customer only receives the result.
    store.jobs.last.status = JobStatus.awaitingConfirm;
    store.notifyListeners();
    await tester.pumpAndSettle();

    final confirmBtn = find.widgetWithText(FilledButton, 'Confirm and rate');
    await tester.ensureVisible(confirmBtn);
    expect(confirmBtn, findsOneWidget);

    await tester.tap(confirmBtn);
    await tester.pumpAndSettle();

    expect(find.text('Rate Rahim Baloch'), findsOneWidget);

    final commentField = find.byType(TextField);
    await tester.enterText(commentField, 'Excellent service, highly trusted!');
    final sheetSubmitBtn = find.descendant(
      of: find.byType(ReviewSheet),
      matching: find.widgetWithText(FilledButton, 'Confirm and rate'),
    );
    await tester.tap(sheetSubmitBtn);
    await tester.pumpAndSettle();

    // Verify completed status
    expect(find.text('Excellent service, highly trusted!'), findsOneWidget);
  });
}
