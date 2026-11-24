import 'package:flutter/material.dart';
import 'dart:async';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'services/trusttier_service.dart';

const customerId =
    String.fromEnvironment('TRUSTTIER_CLIENT_ID', defaultValue: 'CLT-0350');

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  const supabaseUrl = String.fromEnvironment('SUPABASE_URL');
  const supabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');
  if (supabaseUrl.isNotEmpty && supabaseAnonKey.isNotEmpty) {
    await Supabase.initialize(url: supabaseUrl, anonKey: supabaseAnonKey);
    try {
      if (Supabase.instance.client.auth.currentSession == null) {
        await Supabase.instance.client.auth.signInAnonymously();
      }
    } catch (_) {
      // Realtime is optional; the in-memory demo remains usable without auth.
    }
  }
  store.connectRealtime();
  runApp(const TrustTierApp());
}

// ============================================================
//  MODELS
// ============================================================

/// Evidence tiers: self-reported < NFC tap < device-signed.
enum Tier { self, nfc, signed }

extension TierInfo on Tier {
  String get label => switch (this) {
        Tier.self => 'Self-reported',
        Tier.nfc => 'NFC tap',
        Tier.signed => 'Device-signed',
      };

  /// Likelihood ratio per tier (default values, change them to tune scoring).
  double get lr => switch (this) {
        Tier.self => 1.1,
        Tier.nfc => 1.3,
        Tier.signed => 1.8,
      };

  Color get color => switch (this) {
        Tier.self => const Color(0xFF7A7F85),
        Tier.nfc => const Color(0xFFC77D0A),
        Tier.signed => const Color(0xFF0F7B5F),
      };

  IconData get icon => switch (this) {
        Tier.self => Icons.chat_bubble_outline,
        Tier.nfc => Icons.nfc,
        Tier.signed => Icons.verified_outlined,
      };

  String get proof => switch (this) {
        Tier.self => "Worker's own claim, not verified",
        Tier.nfc => 'Tag at your location was read',
        Tier.signed => 'Signature and log chain verified',
      };
}

class JobEvent {
  final String type; // Arrived, Started, Finished, Past job, Dispute
  final Tier tier;
  final bool good;
  final DateTime time;
  JobEvent(this.type, this.tier, this.good, this.time);
}

class Review {
  final String by;
  final int stars;
  final String text;
  Review(this.by, this.stars, this.text);
}

class Worker {
  final String id, name, trade, area;
  final List<JobEvent> events;
  final List<Review> reviews = [];
  double? remoteScore;
  Worker(this.id, this.name, this.trade, this.area, this.events);

  /// Posterior odds = prior odds (1.0) x likelihood ratio of every event.
  /// A good event multiplies by LR(tier), a bad event divides by it.
  double get odds {
    var o = 1.0;
    for (final e in events) {
      o *= e.good ? e.tier.lr : 1 / e.tier.lr;
    }
    return o;
  }

  double get score => remoteScore ?? odds / (1 + odds);
  int count(Tier t) => events.where((e) => e.tier == t).length;
  int get signedPercent =>
      events.isEmpty ? 0 : (count(Tier.signed) * 100 / events.length).round();
  String get initials => name
      .trim()
      .split(RegExp(r'\s+'))
      .where((p) => p.isNotEmpty)
      .map((p) => p[0].toUpperCase())
      .take(2)
      .join();
}

enum JobStatus {
  requested,
  inProgress,
  awaitingConfirm,
  completed,
  disputed,
  cancelled
}

extension JobStatusInfo on JobStatus {
  String get label => switch (this) {
        JobStatus.requested => 'Waiting for worker',
        JobStatus.inProgress => 'In progress',
        JobStatus.awaitingConfirm => 'Confirm completion',
        JobStatus.completed => 'Completed',
        JobStatus.disputed => 'Disputed',
        JobStatus.cancelled => 'Cancelled',
      };

