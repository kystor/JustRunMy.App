import os
import time
from seleniumbase import SB

# 截图配置
SCREENSHOT_DIR = "screenshots"
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

def take_screenshot(sb, account_index, step_name):
    file_path = os.path.join(SCREENSHOT_DIR, f"acc{account_index}_{step_name}.png")
    try:
        sb.save_screenshot(file_path)
    except:
        pass

def handle_turnstile_verification(sb):
    """精简后的验证码处理逻辑"""
    # 尝试关闭 Cookie 弹窗
    try:
        cookie_btn = 'button[data-cky-tag="accept-button"]'
        if sb.is_element_visible(cookie_btn):
            sb.click(cookie_btn)
    except:
        pass

    # 检测并点击
    has_turnstile = False
    for _ in range(10):
        if sb.is_element_present('input[name="cf-turnstile-response"]'):
            has_turnstile = True
            break
        time.sleep(1)

    if not has_turnstile:
        return True

    for attempt in range(1, 3):
        try:
            sb.uc_gui_click_captcha()
            for _ in range(10):
                token = sb.get_attribute('input[name="cf-turnstile-response"]', 'value')
                if token and len(token) > 20:
                    return True
                time.sleep(1)
        except:
            pass
    return False

def process_account(account_index, username, password):
    # 仅保留关键进度日志
    print(f"[{account_index}] 正在登录...")
    
    with SB(uc=True, test=True, locale="en", chromium_arg="--disable-blink-features=AutomationControlled") as sb:
        # 1. 访问并登录
        sb.uc_open_with_reconnect("https://justrunmy.app/panel", reconnect_time=8)
        sb.wait_for_element_visible('input[type="email"], input[type="text"]', timeout=10)
        sb.type('input[type="email"], input[type="text"]', username)
        sb.type('input[type="password"]', password)
        
        handle_turnstile_verification(sb)
        take_screenshot(sb, account_index, "login_attempt")
        
        try:
            sb.click('button.bg-emerald-600[type="submit"]')
        except:
            sb.execute_script('document.querySelector("form").submit();')

        time.sleep(5)
        
        # 2. 访问应用页并重置
        print(f"[{account_index}] 正在检查应用列表...")
        sb.open("https://justrunmy.app/panel/applications")
        time.sleep(3)
        
        app_selector = "div.cursor-pointer h3.font-semibold"
        if sb.is_element_visible(app_selector):
            apps = sb.find_elements(app_selector)
            print(f"[{account_index}] 找到 {len(apps)} 个应用，准备重置...")
            
            for i in range(len(apps)):
                # 重新获取元素防止失效
                current_apps = sb.find_elements(app_selector)
                app_name = current_apps[i].text
                current_apps[i].click()
                time.sleep(3)

                reset_btn = "//button[contains(., 'Reset Timer')]"
                if sb.is_element_visible(reset_btn):
                    sb.click(reset_btn)
                    time.sleep(3)
                    handle_turnstile_verification(sb)
                    # 执行重置确认
                    sb.execute_script('''
                        (function() {
                            var btns = document.querySelectorAll('button');
                            for(var i=0; i<btns.length; i++) {
                                if(btns[i].innerText.includes('Just Reset')) { btns[i].click(); break; }
                            }
                        })();
                    ''')
                    print(f" ✅ [{app_name}] 重置指令已发送")
                else:
                    print(f" ℹ️ [{app_name}] 无需重置")
                
                sb.open("https://justrunmy.app/panel/applications")
                time.sleep(3)
        else:
            print(f"[{account_index}] ℹ️ 未发现可用应用")

def main():
    accounts_str = os.environ.get("TEST_ACCOUNTS", "")
    if not accounts_str:
        print("❌ 错误：未配置 TEST_ACCOUNTS")
        return

    account_list = []
    for pair in accounts_str.split(','):
        if ':' in pair:
            u, p = pair.split(':', 1)
            account_list.append((u.strip(), p.strip()))

    print(f"🚀 开始测试，共计 {len(account_list)} 个账号")

    for index, (username, password) in enumerate(account_list, 1):
        masked_user = username[:2] + "***" + (username.split('@')[1] if '@' in username else "")
        print("-" * 30)
        print(f"▶ 账号 {index}/{len(account_list)}: {masked_user}")
        try:
            process_account(index, username, password)
        except Exception as e:
            print(f"❌ 运行异常: {str(e)[:50]}...")
    
    print("\n🎊 所有任务处理完毕")

if __name__ == "__main__":
    main()
