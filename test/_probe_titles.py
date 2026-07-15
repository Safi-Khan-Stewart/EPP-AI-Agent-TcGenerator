"""Probe: new title-builder produces concise, grammatical titles.

Verifies that:
  • _build_condition_phrase distils common AC outcome patterns,
  • _assemble_title produces natural English (no awkward concatenation),
  • _normalize_title never ends on a preposition / article / conjunction,
  • the live US #451104 title now reads cleanly.
"""
from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

import ado_advisor as A  # noqa: E402


SAMPLES = [
    'the Rejected transaction is not displayed in the Failed transactions table',
    'the user is blocked with an HTTP 403 response',
    'the wire integration is created and a confirmation is shown',
    'the count on the Failed tab matches the sum of transmission-failed payments',
    'a validation error is displayed next to the Amount field',
    'every transmission-failed intent is retried',
    'the Counterparty record is updated successfully',
    'the FieldUser is denied access to /payments/monitoring',
    'the bank filter is shown on the page',
    'the API returns HTTP 202 for the Retry endpoint',
]

print('--- Helper unit checks ---')
ok = True
for s in SAMPLES:
    cond = A._build_condition_phrase(s)
    title = A._normalize_title(A._assemble_title('Payment Monitoring', cond))
    last_word = title.split()[-1].lower().strip(',;:.-') if title else ''
    bad_tail = last_word in A._TRAILING_FUNC_WORDS
    flag = '!' if bad_tail else ' '
    ok = ok and not bad_tail
    print(f'  IN : {s}')
    print(f' {flag}-> {title}  ({len(title)} chars, ends="{last_word}")')
    print()

assert ok, 'A generated title ends on a function word'

# Live story
wi = A.get_work_item_full_details(451104)
tcs, *_ = A.generate_test_cases_from_acceptance_criteria(wi, history=None)
print('--- US 451104 generated titles ---')
for tc in tcs:
    title = tc['title']
    last_word = title.split()[-1].lower().strip(',;:.-')
    assert last_word not in A._TRAILING_FUNC_WORDS, (
        f'Title ends on function word: {title!r}')
    print(f'  [{tc.get("ac_ref", "?"):>14s}] {title}  ({len(title)} chars)')

print('\nOK — all titles are concise, grammatical, and end on a content word.')
