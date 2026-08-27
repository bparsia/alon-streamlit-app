import sys
sys.path.insert(0, '/Users/mbassbp2/Development/alon-streamlit-app')
import re
import subprocess
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path

SCRATCH = Path('/private/tmp/claude-502/-Users-mbassbp2-Development-deontickit/6da70574-c498-467c-a040-ddd9ecb8a6e3/scratchpad')
ROBOT = '/Users/mbassbp2/Development/deontickit/alon_experiments/reasonerstuff/robot/robot'
SRC = SCRATCH / '3_5_bare_directed.owl'


def tag(e):
    return e.tag.split('}')[-1]


def build_variant(n):
    """Keep only same_moment(m_h1, m_hK) for K in 1..n, adjust cardinality to n."""
    tree = ET.parse(SRC)
    root = tree.getroot()
    keep_targets = {f'm_h{i}' for i in range(1, n + 1)}

    new_root = ET.Element(root.tag, root.attrib)
    for child in root:
        t = tag(child)
        if t == 'ObjectPropertyAssertion':
            kids = list(child)
            if kids[0].get('IRI', '').endswith('#same_moment'):
                target = kids[2].get('IRI', '').split('#')[-1]
                if target not in keep_targets:
                    continue
        if t == 'ClassAssertion':
            kids = list(child)
            if len(kids) == 2 and tag(kids[0]) in ('ObjectExactCardinality', 'ObjectMaxCardinality'):
                kids[0].set('cardinality', str(n))
        new_root.append(child)

    rough = ET.tostring(new_root, encoding='unicode')
    reparsed = minidom.parseString(rough)
    xml_string = reparsed.toprettyxml(indent='    ')
    xml_string = re.sub(r'xmlns:ns0="[^"]*"\s*', '', xml_string)
    xml_string = re.sub(r'ns0:', '', xml_string)
    return xml_string


def run_check(owl_xml, label, timeout=120):
    in_path = SCRATCH / f'{label}.owl'
    out_path = SCRATCH / f'{label}_result.owx'
    in_path.write_text(owl_xml)
    cmd = [ROBOT, 'reason', '-r', 'HermiT', '-i', str(in_path),
           '-n', 'true', '-A', 'ClassAssertion', '-d', 'true',
           'convert', '--format', 'owx', '-o', str(out_path)]
    import time
    t0 = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, timeout
    dt = time.time() - t0
    return result.returncode == 0, dt


if __name__ == '__main__':
    for n in [1, 2, 4, 6, 8, 10, 12, 14, 16]:
        xml = build_variant(n)
        ok, dt = run_check(xml, f'breakpoint_n{n}', timeout=120)
        print(f"n={n}: {'OK' if ok else 'TIMEOUT/FAIL'} in {dt:.1f}s")
