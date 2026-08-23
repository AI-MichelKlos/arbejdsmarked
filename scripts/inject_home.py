#!/usr/bin/env python3
from pathlib import Path
import re

p=Path(__file__).resolve().parents[1]/'index.html'
text=p.read_text(encoding='utf-8')

if 'href="control-tower.css"' not in text:
    text=text.replace('</head>','  <link rel="stylesheet" href="control-tower.css">\n</head>',1)
if 'src="control-tower.js"' not in text:
    text=text.replace('</body>','  <script src="control-tower.js"></script>\n</body>',1)

text=text.replace('aria-label="Fem interaktive løsninger"','aria-label="Syv interaktive løsninger"')
text=re.sub(r'(<div class="hero-stat"[^>]*>\s*<strong>)5(</strong>)',r'\g<1>7\2',text,count=1)

control='''\n  <section id="control-tower" aria-label="Arbejdsmarkedet lige nu">\n    <div class="ct-head"><div><h2>Arbejdsmarkedet lige nu</h2></div><p>Seneste tilgængelige tal på tværs af dashboards</p></div>\n    <div id="ctGrid" class="ct-grid"><div class="ct-loading">Henter de nyeste nøgletal...</div></div>\n  </section>\n'''
if 'id="control-tower"' not in text:
    marker='\n  <main id="overblik">'
    if marker not in text: raise RuntimeError('Kunne ikke finde hovedindholdet')
    text=text.replace(marker,control+marker,1)

nav_marker='<li><a href="https://ai-michelklos.github.io/ansatteidanskevirksomheder/">Virksomheder</a></li>'
if 'href="https://ai-michelklos.github.io/arbejdsstyrke/"' not in text.split('</nav>',1)[0]:
    text=text.replace(nav_marker,nav_marker+'\n        <li><a href="https://ai-michelklos.github.io/arbejdsstyrke/">Arbejdsstyrke</a></li>',1)

work_card='''\n      <article class="project-card">\n        <div class="card-topline"><span class="project-type">Arbejdsudbud</span><span class="live-dot" aria-hidden="true"></span><span class="live-label">Interaktiv</span></div>\n        <h3>Arbejdsstyrken i Danmark</h3>\n        <p>Se de registerbaserede RAS-tal for beskæftigelses- og erhvervsfrekvens efter alder, det aktuelle lønmodtagertal og et særligt tema om seniorer på arbejdsmarkedet.</p>\n        <ul class="topics" aria-label="Emner"><li>RAS</li><li>Beskæftigelsesfrekvens</li><li>Alder</li><li>Seniorer</li></ul>\n        <a class="project-link" href="https://ai-michelklos.github.io/arbejdsstyrke/" target="_blank" rel="noopener"><span>Åbn dashboard</span><span aria-hidden="true">→</span></a>\n      </article>'''
jobs_card='''\n      <article class="project-card">\n        <div class="card-topline"><span class="project-type">Efterspørgsel</span><span class="live-dot" aria-hidden="true"></span><span class="live-label">Interaktiv</span></div>\n        <h3>Hvor er jobbene?</h3>\n        <p>Se udviklingen i jobopslag, virksomhedernes forgæves rekrutteringer og de stillinger, hvor efterspørgslen er sværest at imødekomme.</p>\n        <ul class="topics" aria-label="Emner"><li>Jobopslag</li><li>Rekruttering</li><li>Stillinger</li><li>Efterspørgsel</li></ul>\n        <a class="project-link" href="jobs.html" target="_blank" rel="noopener"><span>Åbn dashboard</span><span aria-hidden="true">→</span></a>\n      </article>'''

start=text.find('<section class="project-grid"')
if start<0: raise RuntimeError('Kunne ikke finde projektoversigten')
end=text.find('</section>',start)
if end<0: raise RuntimeError('Kunne ikke finde slutningen på projektoversigten')
segment=text[start:end]
if 'Arbejdsstyrken i Danmark' in segment:
    segment=re.sub(r'\n\s*<article class="project-card">\s*<div class="card-topline"><span class="project-type">Arbejdsudbud</span>.*?<h3>Arbejdsstyrken i Danmark</h3>.*?</article>',work_card,segment,count=1,flags=re.S)
else:
    segment+=work_card
if 'Hvor er jobbene?' not in segment:
    segment+=jobs_card
text=text[:start]+segment+text[end:]

p.write_text(text,encoding='utf-8')
print('Forsiden er samlet med kontroltårn og syv løsninger.')