  Color get color => switch (this) {
        JobStatus.requested => const Color(0xFF3B6EA5),
        JobStatus.inProgress => const Color(0xFFC77D0A),
        JobStatus.awaitingConfirm => const Color(0xFF7B4EA3),
        JobStatus.completed => const Color(0xFF0F7B5F),
        JobStatus.disputed => const Color(0xFFB3382C),
        JobStatus.cancelled => const Color(0xFF7A7F85),
      };
}

const steps = ['Arrived', 'Started', 'Finished'];

class Job {
  final int id;
  final Worker worker;
  final String title, address;
  final DateTime created;
  final List<JobEvent> events = [];
  JobStatus status = JobStatus.requested;
  int? stars;
  String? review;
  String? remoteId;
  Job(this.id, this.worker, this.title, this.address, this.created,
      {this.remoteId});
}

// ============================================================
//  STORE (local presentation state backed by the TrustTier API)
// ============================================================

class Store extends ChangeNotifier {
  int tab = 0;
  final List<Worker> workers = [];
  final List<Job> jobs = [];
  int _nextId = 1;
  RealtimeChannel? _scoreChannel;
  final TrustTierService _service = TrustTierService();
  String? syncMessage;
  Timer? _refreshTimer;
  bool apiEnabled = true;

  void connectRealtime() {
    refreshScores();
    refreshJobs();
    _refreshTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (tab == 1) refreshJobs();
      refreshScores();
    });
    _scoreChannel = TrustTierService().subscribeTrustScores((row) {
      final id = row['worker_id']?.toString();
      final score = row['score'];
      final worker = workers.where((item) => item.id == id).firstOrNull;
      if (worker != null && score is num) {
        worker.remoteScore = score.toDouble().clamp(0, 1);
        notifyListeners();
      }
    });
  }

  List<JobEvent> _eventsFromCounts(dynamic counts) {
    if (counts is! Map) return [];
    final now = DateTime.now();
    final signed = (counts['signed'] is num) ? (counts['signed'] as num).toInt() : 0;
    final nfc = (counts['nfc'] is num) ? (counts['nfc'] as num).toInt() : 0;
    final self = (counts['self'] is num) ? (counts['self'] as num).toInt() : 0;
    final list = <JobEvent>[];
    for (var i = 0; i < signed; i++) {
      list.add(JobEvent('Badge signed', Tier.signed, true, now.subtract(Duration(hours: i + 1))));
    }
    for (var i = 0; i < nfc; i++) {
      list.add(JobEvent('NFC tap', Tier.nfc, true, now.subtract(Duration(hours: signed + i + 1))));
    }
    for (var i = 0; i < self; i++) {
      list.add(JobEvent('Self-report', Tier.self, true, now.subtract(Duration(hours: signed + nfc + i + 1))));
    }
    return list;
  }

  Future<void> refreshScores() async {
    if (!apiEnabled) return;
    try {
      final rows = await _service.trustScores();
      Map<String, Map<String, dynamic>> riderMeta = {};
      try {
        final riders = await _service.workers();
        for (final r in riders) {
          final rid = r['rider_id']?.toString();
          if (rid != null) riderMeta[rid] = r;
        }
      } catch (_) {}

      final sorted = [...rows]..sort((a, b) {
          final idA = a['worker_id']?.toString() ?? '';
          final idB = b['worker_id']?.toString() ?? '';
          final prioA = idA.startsWith('WRK-') ? 0 : (idA == 'RDR-025' ? 1 : 2);
          final prioB = idB.startsWith('WRK-') ? 0 : (idB == 'RDR-025' ? 1 : 2);
          if (prioA != prioB) return prioA.compareTo(prioB);
          final sa = (a['score'] is num) ? (a['score'] as num).toDouble() : 0.0;
          final sb = (b['score'] is num) ? (b['score'] as num).toDouble() : 0.0;
          return sb.compareTo(sa);
        });

      for (final row in sorted.take(40)) {
        final wid = row['worker_id']?.toString();
        if (wid == null || wid.isEmpty) continue;
        final score = row['score'];
        final events = _eventsFromCounts(row['evidence_counts']);
        final existing = workers.where((item) => item.id == wid).firstOrNull;
        if (existing != null) {
          if (score is num) existing.remoteScore = score.toDouble().clamp(0, 1);
          existing.events
            ..clear()
            ..addAll(events);
        } else {
          final meta = riderMeta[wid];
          final displayName = row['display_name']?.toString();
          final name = (displayName != null && displayName.isNotEmpty) ? displayName : wid;
          final dbCohort = row['cohort']?.toString() ?? '';
          String trade = 'Rider';
          String area = 'Turbat / Gwadar';
          if (dbCohort.contains('·')) {
            final parts = dbCohort.split('·');
            trade = parts[0].trim();
            area = parts[1].trim();
          } else {
            final cohort = meta?['cohort']?.toString() ?? dbCohort;
            if (cohort.contains('Offline')) {
              area = 'Gwadar Port';
            } else if (cohort.contains('Colluder')) {
              area = 'Flagged Cohort';
            }
          }
          final w = Worker(wid, name, trade, area, events);
          if (score is num) w.remoteScore = score.toDouble().clamp(0, 1);
          workers.add(w);
        }
      }
      syncMessage = null;
      notifyListeners();
    } catch (e) {
      syncMessage = 'API unavailable: $e';
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    _scoreChannel?.unsubscribe();
    super.dispose();
  }

  void setTab(int i) {
    tab = i;
    if (i == 1) refreshJobs();
    notifyListeners();
  }

  Future<void> refreshJobs() async {
    if (!apiEnabled) return;
    try {
      final rows = await _service.jobsForClient(customerId);
      for (final row in rows) {
        final id = row['id'].toString();
        final existing = jobs.where((job) => job.remoteId == id).firstOrNull;
        final workerId = row['worker_id'].toString();
        final worker =
            workers.where((item) => item.id == workerId).firstOrNull ??
                Worker(workerId, workerId, 'Worker', '', []);
        if (existing != null) {
          existing.status = _statusFromApi(row['status']);
          continue;
        }
        final job = Job(
            _nextId++,
            worker,
            row['title']?.toString() ?? 'Job',
            row['address']?.toString() ?? '',
            DateTime.tryParse(row['created_at']?.toString() ?? '') ??
                DateTime.now(),
            remoteId: id);
        job.status = _statusFromApi(row['status']);
        jobs.add(job);
      }
      syncMessage = null;
      notifyListeners();
    } catch (_) {
      syncMessage =
          'Could not reach the TrustTier API; showing locally created jobs.';
      notifyListeners();
    }
  }

  Future<Job> addJob(Worker w, String title, String address) async {
    final j = Job(_nextId++, w, title, address, DateTime.now());
    jobs.add(j);
    if (!apiEnabled) {
      syncMessage = 'API disabled; request is local only.';
      notifyListeners();
      return j;
    }
    try {
      final remote = await _service.createJob(
          workerId: w.id, clientId: customerId, title: title, address: address);
      j.remoteId = remote['id']?.toString();
      syncMessage = null;
    } catch (_) {
      syncMessage = 'Request saved on this device only; API connection failed.';
    }
    notifyListeners();
    return j;
  }

  Future<void> confirm(Job j, int stars, String text) async {
    if (apiEnabled && j.remoteId != null) {
      await _service.confirmJob(
          jobId: j.remoteId!, clientId: customerId, stars: stars, body: text);
    } else {
      syncMessage =
          'Confirmation is local only because this job is not connected to the API.';
    }
    j.status = JobStatus.completed;
    j.stars = stars;
    j.review = text;
    j.worker.reviews.insert(0, Review('You', stars, text));
    notifyListeners();
  }

  Future<void> cancel(Job j) async {
    if (apiEnabled && j.remoteId != null) {
      await _service.updateJobStatus(j.remoteId!, 'cancelled');
    }
    j.status = JobStatus.cancelled;
    notifyListeners();
  }

  Future<void> dispute(Job j) async {
    if (apiEnabled && j.remoteId != null) {
      await _service.createDispute({
        'job_id': j.remoteId,
        'worker_id': j.worker.id,
        'client_id': customerId,
        'reason': 'Customer reported a delivery problem.'
      });
    } else {
      syncMessage =
          'Dispute is local only because this job is not connected to the API.';
    }
    j.status = JobStatus.disputed;
    // A dispute is only a claim, so it counts as a low-tier bad event.
    j.worker.events.add(JobEvent('Dispute', Tier.self, false, DateTime.now()));
    notifyListeners();
  }
}

