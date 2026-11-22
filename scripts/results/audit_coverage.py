#!/usr/bin/env python3
"""Audit diagnostic coverage, distinguishing absent measurements from missing figures."""
import re
from catalog import STANDARD_SECTIONS

def audit(meta,markdown=None):
    sections={s['id']:s for s in meta['sections']};failures=[];coverage={}
    for key,title in STANDARD_SECTIONS:
        sec=sections.get(key)
        if sec is None:
            failures.append(key+': diagnostic section absent');coverage[key]='missing';continue
        images=sec.get('images',[]);status=sec.get('data_status')
        links=re.findall(r'\[[^\]]+\]\(([^)]+)\)',sec.get('text',''))
        if images:
            coverage[key]='inline'
            if status=='unavailable':failures.append(key+': figure contradicts unavailable data status')
        elif status=='unavailable':
            coverage[key]='unavailable'
            if not sec.get('reason','').strip():failures.append(key+': unavailable measurement needs an explicit reason')
        elif links:
            coverage[key]='linked'
        elif meta.get('cases'):
            # The renderer provides real case-report links for an overview fallback.
            coverage[key]='linked'
        else:
            coverage[key]='missing';failures.append(key+': neither a figure, a data/report link, nor an unavailable-data reason')
        if markdown is not None:
            header='## '+sec.get('title',title)+'\n'
            if header not in markdown:failures.append(key+': heading absent from rendered report');continue
            body=markdown.split(header,1)[1].split('\n## ',1)[0]
            if images and not all(im['path'] in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',body) for im in images):
                failures.append(key+': declared figure not embedded under its diagnostic heading')
            if coverage[key]=='linked' and not re.search(r'\[[^\]]+\]\([^)]+\)',body):
                failures.append(key+': detailed-data link absent from rendered section')
            if coverage[key]=='unavailable' and sec.get('reason','') not in body:
                failures.append(key+': unavailable-data reason not visible in report')
    return {'coverage':coverage,'failures':failures}
