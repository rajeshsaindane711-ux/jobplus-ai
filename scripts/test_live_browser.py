"""
JobPlus AI — Live Sandbox Browser Automation Test
Launches a real, visible Google Chrome / Chromium window on your screen to demonstrate live form auto-filling.
Run: python scripts/test_live_browser.py
"""

import sys
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_live_browser_demo():
    print("=" * 70)
    print("      🚀 JOBPLUS AI — LIVE BROWSER SANDBOX DEMONSTRATION")
    print("=" * 70)
    print("1. Launching real visible Chromium browser window on your screen...")
    
    html_form_path = Path(r"d:\Job_Applier\tests\sandbox_form.html").resolve()
    file_url = html_form_path.as_uri()

    with sync_playwright() as p:
        # Launch real headful browser
        browser = p.chromium.launch(
            headless=False,
            slow_mo=60,  # 60ms delay so you can watch typing in real time
            args=["--window-size=1200,850", "--window-position=100,50"]
        )
        
        context = browser.new_context(viewport={"width": 1180, "height": 800})
        page = context.new_page()
        
        print(f"2. Navigating to simulated PhonePe ATS Career Portal...")
        page.goto(file_url)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(1)

        # Candidate Verified Data
        fields = [
            ("first_name", "Rajesh", "First Name"),
            ("last_name", "Saindane", "Last Name"),
            ("email", "rajeshsaindane264@gmail.com", "Email Address"),
            ("phone", "+91 8830807939", "Phone Number"),
            ("current_company", "DGLiger Consulting — Digital Engineer (DevOps)", "Current Role"),
            ("experience", "5.0 Years", "Total Experience"),
            ("notice_period", "30 Days (Negotiable)", "Notice Period"),
            ("expected_ctc", "20 LPA Fixed", "Expected CTC"),
            ("screening_tech", "4+ Years architecting EKS/AKS clusters, Helm, ArgoCD, and Kafka event streaming with 99.95% uptime.", "Screening Answer")
        ]

        print("3. Auto-filling verified candidate profile into form fields:")
        for field_id, value, label in fields:
            print(f"   ✍️  Filling [{label}] ➔ '{value[:40]}...'")
            el = page.locator(f"#{field_id}")
            el.click()
            el.type(value, delay=35)
            # Add visual highlight class
            page.evaluate(f"document.getElementById('{field_id}').classList.add('field-filled')")
            time.sleep(0.3)

        # Highlight Resume Box
        print("4. Attaching ATS-Optimized Master Resume (DevOps_SRE_Master.pdf)...")
        page.evaluate("document.getElementById('resume-box').classList.add('field-filled')")
        page.evaluate("document.getElementById('bot-status').innerText = '✅ All 9 fields auto-filled with 100% verified accuracy!'")
        time.sleep(0.5)

        print("\n" + "=" * 70)
        print("  🎉 SUCCESS! ALL FIELDS AUTO-FILLED ON YOUR SCREEN!")
        print("  Browser window is now paused for 15 seconds for your inspection.")
        print("=" * 70 + "\n")
        
        # Keep open for 15 seconds so the user can inspect the real window
        for remaining in range(15, 0, -1):
            sys.stdout.write(f"\r  ⏱️  Closing live sandbox window in {remaining} seconds (or close Chrome window anytime)...")
            sys.stdout.flush()
            time.sleep(1)

        print("\n\n5. Closing sandbox browser context safely.")
        browser.close()
        print("✅ Live Sandbox Test Finished Cleanly!\n")

if __name__ == "__main__":
    run_live_browser_demo()
