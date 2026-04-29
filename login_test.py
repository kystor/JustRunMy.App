#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
from seleniumbase import SB

# =========================================================
# 截图目录
# =========================================================
SCREENSHOT_DIR = "screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

def take_screenshot(sb, account_index, step_name):
    file_path = os.path.join(SCREENSHOT_DIR, f"acc{account_index}_{step_name}.png")
    try:
        sb.save_screenshot(file_path)
        print(f"  📸 {file_path}")
    except Exception as e:
        print(f"  ⚠️ 截图失败: {e}")


# =========================================================
# Cloudflare 整页盾
# =========================================================
def is_cloudflare_interstitial(sb):
    try:
        page = sb.get_page_source()
        title = (sb.get_title() or "").lower()

        if any(x in page for x in [
            "Just a moment",
            "Verify you are human",
            "Checking your browser",
            "Checking if the site connection is secure"
        ]):
            return True

        if "just a moment" in title or "attention required" in title:
            return True

        body_len = sb.execute_script("return document.body ? document.body.innerText.length : 0;")
        if body_len < 200 and "challenges.cloudflare.com" in page:
            return True

        return False
    except:
        return False


def bypass_cloudflare_interstitial(sb, max_attempts=3):
    print("🛡️ 尝试绕过 CF 整页盾...")
    for i in range(max_attempts):
        try:
            print(f"  ▶ 尝试 {i+1}/{max_attempts}")
            sb.uc_gui_click_captcha()
            time.sleep(6)

            if not is_cloudflare_interstitial(sb):
                print("  ✅ CF 已通过")
                return True
        except Exception as e:
            print(f"  ⚠️ 出错: {e}")

        time.sleep(3)

    return False


# =========================================================
# Turnstile（完整版）
# =========================================================
def _wait_token(sb, timeout=30):
    last = 0
    for _ in range(timeout):
        length = sb.execute_script('''
            var inps = document.querySelectorAll('input[name="cf-turnstile-response"]');
            for (var i=0;i<inps.length;i++){
                if(inps[i].value.length>20) return inps[i].value.length;
            }
            return 0;
        ''')
        if length > 20:
            print(f"    ✅ token OK ({length})")
            return True

        if length != last:
            last = length

        time.sleep(1)

    print("    ❌ token 超时")
    return False


def handle_turnstile_widget(sb, acc, step="cf", page_url=None):
    try:
        def scroll():
            sb.execute_script("""
                var t=document.querySelector('.cf-turnstile');
                if(t) t.scrollIntoView({block:'center'});
                else window.scrollTo(0,document.body.scrollHeight/2);
            """)
            time.sleep(2)

        def exists():
            return sb.execute_script("""
                return !!(
                    document.querySelector('.cf-turnstile') ||
                    document.querySelector('iframe[src*="turnstile"]') ||
                    document.querySelector('input[name="cf-turnstile-response"]')
                );
            """)

        for round_i in range(3):
            if round_i > 0:
                print(f"🔄 刷新重试 {round_i}")
                if page_url:
                    sb.uc_open_with_reconnect(page_url, reconnect_time=8)
                else:
                    sb.refresh()
                time.sleep(5)

            scroll()

            if not exists():
                return True

            for i in range(3):
                print(f"  ▶ 点击 {i+1}/3")
                try:
                    sb.uc_gui_click_captcha()
                except:
                    pass

                if _wait_token(sb, 25):
                    take_screenshot(sb, acc, f"{step}_ok")
                    return True

            print("  ⏳ 被动等待...")
            if _wait_token(sb, 30):
                return True

        take_screenshot(sb, acc, f"{step}_fail")
        return False

    except Exception as e:
        print("Turnstile error:", e)
        return False


# =========================================================
# 主流程
# =========================================================
def process_account(i, user, pwd):
    print(f"\n[{i}] 🚀 启动浏览器")

    with SB(uc=True, test=True, locale="en",
            chromium_arg="--disable-blink-features=AutomationControlled") as sb:

        # 访问
        sb.uc_open_with_reconnect("https://justrunmy.app/panel", reconnect_time=8)
        time.sleep(4)
        take_screenshot(sb, i, "01")

        if is_cloudflare_interstitial(sb):
            if not bypass_cloudflare_interstitial(sb):
                print("❌ CF失败")
                return

        # 输入
        sb.type('input[type="email"], input[type="text"]', user)
        sb.type('input[type="password"]', pwd)
        take_screenshot(sb, i, "02")

        # Turnstile
        handle_turnstile_widget(sb, i, "login", "https://justrunmy.app/panel")

        # 登录
        try:
            sb.click('button.bg-emerald-600[type="submit"]')
        except:
            sb.execute_script("document.querySelector('form').submit()")

        time.sleep(6)
        take_screenshot(sb, i, "03")

        # 进入应用
        sb.open("https://justrunmy.app/panel/applications")
        time.sleep(5)
        take_screenshot(sb, i, "04")

        # 批量处理
        cards = sb.find_elements("div.cursor-pointer h3.font-semibold")
        print(f"发现 {len(cards)} 个应用")

        for idx in range(len(cards)):
            cards = sb.find_elements("div.cursor-pointer h3.font-semibold")
            name = cards[idx].text

            print(f"处理: {name}")
            cards[idx].click()
            time.sleep(4)

            if sb.is_element_visible("//button[contains(., 'Reset Timer')]"):
                sb.click("//button[contains(., 'Reset Timer')]")
                time.sleep(5)

                handle_turnstile_widget(sb, i, f"reset_{idx}")

                sb.click("//button[contains(., 'Just Reset')]")
                time.sleep(5)

            sb.open("https://justrunmy.app/panel/applications")
            time.sleep(4)


# =========================================================
# 入口
# =========================================================
def main():
    raw = os.environ.get("TEST_ACCOUNTS", "")
    if not raw:
        print("❌ 没有账号")
        return

    accounts = []
    for x in raw.split(","):
        if ":" in x:
            u, p = x.split(":", 1)
            accounts.append((u.strip(), p.strip()))

    print(f"账号数量: {len(accounts)}")

    for i, (u, p) in enumerate(accounts, 1):
        try:
            process_account(i, u, p)
        except Exception as e:
            print("账号异常:", e)

        time.sleep(5)


if __name__ == "__main__":
    main()
