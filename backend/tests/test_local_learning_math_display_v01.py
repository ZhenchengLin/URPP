"""14D-4B3: offline local SVG math asset and immutable response boundary."""
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
from app.local_learning_web_v01 import create_local_learning_web_v01
from app.services.course_knowledge.local_learning_workspace_v01 import LocalLearningWorkspaceV01


class FakeGateway:
    def generate_structured(self, *, prompt_name, payload):
        return {"content": "$$\\begin{cases}x^2 & x>0 \\\\ 0 & x\\le0\\end{cases}$$",
                "source_ids": [payload["sources"][0]["source_id"]]}


def test_math_assets_are_same_origin_and_csp_remains_strict(tmp_path):
    workspace = LocalLearningWorkspaceV01(data_root=tmp_path / "local", gateway_factory=FakeGateway)
    client = TestClient(create_local_learning_web_v01(workspace=workspace, allow_test_host=True))
    page = client.get("/")
    assert page.status_code == 200
    html = page.text
    assets = (
        "/assets/local-learning-math.js",
        "/assets/vendor/mathjax-3.2.2-tex-svg.js",
        "/assets/local-learning-markdown.js",
        "/assets/local-learning.js",
    )
    assert [html.index(asset) for asset in assets] == sorted(html.index(asset) for asset in assets)
    assert "script-src 'self'; style-src 'self'" in page.headers["content-security-policy"]
    assert "unsafe-inline" not in page.headers["content-security-policy"]
    for asset in assets[:2]:
        response = client.get(asset)
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]
        assert client.get(asset, headers={"Host": "evil.example"}).status_code == 403
    script = client.get(assets[0]).text
    assert "tex2svgPromise" in script
    assert "fontCache: \"none\"" in script
    assert "replaceChildren(rendered)" in script
    assert "innerHTML" not in script
    assert "DOMParser" not in script
    vendor = client.get(assets[1])
    assert len(vendor.content) > 200000


def test_assistive_mathml_is_clipped_by_same_origin_css(tmp_path):
    # A static contract check, not a claim of rendered-browser verification.
    workspace = LocalLearningWorkspaceV01(
        data_root=tmp_path / "local", gateway_factory=FakeGateway,
    )
    client = TestClient(create_local_learning_web_v01(
        workspace=workspace, allow_test_host=True,
    ))
    page = client.get("/")
    assert page.status_code == 200
    csp = page.headers["content-security-policy"]
    assert "style-src 'self'" in csp
    assert "unsafe-inline" not in csp
    response = client.get("/assets/local-learning.css")
    assert response.status_code == 200
    css = response.text
    assert css.count(".md-body mjx-assistive-mml{") == 1
    declarations = css.split(".md-body mjx-assistive-mml{", 1)[1].split("}", 1)[0]
    for required in (
        "position:absolute!important", "width:1px!important",
        "height:1px!important", "overflow:hidden!important",
        "clip-path:inset(50%)!important",
    ):
        assert required in declarations
    # Do not remove the MathML from the accessibility tree.
    assert "display:none" not in declarations
    assert "visibility:hidden" not in declarations


def test_math_renderer_consumes_only_tex_tokens_and_retains_text_fallback(tmp_path):
    app_path = Path(__file__).resolve().parents[1] / "app/local_learning_web_assets_v01"
    md = (app_path / "markdown_v01.js").read_text(encoding="utf8")
    math = (app_path / "math_v01.js").read_text(encoding="utf8")
    assert 'formula(token.slice(2, -2), true)' in md
    assert 'formula(token.slice(1, -1), false)' in md
    assert 'target.append(formula(content.join("\\n"), true))' in md
    assert 'pre.append(element("code", content.join("\\n")))' in md
    assert '"base", "ams"' in math
    assert 'enableMenu: false' in math
    assert 'target.replaceChildren(rendered)' in math
    assert 'target.isConnected' in math
    # This is an offline DOM-boundary smoke test; real SVG typesetting
    # requires the locally hosted library and a real browser walk-through.
    js = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
class E {
  constructor(tag, txt='') { this.tagName=tag; this._text=txt;
    this.childNodes=[]; this.className=''; this.classList={add:()=>{}}; }
  set textContent(v) {this._text=String(v); this.childNodes=[];}
  get textContent() {return this._text+this.childNodes.map(x=>x.textContent).join('');}
  get firstChild(){return this.childNodes[0];}
  append(...items){this.childNodes.push(...items);}
  replaceChildren(...items){this._text='';this.childNodes=items;}
}
globalThis.document={createElement:(tag)=>new E(tag),
  createTextNode:(value)=>new E('#text',value)};
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
vm.runInThisContext(fs.readFileSync(process.argv[2],'utf8'));
const target = new E('div');
const malicious='<img src=x onerror=alert(1)>';
URPPMarkdownV01.renderInto(target,
  '**Height:** $h_{eff}$\n\n$$\n\\begin{cases}x^2 & x>0 \\\\ 0 & x\\le0\\end{cases}\n$$\n\n```tex\n' + malicious + '\n```');
const tags=[]; const visit=(n)=>{tags.push(n.tagName);n.childNodes.forEach(visit)};visit(target);
assert(tags.includes('strong'));
assert(tags.includes('span'));assert(tags.includes('div'));assert(tags.includes('pre'));
assert(!tags.includes('img'));assert(!tags.includes('script'));
assert(target.textContent.includes('h_{eff}'));
assert(target.textContent.includes('\\begin{cases}'));
assert(target.textContent.includes(malicious));
assert(MathJax.svg.fontCache==='none');
assert(MathJax.tex.packages.join(',')==='base,ams');
'''
    result = subprocess.run(["node", "-e", js, str(app_path / "math_v01.js"),
                             str(app_path / "markdown_v01.js")],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
