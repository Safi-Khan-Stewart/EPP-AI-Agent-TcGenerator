"""Probe: trace exactly why US #451104 got the Escrow_CEA tag.

Run from project root:
    python test/_probe_epp_area_451104.py
"""
from __future__ import annotations

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from ado_advisor import get_work_item_full_details, clean_html
from domain_context import (
    build_domain_context, classify_epp_area, _ESCROW_CEA_KWS
)

wi = get_work_item_full_details(451104)
f = wi.get('fields', {}) if wi else {}
title = f.get('System.Title', '')
desc = clean_html(f.get('System.Description', '') or '')
ac = clean_html(f.get('Microsoft.VSTS.Common.AcceptanceCriteria', '') or '')

text = (title + ' ' + desc + ' ' + ac).lower()
dom = build_domain_context(title, desc, ac)

print('--- Inputs the classifier saw ---')
print(f'Portal resolved : {dom["portal"]}')
print(f'Screen matched  : {dom["matched_screen"]}  (confidence {dom["confidence"]})')
print(f'EPP area tag    : {dom["epp_area"]}')
print(f'Reason          : {dom.get("epp_area_reason")}')
print()

print('--- Why Escrow_CEA fired ---')
print('Trigger: rule #8 in classify_epp_area:')
print('   is_escrow == True  AND  any(keyword in story text)')
print()
print('Escrow_CEA keyword catalogue (HIT = present in this story):')
for k in _ESCROW_CEA_KWS:
    hit = k in text
    mark = '[HIT]' if hit else '     '
    print(f'   {mark}  "{k}"')
print()

sys_tags = (f.get('System.Tags') or '').strip()
print('--- US #451104 actual System.Tags in ADO ---')
print(f'   {sys_tags or "(none — the story itself carries no tag)"}')
