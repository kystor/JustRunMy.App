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
# 移植自 FreeMcServer 的 CF 整页 5 秒盾处理
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
        # 【修复点】：使用纯粹的自执行函数，最前面绝对不加 return
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
            print(f"    ⚠️ 绕过出错: {e}")
        time.sleep(3)
    return False

# =========================================================
# 【核心修复】Turnstile 综合处理逻辑
# =========================================================
def handle_turnstile_verification(sb) -> bool:
    """综合处理登录页和弹窗中的 CF Turnstile 验证码"""
    
    # 1. 尝试将验证码滚动到屏幕正中央 (使用纯自执行函数)
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

    # 2. 检测到底有没有验证码
    has_turnstile = False
    for _ in range(15):
        # 【修复点】：外层不加 return，让 IIFE 自己把 boolean 值返回给 Python
        has_turnstile = sb.execute_script('''
            (function() {
                return !!(document.querySelector('.cf-turnstile') ||
                          document.querySelector('[data-sitekey]') ||
                          document.querySelector('iframe[src*="challenges.cloudflare"]') ||
                          document.querySelector('iframe[src*="turnstile"]') ||
                          document.querySelector('input[name="cf-turnstile-response"]'));
            })();
        ''')
        if has_turnstile:
            break
        time.sleep(1)

    if not has_turnstile:
        print("    ℹ️ 未检测到 Turnstile 组件，可能已被系统判定为无感安全，直接放行。")
        return True

    print("    🧩 发现 Turnstile 组件，开始执行多轮点击策略...")
    verified = False
    
    # 3. 循环 3 次主动尝试点击
    for attempt in range(1, 4):
        print(f"    ▶ 点击尝试 {attempt}/3")
        
        # (1) 用 JS 尝试点击 checkbox 或者 label
        sb.execute_script('''
            (function() {
                try {
                    var cb = document.querySelector('input[type="checkbox"]');
                    if(cb) { cb.click(); }
                    else {
                        var label = document.querySelector('label');
                        if(label) label.click();
                    }
                } catch(e) {}
            })();
        ''')
        
        # (2) 同时使用 SeleniumBase 底层点击作为保险
        try:
            sb.uc_gui_click_captcha()
        except Exception as e:
            pass
            
        # (3) 等待 Token 生成
        for _ in range(15):
            # 【修复点】：绝对不能写 return (function(){...})();
            token_len = sb.execute_script('''
                (function() {
                    var inps = document.querySelectorAll('input[name="cf-turnstile-response"]');
                    for(var i=0; i<inps.length; i++) {
                        if(inps[i].value && inps[i].value.length > 20) return inps[i].value.length;
                    }
                    return 0;
                })();
            ''')
            if token_len > 20:
                print(f"    ✅ Turnstile 主动点击成功！获取到 Token (长度 {token_len})")
                verified = True
                break
            time.sleep(1)
            
        if verified:
            break

    # 4. 如果主动点击全失败了，执行“被动等待 30 秒”兜底方案
    if not verified:
        print("    ⏳ 主动点击均未成功，可能是无感验证的计算过程，被动等待（30 秒）...")
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
            if token_len > 20:
                print(f"    ✅ Turnstile 自动完成！获取到 Token (长度 {token_len})")
                verified = True
                break
            time.sleep(1)

    if not verified:
        print("    ❌ 验证失败，用尽了所有方法未能获得 Token。")
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
            sb.type('input[type="email"], input[type="text"]', username)
            sb.type('input[type="password"]', password)
            take_screenshot(sb, account_index, "02_表单填写完毕")
        except Exception as e:
            print(f"[{account_index}] ❌ 未能找到账号密码输入框: {e}")
            take_screenshot(sb, account_index, "02_未找到输入框报错")
            return

        # --- 步骤 3：处理登录页的人机验证 ---
        print(f"[{account_index}] 步骤 3: 处理登录页 CF 验证...")
        handle_turnstile_verification(sb)

        # --- 步骤 4：点击登录按钮 ---
        print(f"[{account_index}] 步骤 4: 点击 Sign In 提交...")
        try:
            sb.click('button.bg-emerald-600[type="submit"]')
        except:
            try:
                # 【修复点】：将表单提交包入 IIFE
                sb.execute_script('(function() { document.querySelector("form").submit(); })();')
            except Exception as e:
                print(f"[{account_index}] ❌ 点击登录失败: {e}")

        time.sleep(6)
        take_screenshot(sb, account_index, "04_提交登录后")

        # --- 步骤 5：访问应用页 ---
        print(f"[{account_index}] 步骤 5: 访问应用页 https://justrunmy.app/panel/applications")
        sb.open("https://justrunmy.app/panel/applications")
        time.sleep(5)
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
                        
                        # ==================================================
                        # 步骤 7：弹窗处理核心区
                        # ==================================================
                        print(f"    [{account_index}] 等待重置确认弹窗完全加载...")
                        time.sleep(5)  
                        take_screenshot(sb, account_index, f"07_{app_name}_弹窗出现")
                        
                        print(f"    [{account_index}] 处理弹窗 CF 验证...")
                        # 此时再运行这个方法，绝不会报 SyntaxError 了
                        handle_turnstile_verification(sb)
                        
                        take_screenshot(sb, account_index, f"08_{app_name}_验证码处理后状态")

                        print(f"    [{account_index}] 点击 Just Reset 确认...")
                        try:
                            # 【修复点】：用 IIFE 包裹强制点击脚本
                            sb.execute_script('''
                                (function() {
                                    var btns = document.querySelectorAll('button');
                                    for(var i=0; i<btns.length; i++) {
                                        if(btns[i].innerText.includes('Just Reset')) {
                                            btns[i].click();
                                            break;
                                        }
                                    }
                                })();
                            ''')
                            time.sleep(5) # 给后端充足的处理时间
                            take_screenshot(sb, account_index, f"09_{app_name}_重置完成")
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
        else:
            print(f"⚠️ 警告: 发现格式不对的账号配置跳过: {pair}")

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
