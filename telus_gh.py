#!/usr/bin/env python3
# ======================================================================
#  TELUS INTERNATIONAL - GitHub Actions Version
#  Modified for Linux/GitHub runners with Xvfb support
#  Supports matrix parallelization with ACCOUNT_OFFSET and ACCOUNT_LIMIT
# ======================================================================

import os
import sys
import uuid
import hashlib
import time
import random
import json
import subprocess
import threading
import queue
import re

from pathlib import Path
from datetime import datetime, timedelta

# --- ENVIRONMENT DETECTION ---
IS_GITHUB_ACTIONS = os.environ.get('GITHUB_ACTIONS') == 'true'
IS_LINUX = sys.platform != 'win32'

# --- CONFIGURATION ---
PROJECT_URL = "https://www.telusinternational.ai/snake/?redirect=https://www.telusinternational.ai/cmp"
COOLDOWN_HOURS = 12

# Matrix chunking via environment variables - read at runtime
ACCOUNT_OFFSET = 0
ACCOUNT_LIMIT = 0

BASE_DIR = os.environ.get('GITHUB_WORKSPACE', os.path.dirname(os.path.abspath(__file__)))
ACCOUNTS_FILE = os.path.join(BASE_DIR, "accounts.json")
OTP_TRACKING_FILE = os.path.join(BASE_DIR, "otp_tracking.json")

print_lock = threading.Lock()

def safe_print(msg):
    with print_lock:
        print(f"[Job-{os.environ.get('JOB_INDEX', '1')}] {msg}")

# --- ACCOUNTS LOADER ---
def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        safe_print(f"\n  [!] 'accounts.json' not found at {ACCOUNTS_FILE}")
        sys.exit(1)

    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            accounts = json.load(f)

        if not accounts:
            safe_print("\n  [!] accounts.json is empty")
            sys.exit(1)

        # Apply chunking for matrix
        account_offset = int(os.environ.get('ACCOUNT_OFFSET', '0'))
        account_limit = int(os.environ.get('ACCOUNT_LIMIT', '0'))
        
        if account_limit > 0:
            start = account_offset
            end = min(account_offset + account_limit, len(accounts))
            accounts = accounts[start:end]
            safe_print(f"  [*] Processing accounts {start+1} to {end} ({len(accounts)} accounts)")
            safe_print(f"  [*] Offset: {account_offset}, Limit: {account_limit}")

        return accounts
    except Exception as e:
        safe_print(f"\n  [!] Error reading accounts.json: {e}")
        sys.exit(1)

# --- OTP TRACKING (LOCAL JSON) ---
def load_otp_tracking():
    if os.path.exists(OTP_TRACKING_FILE):
        try:
            with open(OTP_TRACKING_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"used_accounts": [], "stats": {"total_success": 0, "total_failed": 0, "last_run": None}}

def save_otp_tracking(tracking_data):
    try:
        with open(OTP_TRACKING_FILE, 'w') as f:
            json.dump(tracking_data, f, indent=2)
    except:
        pass

def get_available_accounts(accounts, tracking_data):
    now = datetime.now()
    used_accounts = tracking_data.get("used_accounts", [])
    available, on_cooldown = [], []

    for account in accounts:
        email = account.get("email", "")
        phone = account.get("phone", "")
        is_on_cooldown, cooldown_remaining = False, ""

        for used in used_accounts:
            if used["email"] == email and used["phone"] == phone:
                used_time = datetime.fromisoformat(used["timestamp"])
                cooldown_end = used_time + timedelta(hours=COOLDOWN_HOURS)
                if now < cooldown_end:
                    is_on_cooldown = True
                    remaining = cooldown_end - now
                    hours, minutes = int(remaining.total_seconds() // 3600), int((remaining.total_seconds() % 3600) // 60)
                    cooldown_remaining = f"{hours}h {minutes}m"
                    break

        if is_on_cooldown:
            on_cooldown.append({"account": account, "cooldown": cooldown_remaining})
        else:
            available.append(account)

    return available, on_cooldown

def mark_account_used(email, phone, success=True):
    tracking_data = load_otp_tracking()
    now = datetime.now().isoformat()
    used_accounts = [u for u in tracking_data.get("used_accounts", []) if not (u["email"] == email and u["phone"] == phone)]
    used_accounts.append({"email": email, "phone": phone, "timestamp": now, "success": success})
    tracking_data["used_accounts"] = used_accounts
    if success:
        tracking_data["stats"]["total_success"] = tracking_data["stats"].get("total_success", 0) + 1
    else:
        tracking_data["stats"]["total_failed"] = tracking_data["stats"].get("total_failed", 0) + 1
    tracking_data["stats"]["last_run"] = now
    save_otp_tracking(tracking_data)

# --- BROWSER SETUP (Linux/Chrome) ---
def kill_browser_processes():
    safe_print("  🔄 Closing existing browser processes...")
    for browser in ['chrome', 'chromium', 'google-chrome', 'firefox']:
        try:
            subprocess.run(['pkill', '-f', browser], capture_output=True, timeout=5)
        except:
            pass
    time.sleep(2)

def check_tabs(driver):
    try:
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[0])
    except:
        pass