JobStatus _statusFromApi(Object? status) => switch (status) {
      'in_progress' => JobStatus.inProgress,
      'awaiting_confirm' => JobStatus.awaitingConfirm,
      'completed' => JobStatus.completed,
      'disputed' => JobStatus.disputed,
      'cancelled' => JobStatus.cancelled,
      _ => JobStatus.requested,
    };

final store = Store();

/// Compact history builder: 'S+ N- F+'  (S = signed, N = NFC, F = self; + good, - bad)
List<JobEvent> _hist(String spec) {
  final parts = spec.split(' ');
  final now = DateTime.now();
  return [
    for (var i = 0; i < parts.length; i++)
      JobEvent(
        'Past job',
        switch (parts[i][0]) {
          'S' => Tier.signed,
          'N' => Tier.nfc,
          _ => Tier.self,
        },
        parts[i][1] == '+',
        now.subtract(Duration(days: parts.length - i)),
      ),
  ];
}

List<Worker> _seed() => [
      Worker('RDR-025', 'Rahim Baloch', 'Rider', 'Turbat',
          _hist('S+ S+ N+ S+ S+ N+ S+ N+ S-'))
        ..reviews.add(
            Review('Customer', 5, 'Arrived on time, careful with the parcel.')),
      Worker('RDR-030', 'Zahid Hussain', 'Electrician', 'Gwadar',
          _hist('S+ S+ S+ N+ S+ S+'))
        ..reviews.add(Review('Customer', 5, 'Fixed the wiring in one visit.')),
      Worker('RDR-035', 'Asif Dad', 'Rider', 'Turbat',
          _hist('F+ F+ F+ F+ F+ F+ F+ F+ F+ F+')),
      Worker('RDR-040', 'Shabir Ahmed', 'Plumber', 'Gwadar',
          _hist('N+ N+ N+ F+ N- F+ N+')),
      Worker('RDR-045', 'Hina Rasheed', 'AC Technician', 'Turbat',
          _hist('S+ S+ S+ S+ S+ N+ S+ S-')),
      Worker('RDR-050', 'Imran Jan', 'AC Technician', 'Gwadar',
          _hist('F+ F+ F- S+ N-')),
    ];

