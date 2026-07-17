from collections import Counter
from django.db.models import Q
from apps.sync.models import SyncQueue
from apps.sync.services import process_queue_row

queryset = (
    SyncQueue.objects.filter(status__in=['PENDING','RETRY'])
    .filter(Q(object_ref__startswith='results.studentsubjectscore:') | Q(object_ref__startswith='results.resultsheet:'))
    .order_by('id')
)
rows = list(queryset)
summary = Counter()
processed = 0
for row in rows:
    result = process_queue_row(row)
    summary[str(result.get('status'))] += 1
    processed += 1
    if processed % 100 == 0:
        print({'processed': processed, 'synced': summary.get('SYNCED', 0), 'retry': summary.get('RETRY', 0), 'failed': summary.get('FAILED', 0), 'conflict': summary.get('CONFLICT', 0)})

print({'total_processed': processed, 'synced': summary.get('SYNCED', 0), 'retry': summary.get('RETRY', 0), 'failed': summary.get('FAILED', 0), 'conflict': summary.get('CONFLICT', 0)})