def setup_chrome(log_prefix):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    for attempt in range(3):
        try:
            options = Options()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-popup-blocking')
            options.add_argument('--ignore-certificate-errors')

            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

            driver = webdriver.Chrome(options=options)
            check_tabs(driver)
            return driver
        except Exception as e:
            if attempt < 2:
                safe_print(f"  {log_prefix} Retry {attempt+1}/3 after 4s...")
                time.sleep(4)
            else:
                safe_print(f"  {log_prefix} [!] Chrome Setup Error: {str(e)[:80]}")
                raise

def get_ip_info(driver):
    try:
        driver.get('http://ip-api.com/json/')
        time.sleep(2)
        body_text = driver.find_element(By.TAG_NAME, 'body').text
        if body_text:
            return {'ip': json.loads(body_text).get('query', 'Unknown')}
    except Exception as e:
        safe_print(f"  [*] IP check failed: {str(e)[:50]}")
    return {'ip': 'Unknown'}

# --- SELENIUM FUNCTIONS ---
def check_for_error(driver):
    try:
        for elem in driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'too many attempts')]"):
            if elem.is_displayed():
                return True
        for elem in driver.find_elements(By.CSS_SELECTOR, "[id*='phoneError'], [class*='error']"):
            if elem.is_displayed() and 'too many attempts' in elem.text.lower():
                return True
    except:
        pass
    return False

def wait_for_page_load(driver, timeout=60, prefix=""):
    try:
        WebDriverWait(driver, timeout).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(10)
        return True
    except:
        time.sleep(10)
        return False

def wait_for_iframe_content(driver, timeout=120, prefix=""):
    max_retries = 12
    for retry in range(max_retries):
        try:
            iframes = driver.find_elements(By.CSS_SELECTOR, "iframe")
            if iframes:
                driver.switch_to.frame(iframes[0])
                time.sleep(20)
                try:
                    body = driver.find_element(By.TAG_NAME, 'body')
                    if body and len(body.text.strip()) > 50:
                        return True
                except:
                    pass
        except:
            pass
        time.sleep(10)
    return False

def login_to_telus(driver, account, prefix=""):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    safe_print(f"  {prefix} 🌐 Loading Telus website...")
    driver.get(PROJECT_URL)
    wait_for_page_load(driver, 60, prefix)
    time.sleep(10)

    try:
        try:
            consent = driver.find_elements(By.XPATH, "//button[contains(text(), 'Got it') or contains(text(), 'Accept')]")
            if consent:
                driver.execute_script("arguments[0].click();", consent[0])
        except:
            pass

        safe_print(f"  {prefix} [*] Waiting for email field...")
        email_field = WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Your email'], input[type='email']")))
        try:
            email_field.clear()
        except:
            pass
        email_field.send_keys(Keys.CONTROL, 'a')
        email_field.send_keys(Keys.BACKSPACE)
        email_field.send_keys(account["email"])
        safe_print(f"  {prefix} [*] Email entered")

        btn = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.sui-bg-primary")))
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(8)

        safe_print(f"  {prefix} [*] Waiting for password field...")
        pass_field = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='password']")))
        try:
            pass_field.clear()
        except:
            pass
        pass_field.send_keys(account["password"])
        safe_print(f"  {prefix} [*] Password entered")

        btn = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.sui-bg-primary")))
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(10)
        safe_print(f"  {prefix} [*] Login successful")
        return True
    except Exception as e:
        safe_print(f"  {prefix} [✗] Login Error: {str(e)[:80]}")
        return False