// ============================================================
//  APP
// ============================================================

class TrustTierApp extends StatelessWidget {
  const TrustTierApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TrustTier',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: const Color(0xFF0F5E5A),
        appBarTheme: const AppBarTheme(centerTitle: false),
      ),
      home: const HomeShell(),
    );
  }
}

class HomeShell extends StatelessWidget {
  const HomeShell({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) => Scaffold(
        body: IndexedStack(
          index: store.tab,
          children: const [WorkersPage(), JobsPage()],
        ),
        bottomNavigationBar: NavigationBar(
          selectedIndex: store.tab,
          onDestinationSelected: store.setTab,
          destinations: const [
            NavigationDestination(
                icon: Icon(Icons.people_outline),
                selectedIcon: Icon(Icons.people),
                label: 'Workers'),
            NavigationDestination(
                icon: Icon(Icons.assignment_outlined),
                selectedIcon: Icon(Icons.assignment),
                label: 'My jobs'),
          ],
        ),
      ),
    );
  }
}

// ============================================================
//  SMALL WIDGETS
// ============================================================

String hm(DateTime t) =>
    '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

Color scoreColor(double s) => s >= 0.8
    ? const Color(0xFF0F7B5F)
    : s >= 0.6
        ? const Color(0xFFC77D0A)
        : const Color(0xFFB3382C);

