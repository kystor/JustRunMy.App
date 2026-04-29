import os
import time
from seleniumbase import SB

# =========================================================
# 准备工作：设置截图保存的文件夹
# =========================================================
SCREENSHOT_DIR = "screenshots"
if not os.path.exists(SCREENSHOT_DIR):
    os.makedirs(SCREENSHOT_DIR)

def take_screenshot(sb, account_index, step_name):
    """辅助函数：给当前网页拍照并保存"""
    file_path = os.path.join(SCREENSHOT_DIR, f"acc{account_index}_{step_name}.png")
    try:
        sb.save_screenshot(file_path)
        print(f"  📸 截图已保存: {file_path}")
    except Exception as e:
        pass

# =========================================================
# 辅助操作：摧毁遮挡物和精准点击
# =========================================================
def kill_cookie_banners(sb):
    """摧毁屏幕上烦人的 Cookie 弹窗，防止它挡住验证码的点击"""
    try:
        sb.execute_script('''
            (function() {
                var btns = document.querySelectorAll('button');
                for(var i=0; i<btns.length; i++) {
                    if(btns[i].innerText.includes('Accept All') || btns[i].innerText.includes('Got it') || btns[i].innerText.includes('Allow')) {
                        btns[i].click();
                    }
                }
            })();
        ''')
        time.sleep(1)
    except:
        pass

def safe_click_by_text(sb, text_to_find):
    """最稳妥的点击按钮方式：寻找包含指定文本的按钮并点击"""
    sb.execute_script(f'''
        (function() {
            var btns = document.querySelectorAll('button, a, div.btn');
            for(var i=0; i<btns.length; i++) {
                if(btns[i].innerText.includes('{text_to_find}')) {{
                    btns[i].click();
                    break;
                }}
            }
        })();
    ''')

# =========================================================
# Cloudflare 整页 5 秒盾处理
# =========================================================
def is_cloudflare_interstitial(sb) -> bool:
    try:
        page_source = sb.get_page_source()
        title = sb.get_title().lower() if sb.get_title() else ""
        indicators = ["Just a moment", "Verify you are human", "Checking your browser", "Checking if the site connection is secure"]
        for ind in indicators:
            if ind in page_source:
                return True
        if "just a moment" in title or "attention required" in title:
            return True
        body_len = sb.execute_script('(function() { return document.body ? document.body.innerText.length : 0; })();')
        if body_len < 200 and "challenges.cloudflare.com" in page_source:
            return True
        return False
    except:
        return False

def bypass_cloudflare_interstitial(sb, max_attempts=3) -> bool:
    print("  🛡️ 检测到 Cloudflare 整页挑战，尝试绕过...")
    for attempt in range(max_attempts):
        print(f"    ▶ 绕过尝试 {attempt+1}/{max_attempts}")
        try:
            sb.uc_gui_click_captcha()
            time.sleep(6)
            if not is_cloudflare_interstitial(sb):
                print("    ✅ Cloudflare 挑战已通过")
                return True
        except Exception as e:
            pass
        time.sleep(3)
    return False