def handle_phone_verification(driver, account, prefix=""):
    from selenium.webdriver.common.by import By

    phone = account.get("phone", "")
    if not phone or not phone.startswith('+'):
        return False
    phone_number = phone[4:]

    safe_print(f"  {prefix} 📱 Phone: {phone}")
    safe_print(f"  {prefix} 📞 Number: {phone_number}")

    driver.get("https://www.telusinternational.ai/cmp/profile")
    time.sleep(15)

    if not wait_for_iframe_content(driver, timeout=90, prefix=prefix):
        return False

    try:
        safe_print(f"  {prefix} 🔍 Searching for country dropdown...")
        country_dropdown = None
        for _ in range(8):
            try:
                xpath_list = ["//*[contains(text(), '+91')]", "//*[contains(text(), '+1')]", "//*[contains(text(), '+44')]", "//div[contains(text(), '+')]", "//button[contains(text(), '+')]", "//span[contains(text(), '+')]"]
                for xpath in xpath_list:
                    for elem in driver.find_elements(By.XPATH, xpath):
                        if elem.is_displayed() and len(elem.text.strip()) <= 10:
                            country_dropdown = elem
                            safe_print(f"  {prefix} Found: '{elem.text.strip()}'")
                            break
                    if country_dropdown:
                        break
            except:
                pass
            if country_dropdown:
                break
            time.sleep(2)

        if country_dropdown:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", country_dropdown)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", country_dropdown)
                time.sleep(2)

                tanzania_xpaths = ["//*[contains(text(), 'Tanzania')]", "//*[contains(text(), '+255')]", "//li[contains(text(), 'Tanzania')]", "//div[contains(text(), 'Tanzania')]"]
                tanzania_found = False
                for xpath in tanzania_xpaths:
                    for opt in driver.find_elements(By.XPATH, xpath):
                        if opt.is_displayed():
                            safe_print(f"  {prefix} Found Tanzania")
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", opt)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", opt)
                            tanzania_found = True
                            break
                    if tanzania_found:
                        break
            except:
                pass

        safe_print(f"  {prefix} 🔍 Searching for phone input...")
        phone_field = None
        for _ in range(8):
            try:
                for selector in ["input[placeholder*='81234']", "input[type='text']", "input:not([type='hidden']):not([type='submit']):not([type='button'])"]:
                    for field in driver.find_elements(By.CSS_SELECTOR, selector):
                        if field.is_displayed():
                            phone_field = field
                            safe_print(f"  {prefix} [*] Found phone field")
                            break
                    if phone_field:
                        break
            except:
                pass
            if phone_field:
                break
            time.sleep(2)

        if phone_field:
            safe_print(f"  {prefix} 📞 Entering: {phone_number}")
            try:
                phone_field.click()
            except:
                pass
            try:
                phone_field.clear()
            except:
                pass

            phone_field.send_keys(Keys.CONTROL, 'a')
            phone_field.send_keys(Keys.BACKSPACE)
            time.sleep(0.5)
            phone_field.send_keys(phone_number)
            time.sleep(2)

            safe_print(f"  {prefix} 📤 Searching for Send button...")
            send_button = None

            for _ in range(15):
                try:
                    button_selectors = [
                        "//button[contains(text(), 'Send verification code')]",
                        "//button[contains(text(), 'Send') and contains(text(), 'verification')]",
                        "//button[contains(text(), 'Send')]",
                        "//button[contains(text(), 'Verification')]",
                        "//button[translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='send']",
                        "//button[contains(text(), 'Submit')]",
                        "//button[@type='submit']",
                        "button.sui-bg-primary",
                        "button[class*='primary']"
                    ]
                    for selector in button_selectors:
                        for btn in (driver.find_elements(By.XPATH, selector) if selector.startswith("//") else driver.find_elements(By.CSS_SELECTOR, selector)):
                            if btn.is_displayed() and btn.is_enabled():
                                send_button = btn
                                safe_print(f"  {prefix} Found button: '{btn.text.strip()}'")
                                break
                        if send_button:
                            break
                except:
                    pass
                if send_button:
                    break
                time.sleep(2)

            if send_button:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", send_button)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", send_button)
                safe_print(f"  {prefix} [*] OTP sent to {phone}")
                time.sleep(4)

                if check_for_error(driver):
                    safe_print(f"  {prefix} [*] ERROR: 'Too many attempts' detected!")
                    mark_account_used(account["email"], account.get("phone", ""), False)
                    return False

                result = verify_otp(driver, phone, prefix)
                mark_account_used(account["email"], account.get("phone", ""), result)
                return result
            else:
                safe_print(f"  {prefix} [!] Send button not found")
                return False

    except Exception as e:
        safe_print(f"  {prefix} [*] Phone verification error: {str(e)[:80]}")

    return False