class ScoreRing extends StatelessWidget {
  final double score;
  final double size;
  const ScoreRing(this.score, {this.size = 56, super.key});

  @override
  Widget build(BuildContext context) {
    final clampedScore = score.clamp(0.0, 1.0);
    final c = scoreColor(clampedScore);
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          SizedBox.expand(
            child: CircularProgressIndicator(
              value: clampedScore,
              strokeWidth: size / 10,
              color: c,
              backgroundColor: c.withOpacity(0.15),
            ),
          ),
          Text(
            '${(clampedScore * 100).round()}',
            style: TextStyle(
                fontSize: size * 0.32, fontWeight: FontWeight.w700, color: c),
          ),
        ],
      ),
    );
  }
}

class Pill extends StatelessWidget {
  final String text;
  final Color color;
  final IconData? icon;
  const Pill(this.text, this.color, {this.icon, super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: color),
            const SizedBox(width: 4),
          ],
          Text(text,
              style: TextStyle(
                  fontSize: 12, color: color, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class TierChip extends StatelessWidget {
  final Tier tier;
  const TierChip(this.tier, {super.key});

  @override
  Widget build(BuildContext context) =>
      Pill(tier.label, tier.color, icon: tier.icon);
}

/// Thin bar showing how much of a worker's history is signed / NFC / self-reported.
class EvidenceBar extends StatelessWidget {
  final Worker w;
  const EvidenceBar(this.w, {super.key});

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: SizedBox(
        height: 6,
        child: Row(
          children: [
            for (final t in [Tier.signed, Tier.nfc, Tier.self])
              if (w.count(t) > 0)
                Expanded(flex: w.count(t), child: Container(color: t.color)),
          ],
        ),
      ),
    );
  }
}

// ============================================================
//  WORKERS
// ============================================================

class WorkersPage extends StatefulWidget {
  const WorkersPage({super.key});

  @override
  State<WorkersPage> createState() => _WorkersPageState();
}

class _WorkersPageState extends State<WorkersPage> {
  String query = '';
  String trade = 'All';

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final trades = [
          'All',
          ...{for (final w in store.workers) w.trade}
        ];
        final cleanQuery = query.trim().toLowerCase();
        final list = store.workers
            .where((w) =>
                (trade == 'All' || w.trade == trade) &&
                ('${w.name} ${w.trade} ${w.area}')
                    .toLowerCase()
                    .contains(cleanQuery))
            .toList()
          ..sort((a, b) => b.score.compareTo(a.score));

        return Scaffold(
          appBar: AppBar(title: const Text('Find a worker')),
          body: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
                child: TextField(
                  onChanged: (v) => setState(() => query = v),
                  decoration: const InputDecoration(
                    prefixIcon: Icon(Icons.search),
                    hintText: 'Search by name or town',
                    border: OutlineInputBorder(),
                    isDense: true,
                  ),
                ),
              ),
              SizedBox(
                height: 44,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  children: [
                    for (final t in trades)
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: ChoiceChip(
                          label: Text(t),
                          selected: trade == t,
                          onSelected: (_) => setState(() => trade = t),
                        ),
                      ),
                  ],
                ),
              ),
              Expanded(
                child: list.isEmpty
                    ? const Center(child: Text('No workers match your search.'))
                    : ListView.builder(
                        padding: const EdgeInsets.only(bottom: 16),
                        itemCount: list.length,
                        itemBuilder: (_, i) => WorkerCard(list[i]),
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class WorkerCard extends StatelessWidget {
  final Worker w;
  const WorkerCard(this.w, {super.key});

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.fromLTRB(16, 6, 16, 6),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => Navigator.push(
            context, MaterialPageRoute(builder: (_) => WorkerDetailPage(w))),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              CircleAvatar(child: Text(w.initials)),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(w.name,
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w600)),
                    Text('${w.trade}, ${w.area}'),
                    const SizedBox(height: 8),
                    EvidenceBar(w),
                    const SizedBox(height: 4),
                    Text(
                      '${w.events.length} events, ${w.signedPercent}% device-signed',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              ScoreRing(w.score),
            ],
          ),
        ),
      ),
    );
  }
}

