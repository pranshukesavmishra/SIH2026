#!/usr/bin/env python3
"""
SIH 2026 problem-statement selection analysis.

Merges two independent public snapshots of the 226 SIH 2026 problem statements,
then scores every statement on a "crowd-repellence index" -- a text-derived proxy
for how many student teams will realistically attempt it.

Sources (clone alongside this repo):
  https://github.com/NoBugNinja/Smart-India-Hackathon-SIH-2026-Problem-Statements
      -> full official descriptions, category, organization  (snapshot 2026-08-22)
  https://github.com/Sourav112-droid/sih-2026-problem-statements
      -> correct theme column + a community 6-factor difficulty model (snapshot 2026-08-21)

The scraped `theme` column in the first source is misaligned against its own rows
(all 226 disagree with the second source), so themes are taken from the second.

Both snapshots predate any idea submissions -- every statement reads 0/500 -- so
crowding is MODELLED here, not measured. Check live counts on sih.gov.in before
committing to a statement.
"""
import json, re, argparse, statistics, collections, pathlib

# Statements are picked by students who skim. These two vocabularies predict who skims on.
ATTRACT = r"""chatbot|chat bot|mobile app|web app|web portal|portal|dashboard|website|android|ios|
 e-?learning|gamif|quiz|awareness|survey form|crowdsourc|social media campaign|
 recommendation system|attendance|timetable|grievance|helpdesk|ticketing|marketplace|
 e-?commerce|CRM|LMS|chat interface|user-?friendly app"""

REPEL = r"""SAR|synthetic aperture|radar|radiometric|interferomet|photogrammetr|orthorect|
 infrasound|micro ?barometer|piezo|MEMS|RF|radio frequency|spectrum|IQ file|I/Q|baseband|
 modulation|demodulat|SDR|software defined radio|electronic warfare|ELINT|SIGINT|
 kalman|ephemeris|orbit|attitude|sun angle|photoclinometr|epipolar|bundle adjust|
 forensic|carving|file system|NTFS|ext4|hex|firmware|bootloader|reverse engineer|
 cryptograph|cipher|TLS|IPsec|IKE|X.509|PKI|post-?quantum|entropy|
 dead reckoning|IMU|inertial|GNSS|doppler|
 free space optical|FSO|beam|laser|telemetr|burn-?in|
 hydrodynamic|dam break|inundation|shallow water|Saint-?Venant|
 anechoic|antenna|waveguide|EMI|EMC|dielectric|arcing|thermal cycling|
 lidar|point cloud|voxel|SLAM|odometry|
 de-?anonymi|tor|onion|dark web|blockchain analysis|UTXO|mixer|
 embedded|FPGA|DSP|real-?time OS|edge device|quantiz|TinyML"""

DEFENCE_CLUSTER = {
    'DRDO',
    'Indian Space Research Organisation(ISRO)',
    'National Technical Research Organisation (NTRO)',
    'Bharat Electronics Limited',
    'Ministry of Defence (MoD)',
}

SHORT = {
    'DRDO': 'DRDO',
    'Indian Space Research Organisation(ISRO)': 'ISRO',
    'National Technical Research Organisation (NTRO)': 'NTRO',
    'Bharat Electronics Limited': 'BEL',
    'Ministry of Defence (MoD)': 'MoD',
}


def load(descriptions_json, themes_json):
    """Merge the two snapshots on PS number."""
    a = json.loads(pathlib.Path(descriptions_json).read_text())['problem_statements']
    b = json.loads(pathlib.Path(themes_json).read_text())['problems']
    by_id = {x['id']: x for x in b}

    out = []
    for rec in a:
        pid = rec['ps number'].strip()
        other = by_id.get(pid, {})
        out.append({
            'id': pid,
            'title': rec['problem statement title'].strip(),
            'org': rec['organization'].strip(),
            'category': rec['category'].strip(),
            'theme': other.get('theme'),
            'difficulty_level': other.get('difficulty_level'),
            'difficulty_score': other.get('difficulty_score'),
            'description': rec['description'],
        })
    return out


def score(statements):
    """Attach a crowd-repellence index to every statement.

    Positive index -> attractor vocabulary dominates, expect a large field.
    Negative index -> specialist vocabulary dominates, expect a small field.
    Reported to the reader as repellence = -index, so higher means fewer rivals.
    """
    for s in statements:
        text = s['title'] + "\n" + (s['description'] or "")
        s['attract'] = len(re.findall(ATTRACT, text, re.I | re.X))
        s['repel'] = len(re.findall(REPEL, text, re.I | re.X))
        s['acronyms'] = len(set(re.findall(r'\b[A-Z]{3,6}\b', text)))
        s['desc_len'] = len(s['description'] or "")
        s['crowd_index'] = round(
            3.0 * s['attract']
            - 1.6 * s['repel']
            - 0.30 * s['acronyms']
            - s['desc_len'] / 900.0,
            1,
        )
        s['repellence'] = -s['crowd_index']
    return statements


def report(statements, only_defence=False):
    rows = [s for s in statements if not only_defence or s['org'] in DEFENCE_CLUSTER]
    rows.sort(key=lambda s: -s['repellence'])

    median_all = statistics.median(s['repellence'] for s in statements)
    print(f"{len(rows)} statements | repellence median across all "
          f"{len(statements)}: {median_all:.1f}\n")
    print(f"{'ID':10}{'ORG':6}{'CAT':10}{'LVL':5}{'REPEL':8}  TITLE")
    print("-" * 132)
    for s in rows:
        print(f"{s['id']:10}{SHORT.get(s['org'], s['org'][:5]):6}{s['category']:10}"
              f"L{s['difficulty_level']:<4}{s['repellence']:<8.1f}  {s['title'][:74]}")

    print("\nBy organisation (defence cluster):")
    counts = collections.Counter(SHORT.get(s['org'], s['org'])
                                 for s in statements if s['org'] in DEFENCE_CLUSTER)
    for org, n in counts.most_common():
        print(f"  {n:3d}  {org}")


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--descriptions', default='analysis/data/sih2026_descriptions.json')
    p.add_argument('--themes', default='analysis/data/sih2026_themes.json')
    p.add_argument('--all', action='store_true', help='report all 226, not just the defence cluster')
    p.add_argument('--out', default='analysis/data/scored.json')
    args = p.parse_args()

    scored = score(load(args.descriptions, args.themes))
    pathlib.Path(args.out).write_text(json.dumps(scored, indent=1))
    report(scored, only_defence=not args.all)