def verify_otp(driver, phone, prefix="", max_attempts=4):
    from selenium.webdriver.common.by import By

    for attempt in range(1, max_attempts + 1):
        resend_clicked = False

        for check in range(15):
            if check_for_error(driver):
                safe_print(f"\n  {prefix} [*] ERROR: 'Too many attempts' detected!")
                return False

            try:
                for selector in ["//div[@class='_resendButton_yukhx_78']//span[@role='button']", "//span[text()='Resend a verification code']", "//*[contains(text(), 'Resend a verification code')]"]:
                    for elem in driver.find_elements(By.XPATH, selector):
                        if elem.is_displayed():
                            elem_text = elem.text.strip().lower()
                            if 'resend' in elem_text and not any(char.isdigit() for char in elem_text):
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", elem)
                                time.sleep(0.5)
                                driver.execute_script("arguments[0].click();", elem)
                                resend_clicked = True
                                safe_print(f"  {prefix} [*] Resend clicked - OTP #{attempt + 1}")
                                time.sleep(3)
                                break
                    if resend_clicked:
                        break
            except:
                pass

            if resend_clicked:
                break
            time.sleep(8)

        if not resend_clicked:
            safe_print(f"  {prefix} [!] Resend button never activated")
            return False

    return True

# --- MAIN PROCESS ---
def process_account(account, account_num):
    email = account["email"]
    prefix = f"[Account-{account_num}]"

    safe_print(f"\n  {'='*60}\n  {prefix} Processing: {email}\n  {'='*60}")

    driver = None
    try:
        kill_browser_processes()

        driver = setup_chrome(prefix)
        time.sleep(3)

        ip_info = get_ip_info(driver)
        safe_print(f"  {prefix} IP: {ip_info.get('ip', 'Unknown')}")

        if login_to_telus(driver, account, prefix):
            verification_result = handle_phone_verification(driver, account, prefix)
            if verification_result:
                safe_print(f"  {prefix} [✓] OTP sent successfully")
            else:
                safe_print(f"  {prefix} [!] OTP process incomplete")
        else:
            safe_print(f"  {prefix} [✗] Login failed")

    except Exception as e:
        safe_print(f"  {prefix} [✗] ERROR: {str(e)[:50]}")
    finally:
        if driver:
            try:
                driver.switch_to.default_content()
            except:
                pass
            try:
                driver.delete_all_cookies()
            except:
                pass
            try:
                driver.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
            except:
                pass

            try:
                driver.quit()
            except:
                pass

            try:
                for browser in ['chrome', 'chromium', 'google-chrome']:
                    subprocess.run(['pkill', '-f', browser], capture_output=True, timeout=5)
            except:
                pass

def main():
    safe_print("\n" + "="*60 + "\n   TELUS GITHUB ACTIONS BOT\n" + "="*60)

    job_index = os.environ.get('JOB_INDEX', '1')
    account_offset = int(os.environ.get('ACCOUNT_OFFSET', '0'))
    account_limit = int(os.environ.get('ACCOUNT_LIMIT', '0'))
    
    safe_print(f"  Job Index: {job_index}")
    safe_print(f"  Account Offset: {account_offset}")
    safe_print(f"  Account Limit: {account_limit}")

    all_accounts = load_accounts()
    kill_browser_processes()

    tracking_data = load_otp_tracking()
    available_accounts, on_cooldown = get_available_accounts(all_accounts, tracking_data)

    safe_print(f"\n  Total accounts: {len(all_accounts)}")
    safe_print(f"  Available: {len(available_accounts)}")
    safe_print(f"  On cooldown: {len(on_cooldown)}\n")

    if not available_accounts:
        safe_print("  [*] All accounts on cooldown. Exiting.")
        sys.exit(0)

    safe_print(f"  🚀 Processing {len(available_accounts)} accounts...\n")

    for idx, account in enumerate(available_accounts):
        process_account(account, idx + 1)

    safe_print("\n" + "="*60 + "\n  [*] All accounts processed!\n" + "="*60)

if __name__ == "__main__":
    main()