class WorkerDetailPage extends StatelessWidget {
  final Worker w;
  const WorkerDetailPage(this.w, {super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final recent = w.events.reversed.take(6).toList();
        return Scaffold(
          appBar: AppBar(title: Text(w.name)),
          bottomNavigationBar: SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: FilledButton(
                onPressed: () => Navigator.push(
                    context, MaterialPageRoute(builder: (_) => BookJobPage(w))),
                child: const Text('Request this worker'),
              ),
            ),
          ),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Center(child: ScoreRing(w.score, size: 110)),
              const SizedBox(height: 12),
              Center(
                child: Text('${w.trade}, ${w.area}',
                    style: Theme.of(context).textTheme.titleMedium),
              ),
              const SizedBox(height: 20),
              Text('How this score is built',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                'Every job event changes the score. Proof counts more than claims, so signed events move it the most.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
              const SizedBox(height: 8),
              Card(
                child: Column(
                  children: [
                    for (final t in [Tier.signed, Tier.nfc, Tier.self])
                      ListTile(
                        dense: true,
                        leading: Icon(t.icon, color: t.color),
                        title: Text(t.label),
                        subtitle: Text(t.proof),
                        trailing: Text('${w.count(t)} events\nweight x${t.lr}',
                            textAlign: TextAlign.right,
                            style: Theme.of(context).textTheme.bodySmall),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Text('Recent activity',
                  style: Theme.of(context).textTheme.titleMedium),
              for (final e in recent)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(e.good ? Icons.check_circle : Icons.cancel,
                      color: e.good
                          ? const Color(0xFF0F7B5F)
                          : const Color(0xFFB3382C)),
                  title: Text(e.type),
                  trailing: TierChip(e.tier),
                ),
              const SizedBox(height: 16),
              Text('Reviews', style: Theme.of(context).textTheme.titleMedium),
              if (w.reviews.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text('No reviews yet.'),
                ),
              for (final r in w.reviews)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Row(children: [
                    for (var i = 1; i <= 5; i++)
                      Icon(i <= r.stars ? Icons.star : Icons.star_border,
                          size: 18, color: Colors.amber),
                  ]),
                  subtitle: Text(r.text.isEmpty ? 'No comment' : r.text),
                ),
            ],
          ),
        );
      },
    );
  }
}

// ============================================================
//  BOOK A JOB
// ============================================================

class BookJobPage extends StatefulWidget {
  final Worker w;
  const BookJobPage(this.w, {super.key});

  @override
  State<BookJobPage> createState() => _BookJobPageState();
}

class _BookJobPageState extends State<BookJobPage> {
  final title = TextEditingController();
  final address = TextEditingController();

  @override
  void dispose() {
    title.dispose();
    address.dispose();
    super.dispose();
  }

  Future<void> submit() async {
    final messenger = ScaffoldMessenger.of(context);
    final job =
        await store.addJob(widget.w, title.text.trim(), address.text.trim());
    if (!mounted) return;
    store.setTab(1);
    Navigator.of(context).popUntil((r) => r.isFirst);
    messenger.showSnackBar(SnackBar(
        content: Text(job.remoteId == null
            ? 'Saved locally; API connection is unavailable.'
            : 'Request sent to ${widget.w.name}')));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Request ${widget.w.name}')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: title,
            onChanged: (_) => setState(() {}),
            decoration: const InputDecoration(
              labelText: 'What do you need done?',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: address,
            decoration: const InputDecoration(
              labelText: 'Address or landmark',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            'A worker can prove they reached you by tapping the NFC tag at your location.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: title.text.trim().isEmpty ? null : () => submit(),
            child: const Text('Send request'),
          ),
        ],
      ),
    );
  }
}

