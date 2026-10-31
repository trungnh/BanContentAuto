from pathlib import Path
import subprocess

html_path = Path("src/autovideo/ui/index.html")
content = html_path.read_text(encoding="utf-8")

# Activate settings tab
content = content.replace('class="nav-btn active" data-screen="wizard"', 'class="nav-btn" data-screen="wizard"')
content = content.replace('class="nav-btn" data-screen="settings"', 'class="nav-btn active" data-screen="settings"')
content = content.replace('class="screen-view active" id="screenWizard"', 'class="screen-view" id="screenWizard"')
content = content.replace('class="screen-view" id="screenSettings"', 'class="screen-view active" id="screenSettings"')

# Activate Edge subtab instead of Zerotts
content = content.replace('class="tts-tab-btn active" data-subtab="zerotts"', 'class="tts-tab-btn" data-subtab="zerotts"')
content = content.replace('class="tts-tab-btn" data-subtab="edge"', 'class="tts-tab-btn active" data-subtab="edge"')
content = content.replace('class="tts-subpage active" id="ttsPageZerotts"', 'class="tts-subpage" id="ttsPageZerotts"')
content = content.replace('class="tts-subpage" id="ttsPageEdge"', 'class="tts-subpage active" id="ttsPageEdge"')

temp_html = Path("cache/temp_edge_preview.html")
temp_html.parent.mkdir(parents=True, exist_ok=True)
temp_html.write_text(content, encoding="utf-8")

edge_bin = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
screenshot_out = Path("project/evidence/ui-07-settings-edge.png").resolve()

cmd = [
    edge_bin,
    "--headless=new",
    "--disable-gpu",
    "--window-size=1920,1080",
    f"--screenshot={screenshot_out}",
    str(temp_html.resolve().as_uri())
]
subprocess.run(cmd, check=True)
print(f"Edge subtab screenshot successfully generated: {screenshot_out}")
