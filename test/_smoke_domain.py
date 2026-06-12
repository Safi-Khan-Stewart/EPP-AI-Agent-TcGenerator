"""Smoke-test the domain-aware generator."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from ado_advisor import generate_test_cases_from_acceptance_criteria

SAMPLES = [
    {
        'title': 'EPP: Retry transmission-failed payment from Payment Monitoring',
        'ac': ('GIVEN an AccountingUser is on /payments/monitoring and a payment '
               'is in Transmission Failed status WHEN the user clicks Retry '
               'THEN the payment is re-submitted to the provider and status updates to Pending'),
    },
    {
        'title': 'EPP: Bulk Payment Import improvements',
        'ac': ('GIVEN a Bulk AP Payment Requester WHEN they upload a CSV file '
               'with valid records THEN the batch is created and shown in /bulk-payments/batches'),
    },
]

for s in SAMPLES:
    wi = {
        'fields': {
            'System.Title': s['title'],
            'System.Description': '',
            'Microsoft.VSTS.Common.AcceptanceCriteria': s['ac'],
            'System.AreaPath': 'A',
            'System.IterationPath': 'I',
        }
    }
    tcs, *_ = generate_test_cases_from_acceptance_criteria(wi)
    print("\n" + "=" * 70)
    print(f"STORY: {s['title']}")
    print(f"Generated {len(tcs)} TCs")
    for tc in tcs[:3]:
        print(f"\n  --- {tc['title']}")
        print(f"  Objective : {tc['objective']}")
        print(f"  Preconds  : {tc['preconditions']}")
        print(f"  Steps     :")
        for st in tc['steps']:
            print(f"     - {st}")
        print(f"  Expected  :")
        for ex in tc['expected']:
            print(f"     - {ex}")