// ============================================================
//  MY JOBS
// ============================================================

class JobsPage extends StatelessWidget {
  const JobsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        final list = store.jobs.reversed.toList();
        return Scaffold(
          appBar: AppBar(title: const Text('My jobs')),
          body: list.isEmpty
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Text('No jobs yet.'),
                      const SizedBox(height: 12),
                      FilledButton.tonal(
                        onPressed: () => store.setTab(0),
                        child: const Text('Find a worker'),
                      ),
                    ],
                  ),
                )
              : ListView.builder(
                  padding: const EdgeInsets.only(bottom: 16),
                  itemCount: list.length,
                  itemBuilder: (_, i) {
                    final j = list[i];
                    return Card(
                      margin: const EdgeInsets.fromLTRB(16, 6, 16, 6),
                      child: ListTile(
                        title: Text(j.title),
                        subtitle: Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(j.worker.name),
                        ),
                        trailing: Pill(j.status.label, j.status.color),
                        onTap: () => Navigator.push(
                            context,
                            MaterialPageRoute(
                                builder: (_) => JobDetailPage(j))),
                      ),
                    );
                  },
                ),
        );
      },
    );
  }
}

class JobDetailPage extends StatelessWidget {
  final Job j;
  const JobDetailPage(this.j, {super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: store,
      builder: (context, _) {
        return Scaffold(
          appBar: AppBar(title: Text('Job #${j.id}')),
          body: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(j.title,
                          style: Theme.of(context).textTheme.titleMedium),
                      if (j.address.isNotEmpty) ...[
                        const SizedBox(height: 4),
                        Text(j.address),
                      ],
                      const SizedBox(height: 10),
                      Pill(j.status.label, j.status.color),
                      const Divider(height: 24),
                      Row(
                        children: [
                          CircleAvatar(
                              radius: 18, child: Text(j.worker.initials)),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(j.worker.name,
                                    style: const TextStyle(
                                        fontWeight: FontWeight.w600)),
                                Text(j.worker.trade),
                              ],
                            ),
                          ),
                          ScoreRing(j.worker.score, size: 44),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Text('Timeline', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              for (var i = 0; i < steps.length; i++)
                _TimelineRow(
                    label: steps[i],
                    event: i < j.events.length ? j.events[i] : null),
              if (j.status == JobStatus.requested ||
                  j.status == JobStatus.inProgress) ...[
                const SizedBox(height: 12),
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.verified_user_outlined),
                    title: const Text('Rider activity is in progress'),
                    subtitle: Text(j.remoteId == null
                        ? 'This request is local only. Connect to the API to receive rider updates.'
                        : 'Rider badge actions appear in the timeline after they sync.'),
                  ),
                ),
              ],
              if (j.status == JobStatus.requested) ...[
                const SizedBox(height: 16),
                OutlinedButton(
                  onPressed: () => showDialog(
                    context: context,
                    builder: (dialogContext) => AlertDialog(
                      title: const Text('Cancel this request?'),
                      content: const Text(
                          'The worker will no longer be asked to come.'),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(dialogContext),
                          child: const Text('Keep request'),
                        ),
                        FilledButton(
                          onPressed: () async {
                            try {
                              await store.cancel(j);
                              if (dialogContext.mounted) {
                                Navigator.pop(dialogContext);
                              }
                            } catch (_) {
                              if (context.mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(
                                        content: Text(
                                            'Could not cancel on the server.')));
                              }
                            }
                          },
                          child: const Text('Cancel request'),
                        ),
                      ],
                    ),
                  ),
                  child: const Text('Cancel request'),
                ),
              ],
              if (j.status == JobStatus.awaitingConfirm) ...[
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () => showModalBottomSheet(
                    context: context,
                    isScrollControlled: true,
                    builder: (_) => ReviewSheet(j),
                  ),
                  child: const Text('Confirm and rate'),
                ),
                const SizedBox(height: 8),
                OutlinedButton(
                  onPressed: () => showDialog(
                    context: context,
                    builder: (dialogContext) => AlertDialog(
                      title: const Text('Report a problem?'),
                      content: const Text(
                          'This marks the job as disputed. A dispute is a claim without hardware proof, so it lowers the score only slightly.'),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(dialogContext),
                          child: const Text('Cancel'),
                        ),
                        FilledButton(
                          onPressed: () async {
                            try {
                              await store.dispute(j);
                              if (dialogContext.mounted) {
                                Navigator.pop(dialogContext);
                              }
                            } catch (_) {
                              if (context.mounted) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(
                                        content: Text(
                                            'Could not submit the report.')));
                              }
                            }
                          },
                          child: const Text('Report problem'),
                        ),
                      ],
                    ),
                  ),
                  child: const Text('Report a problem'),
                ),
              ],
              if (j.status == JobStatus.completed) ...[
                const SizedBox(height: 16),
                Card(
                  child: ListTile(
                    title: Row(children: [
                      for (var i = 1; i <= 5; i++)
                        Icon(
                            i <= (j.stars ?? 0)
                                ? Icons.star
                                : Icons.star_border,
                            size: 20,
                            color: Colors.amber),
                    ]),
                    subtitle: Text((j.review ?? '').isEmpty
                        ? 'You confirmed this job.'
                        : j.review!),
                  ),
                ),
              ],
            ],
          ),
        );
      },
    );
  }
}