# =========================================================
# Turnstile 内嵌验证码处理逻辑
# =========================================================
def handle_turnstile_verification(sb, account_index, step_prefix) -> bool:
    """综合处理登录页和弹窗中的 CF Turnstile 验证码"""
    
    # 将验证码滚动到屏幕正中央
    sb.execute_script('''
        (function() {
            try {
                var t = document.querySelector('.cf-turnstile') || 
                        document.querySelector('iframe[src*="challenges.cloudflare"]') || 
                        document.querySelector('iframe[src*="turnstile"]');
                if (t) t.scrollIntoView({behavior:'smooth', block:'center'});
            } catch(e) {}
        })();
    ''')
    time.sleep(2)

    # 再次清理可能弹出的遮挡物
    kill_cookie_banners(sb)

    # 检测到底有没有验证码
    has_turnstile = False
    for _ in range(15):
        has_turnstile = sb.execute_script('''
            (function() {
                return !!(document.querySelector('.cf-turnstile') ||
                          document.querySelector('[data-sitekey]') ||
                          document.querySelector('iframe[src*="challenges.cloudflare"]') ||
                          document.querySelector('iframe[src*="turnstile"]'));
            })();
        ''')
        if has_turnstile:
            break
        time.sleep(1)

    if not has_turnstile:
        print("    ℹ️ 未检测到 Turnstile 组件，直接放行。")
        return True

    print("    🧩 发现 Turnstile 组件，开始执行主动点击...")
    verified = False
    
    for attempt in range(1, 4):
        print(f"    ▶ 点击尝试 {attempt}/3")
        
        # 1. 尝试使用 SeleniumBase 底层接口点
        try:
            sb.uc_gui_click_captcha()
        except Exception as e:
            pass
            
        # 2. 尝试用 JS 强行点击复选框
        sb.execute_script('''
            (function() {
                try {
                    var cb = document.querySelector('input[type="checkbox"]');
                    if(cb) { cb.click(); }
                } catch(e) {}
            })();
        ''')
            
        # 3. 等待 Token 生成
        for _ in range(15):
            token_len = sb.execute_script('''
                (function() {
                    var inps = document.querySelectorAll('input[name="cf-turnstile-response"]');
                    for(var i=0; i<inps.length; i++) {
                        if(inps[i].value && inps[i].value.length > 20) return inps[i].value.length;
                    }
                    return 0;
                })();
            ''')
            if token_len and int(token_len) > 20:
                print(f"    ✅ 验证码已通过！获取到 Token (长度 {token_len})")
                take_screenshot(sb, account_index, f"{step_prefix}_点击通过")
                verified = True
                break
            time.sleep(1)
            
        if verified:
            break

    if not verified:
        print("    ⏳ 主动点击未生效，被动等待无感验证完成（30 秒）...")
        for _ in range(30):
            token_len = sb.execute_script('''
                (function() {
                    var inps = document.querySelectorAll('input[name="cf-turnstile-response"]');
                    for(var i=0; i<inps.length; i++) {
                        if(inps[i].value && inps[i].value.length > 20) return inps[i].value.length;
                    }
                    return 0;
                })();
            ''')
            if token_len and int(token_len) > 20:
                print(f"    ✅ 验证码自动完成！(长度 {token_len})")
                take_screenshot(sb, account_index, f"{step_prefix}_自动通过")
                verified = True
                break
            time.sleep(1)

    if not verified:
        print("    ❌ 验证失败，截图留证。")
        take_screenshot(sb, account_index, f"{step_prefix}_彻底失败")
        return False
        
    return True

