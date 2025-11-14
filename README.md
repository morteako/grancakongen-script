# Grancakongen-script

## Lagre curl med token og cookie, fra strava 

Åpne https://www.strava.com/segments/4580190 i chrome. 
Åpne devtools -> network..
Finn "history"-requestet. Kjør "Copy" -> "Copy as Curl".
Lim inn i en fil som heter .strava_curl

## Kjør
Kjør `python segment_history.py`.

Velg navn når man blir spurt.

Eksempel-output:
```
Velg NAVN fra Utøvere-listen (skriv tallet eller et eget navn):
1. Sivert Schou Olsen
2. Morten Kolstad
3. Sondre Lunde
4. Edvard Bakken
5. Fredrik Mørk
6. Erik Kolstad
Skriv f.eks. 3. for å velge navn nummer 3, eller skriv inn et annet navn.
NAVN: 2
År	segment	NAVN	elapsed time (mm:ss)	segment effort URL	avg Watt	avg Bpm	avg Cadence
2022	soria	Morten Kolstad	30:35	https://www.strava.com/segment_efforts/3030174483721426408		171
2023	soria	Morten Kolstad	34:38	https://www.strava.com/segment_efforts/3158091196060074326		162
2024	soria	Morten Kolstad	26:35	https://www.strava.com/segment_efforts/3294343878888079796		173
2023	serenity	Morten Kolstad	44:34	https://www.strava.com/segment_efforts/3159861183229221324		166
2024	serenity	Morten Kolstad	36:56	https://www.strava.com/segment_efforts/3294343878882411956		171
2022	ayagueres	Morten Kolstad	16:54	https://www.strava.com/segment_efforts/3030484105445438458		166
2024	ayagueres	Morten Kolstad	29:08	https://www.strava.com/segment_efforts/3292859268892852236		138
2023	ayacata	Morten Kolstad	32:02	https://www.strava.com/segment_efforts/3158804390256798398		157
2024	ayacata	Morten Kolstad	19:18	https://www.strava.com/segment_efforts/3292544199819237376		166
2022	san-bart	Morten Kolstad	19:27	https://www.strava.com/segment_efforts/3028736364292831114		164
2023	san-bart	Morten Kolstad	19:38	https://www.strava.com/segment_efforts/3159568189989073566		163
2024	san-bart	Morten Kolstad	17:56	https://www.strava.com/segment_efforts/3292167447365834904		162
2022	test	Morten Kolstad	20:04	https://www.strava.com/segment_efforts/2993251959219100820		111
2024	test	Morten Kolstad	14:35	https://www.strava.com/segment_efforts/3234842962924355270		161
2025	test	Morten Kolstad	14:20	https://www.strava.com/segment_efforts/3400892324094679722	215	181	77

Saved 15 rows to /Users/mortenkolstad/grancakongen-script/results.csv
```

Kopier linjene under Headeren, altså de som starter med et årstall.

Lim disse inn i Resultater-tabben i [grancakongen-tider](https://docs.google.com/spreadsheets/d/16-gb4q-aAdpWsrwcn-91vOEqSNfND9xp8Sku4QVDi9s/edit?gid=1339766999#gid=1339766999).
La det være noen tomme rader mellom forskjellige folk, for å lettere kunne legge til flere senere osv