class _TimelineRow extends StatelessWidget {
  final String label;
  final JobEvent? event;
  const _TimelineRow({required this.label, required this.event});

  @override
  Widget build(BuildContext context) {
    final done = event != null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(done ? Icons.check_circle : Icons.radio_button_unchecked,
              color: done ? const Color(0xFF0F7B5F) : Colors.grey),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label,
                    style: TextStyle(
                        fontWeight: FontWeight.w600,
                        color: done ? null : Colors.grey)),
                if (event != null) ...[
                  const SizedBox(height: 4),
                  Row(children: [
                    TierChip(event!.tier),
                    const SizedBox(width: 8),
                    Text(hm(event!.time)),
                  ]),
                  const SizedBox(height: 2),
                  Text(event!.tier.proof,
                      style: Theme.of(context).textTheme.bodySmall),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class ReviewSheet extends StatefulWidget {
  final Job job;
  const ReviewSheet(this.job, {super.key});

  @override
  State<ReviewSheet> createState() => _ReviewSheetState();
}

class _ReviewSheetState extends State<ReviewSheet> {
  int stars = 5;
  final comment = TextEditingController();

  @override
  void dispose() {
    comment.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: EdgeInsets.fromLTRB(
          20, 20, 20, 20 + MediaQuery.of(context).viewInsets.bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Rate ${widget.job.worker.name}',
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          Row(
            children: [
              for (var i = 1; i <= 5; i++)
                IconButton(
                  onPressed: () => setState(() => stars = i),
                  icon: Icon(i <= stars ? Icons.star : Icons.star_border,
                      color: Colors.amber, size: 32),
                ),
            ],
          ),
          TextField(
            controller: comment,
            maxLines: 2,
            decoration: const InputDecoration(
              hintText: 'Add a comment (optional)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 8),
          Text(
            'Your review is saved on the worker\'s profile. It does not change the trust score, because a review is a claim, not proof.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: () async {
                try {
                  await store.confirm(widget.job, stars, comment.text.trim());
                  if (context.mounted) Navigator.pop(context);
                } catch (_) {
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                        content: Text('Could not save confirmation.')));
                  }
                }
              },
              child: const Text('Confirm and rate'),
            ),
          ),
        ],
      ),
    );
  }
}
