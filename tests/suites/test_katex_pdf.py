#!/usr/bin/env python3
"""v1.0.43 PDF export must keep KaTeX's stretchy glyphs. KaTeX draws the √ hook
(and arrows/braces) as a 400em-wide SVG cropped by preserveAspectRatio "slice";
html2canvas rasterizes it at that attribute size and squeezes it into the box,
so only the √ overline printed. fixKatexSvgsForCapture crops each viewBox to the
visible part and pins px sizes. This test rasterizes the √ SVG the way
html2canvas does (serialize → <img> → drawImage into the box) and asserts the
hook has ink after the fix."""
import sys
import pathlib
HARNESS = (pathlib.Path(__file__).resolve().parents[1] / 'harness.html').as_uri()
from playwright.sync_api import sync_playwright

DOC = r"""# 수식

인라인 $\sqrt{x^2+1}$ 그리고 $\overrightarrow{AB}$

$$\sqrt{\frac{1}{n}\sum_{i=1}^{n}(x_i-\bar{x})^2}$$
"""

# Ink in the left third of the √ SVG below its top quarter: the hook, not the
# overline that runs along the top.
HOOK_INK = """async () => {
    const svg = document.querySelector('#preview .katex .sqrt svg');
    const r = svg.getBoundingClientRect();
    const clone = svg.cloneNode(true);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    const url = 'data:image/svg+xml;charset=utf-8,' +
        encodeURIComponent(new XMLSerializer().serializeToString(clone));
    const img = await new Promise((res, rej) => {
        const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = url;
    });
    const c = document.createElement('canvas');
    c.width = Math.ceil(r.width * 2); c.height = Math.ceil(r.height * 2);
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0, c.width, c.height);
    const y0 = Math.floor(c.height * 0.25);
    const d = ctx.getImageData(0, y0, Math.max(1, Math.floor(c.width / 3)), c.height - y0).data;
    let ink = 0;
    for (let k = 3; k < d.length; k += 4) if (d[k] > 128) ink++;
    return ink;
}"""

results = []
def check(name, ok, detail=''):
    results.append((name, ok))
    print(('PASS' if ok else 'FAIL') + ' - ' + name + (': ' + str(detail) if detail and not ok else ''))

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1000, 'height': 700})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(HARNESS)
    page.wait_for_function('!!window.__test')
    page.evaluate("window.__test.setContent(%r)" % DOC)
    page.wait_for_timeout(300)

    n = page.evaluate("document.querySelectorAll('#preview .katex svg').length")
    check('KaTeX renders SVG glyphs (√ ×2, arrow)', n >= 3, n)
    check('fixKatexSvgsForCapture is defined', page.evaluate("typeof fixKatexSvgsForCapture === 'function'"))

    before = page.evaluate(HOOK_INK)
    page.evaluate("fixKatexSvgsForCapture(document)")
    after = page.evaluate(HOOK_INK)
    check('√ hook has ink once cropped (was squeezed away)', after > 40 and after > before * 3,
          {'before': before, 'after': after})

    attrs = page.evaluate("""() => Array.from(document.querySelectorAll('#preview .katex svg')).map(s => {
        const r = s.getBoundingClientRect();
        const vb = s.getAttribute('viewBox').split(' ').map(Number);
        return { par: s.getAttribute('preserveAspectRatio'), w: +s.getAttribute('width'),
                 boxW: r.width, ratioBox: r.width / r.height, ratioVb: vb[2] / vb[3] };
    })""")
    check('every glyph SVG maps 1:1 (no slice, px size = box)',
          all(a['par'] == 'none' and abs(a['w'] - a['boxW']) < 1 for a in attrs), attrs)
    check('cropped viewBox keeps the box aspect ratio',
          all(abs(a['ratioBox'] - a['ratioVb']) / a['ratioBox'] < 0.02 for a in attrs), attrs)

    check('no page errors', len(errors) == 0, errors[:3])
    browser.close()

failed = [r for r in results if not r[1]]
print('\nRESULT: %d/%d passed' % (len(results) - len(failed), len(results)))
sys.exit(1 if failed else 0)
