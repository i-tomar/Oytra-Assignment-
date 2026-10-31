"""memo/memo.md -> memo/memo.html -> memo.pdf (headless Chrome/Chromium)."""
import markdown, subprocess, shutil, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
md = open(os.path.join(ROOT, "memo", "memo.md")).read()
css = """@page{size:A4;margin:13mm 15mm} body{font-family:Georgia,'Times New Roman',serif;font-size:10.2pt;line-height:1.36;color:#111}
h3{font-family:Helvetica,Arial,sans-serif;font-size:11pt;margin:10px 0 3px;color:#1a3d6d} ul,ol{margin:3px 0 3px 18px;padding:0} li{margin:1px 0}
p{margin:4px 0} table{border-collapse:collapse;font-size:9.3pt;margin:4px 0;width:100%} td,th{border:1px solid #bbb;padding:2px 6px;text-align:left}
th{background:#eef2f7}"""
html = f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{markdown.markdown(md, extensions=['tables'])}</body></html>"
hp = os.path.join(ROOT, "memo", "memo.html"); open(hp, "w").write(html)
chrome = next((c for c in ["google-chrome", "chromium", "chromium-browser"] if shutil.which(c)), None)
if not chrome: sys.exit("Install Chrome/Chromium to build the PDF (memo.html is ready to print).")
subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                f"--print-to-pdf={os.path.join(ROOT, 'memo.pdf')}", "file://" + hp], check=True, capture_output=True)
print(os.path.join(ROOT, "memo.pdf"))