# =========================================================
# 单个账号的处理主流程
# =========================================================
def process_account(account_index, username, password):
    print(f"\n[{account_index}] 🚀 开始启动浏览器测试账号...")
    
    with SB(uc=True, test=True, locale="en", chromium_arg="--disable-blink-features=AutomationControlled") as sb:
        
        # --- 步骤 1：访问面板 ---
        print(f"[{account_index}] 步骤 1: 访问网址 https://justrunmy.app/panel")
        sb.uc_open_with_reconnect("https://justrunmy.app/panel", reconnect_time=8)
        time.sleep(4)
        
        # 【极其关键】干掉 Cookie 弹窗，防止拦截鼠标
        kill_cookie_banners(sb)
        take_screenshot(sb, account_index, "01_访问初始页")

        if is_cloudflare_interstitial(sb):
            if not bypass_cloudflare_interstitial(sb):
                print(f"[{account_index}] ❌ 无法绕过 CF 整页拦截，该账号测试终止。")
                take_screenshot(sb, account_index, "01-1_整页拦截失败")
                return 
            time.sleep(3) 

        # --- 步骤 2：输入账号和密码 ---
        print(f"[{account_index}] 步骤 2: 填写账号密码...")
        try:
            sb.wait_for_element_visible('input[type="email"], input[type="text"]', timeout=10)
            # 在填入前清理一下旧数据，防止重影
            sb.clear('input[type="email"], input[type="text"]')
            sb.clear('input[type="password"]')
            sb.type('input[type="email"], input[type="text"]', username)
            sb.type('input[type="password"]', password)
            take_screenshot(sb, account_index, "02_表单填写完毕")
        except Exception as e:
            print(f"[{account_index}] ❌ 未能找到账号密码输入框: {e}")
            take_screenshot(sb, account_index, "02_未找到输入框报错")
            return

        # --- 步骤 3：处理登录页的人机验证 ---
        print(f"[{account_index}] 步骤 3: 处理登录页 CF 验证...")
        handle_turnstile_verification(sb, account_index, "03_登录页验证")

        # --- 步骤 4：点击登录按钮 ---
        print(f"[{account_index}] 步骤 4: 点击 Sign In 提交...")
        try:
            # 放弃破坏性的 form.submit()，老老实实找按钮点
            safe_click_by_text(sb, "Sign In")
        except Exception as e:
            print(f"[{account_index}] ❌ 点击登录失败: {e}")

        time.sleep(6)
        take_screenshot(sb, account_index, "04_提交登录后状态")

        # 判断是否还在登录页报错
        if "login" in sb.get_current_url().lower():
            print(f"[{account_index}] ⚠️ 似乎仍停留在登录页，可能密码错误或验证码失败，终止该账号测试。")
            return

        # --- 步骤 5：访问应用页 ---
        print(f"[{account_index}] 步骤 5: 访问应用页 https://justrunmy.app/panel/applications")
        sb.open("https://justrunmy.app/panel/applications")
        time.sleep(5)
        
        kill_cookie_banners(sb)
        take_screenshot(sb, account_index, "05_应用列表页")

        # --- 步骤 6：循环查找并重置所有应用 ---
        print(f"[{account_index}] 步骤 6: 查找所有应用并准备挨个重置...")
        try:
            app_card_selector = "div.cursor-pointer h3.font-semibold"
            
            if sb.is_element_visible(app_card_selector):
                elements = sb.find_elements(app_card_selector)
                app_count = len(elements)
                print(f"[{account_index}] 📊 统共发现 {app_count} 个应用！准备开始批量处理...")

                for i in range(app_count):
                    cards = sb.find_elements(app_card_selector)
                    current_card = cards[i]
                    app_name = current_card.text
                    
                    print(f"  -> [{account_index}] 正在处理第 {i+1}/{app_count} 个应用: [{app_name}]")
                    current_card.click()
                    time.sleep(4) 
                    take_screenshot(sb, account_index, f"06_{app_name}_详情页")

                    reset_btn_selector = "//button[contains(., 'Reset Timer')]"
                    if sb.is_element_visible(reset_btn_selector):
                        print(f"    [{account_index}] 点击橙色的 Reset Timer 按钮...")
                        sb.click(reset_btn_selector)
                        
                        print(f"    [{account_index}] 等待重置确认弹窗完全加载...")
                        time.sleep(5)  
                        take_screenshot(sb, account_index, f"07_{app_name}_弹窗出现")
                        
                        print(f"    [{account_index}] 处理弹窗 CF 验证...")
                        # 此时因为没有遮挡物了，验证码应该能被顺利点到
                        handle_turnstile_verification(sb, account_index, f"07_{app_name}_弹窗验证")

                        print(f"    [{account_index}] 点击 Just Reset 确认...")
                        try:
                            # 同样使用最稳妥的根据文字找按钮并点击
                            safe_click_by_text(sb, "Just Reset")
                            time.sleep(5) 
                            take_screenshot(sb, account_index, f"08_{app_name}_最终结果")
                            print(f"    [{account_index}] ✅ 应用 [{app_name}] 重置成功！")
                        except Exception as e:
                            print(f"    [{account_index}] ❌ [{app_name}] 点击 Just Reset 失败: {e}")
                    else:
                        print(f"    [{account_index}] ℹ️ 未找到 Reset Timer 按钮，可能时间还没到。")
                    
                    print(f"  <- [{account_index}] 返回应用列表页...")
                    sb.open("https://justrunmy.app/panel/applications")
                    time.sleep(5)
            else:
                print(f"[{account_index}] ℹ️ 当前账号下没有找到任何应用卡片。")
                
        except Exception as e:
            print(f"[{account_index}] ❌ 批量重置时间过程中发生错误: {e}")
            take_screenshot(sb, account_index, "99_批量重置报错")

        print(f"[{account_index}] 🎉 当前账号测试流程执行完毕！")

# =========================================================
# 程序入口
# =========================================================
def main():
    accounts_str = os.environ.get("TEST_ACCOUNTS", "")
    if not accounts_str:
        print("❌ 错误：环境变量 TEST_ACCOUNTS 为空！请检查 GitHub Secrets。")
        return

    account_list = []
    for pair in accounts_str.split(','):
        pair = pair.strip()
        if not pair:
            continue
        if ':' in pair:
            username, password = pair.split(':', 1) 
            account_list.append((username.strip(), password.strip()))

    print(f"✅ 成功解析到 {len(account_list)} 个待测试账号。")

    for index, (username, password) in enumerate(account_list, 1):
        print("=" * 60)
        masked_user = username
        if "@" in username:
            parts = username.split("@")
            masked_user = parts[0][:2] + "***@" + parts[1]
            
        print(f"▶ 正在处理第 {index} 个账号: {masked_user}")
        
        try:
            process_account(index, username, password)
        except Exception as e:
            print(f"❌ 处理账号 {masked_user} 时发生严重异常: {e}")
            
        if index < len(account_list):
            print(f"等待 5 秒后继续测试下一个账号...")
            time.sleep(5)

    print("\n🎊 全部账号测试完毕！请前往 GitHub Artifacts 下载截图。")

if __name__ == "__main__":
    main()
