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
    """
    辅助函数：给当前网页拍照并保存
    增加 account_index (账号序号)，防止不同账号的截图互相覆盖
    """
    file_path = os.path.join(SCREENSHOT_DIR, f"acc{account_index}_{step_name}.png")
    try:
        sb.save_screenshot(file_path)
        print(f"  📸 截图已保存: {file_path}")
    except Exception as e:
        print(f"  ⚠️ 截图失败 {step_name}: {e}")

# =========================================================
# Cloudflare 整页挑战 (5秒盾) 处理逻辑
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
        body_len = sb.execute_script('return document.body ? document.body.innerText.length : 0;')
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
# 【通用增强版】Cloudflare Turnstile (内嵌组件) 处理逻辑
# =========================================================
def _wait_turnstile_token(sb, timeout=30) -> bool:
    """等待后台生成真正的验证通过凭证 (Token)"""
    last_len = 0
    for _ in range(timeout):
        # 页面上可能残留多个组件，遍历所有存放 token 的输入框，只要有一个生成了就行
        token_len = sb.execute_script('''
            var inps = document.querySelectorAll('input[name="cf-turnstile-response"]');
            for(var i=0; i<inps.length; i++) {
                if(inps[i].value.length > 20) return inps[i].value.length;
            }
            return 0;
        ''')
        if token_len > 20: 
            print(f"    ✅ Turnstile token 已生成 (长度 {token_len})")
            return True
        if token_len != last_len:
            last_len = token_len
        time.sleep(1)
    print(f"    ❌ 超时未得到 token，最终长度 {last_len}")
    return False

def handle_turnstile_widget(sb, account_index, step_prefix="验证") -> bool:
    """增强版内嵌验证码处理函数（能精准识别弹窗内的特征）"""
    try:
        print("    👀 正在寻找 Turnstile 组件...")
        turnstile_found = False
        # 等待 Turnstile 组件渲染
        for _ in range(15):
            # 【核心修复点】：增加多个维度的特征识别，防漏判
            turnstile_found = sb.execute_script('''
                return !!(
                    document.querySelector('.cf-turnstile') ||
                    document.querySelector('[data-sitekey]') ||
                    document.querySelector('iframe[src*="challenges.cloudflare"]') ||
                    document.querySelector('iframe[src*="turnstile"]') ||
                    document.querySelector('input[name="cf-turnstile-response"]')
                );
            ''')
            if turnstile_found:
                break
            time.sleep(1)

        if not turnstile_found:
            print("    ℹ️ 15秒内未检测到 Turnstile 组件，尝试直接跳过。")
            return True

        print("    🧩 发现 Turnstile 组件，准备点击...")
        
        # 首选方案：使用 SeleniumBase 内置的强力验证码点击
        click_success = False
        try:
            sb.uc_gui_click_captcha()
            click_success = True
        except Exception as e:
            print(f"    ⚠️ uc_gui_click_captcha 失败: {e}")

        # 备用方案：如果第一种没点到，用 JS 尝试点击复选框
        if not click_success:
            print("    🔄 尝试备用 JS 点击方案...")
            sb.execute_script('''
                var cb = document.querySelector('input[type="checkbox"]');
                if(cb) { cb.click(); }
                else {
                    var label = document.querySelector('label');
                    if(label) label.click();
                }
            ''')

        print("    ⏳ 等待 Turnstile 完成验证...")
        if _wait_turnstile_token(sb, timeout=30):
            take_screenshot(sb, account_index, f"{step_prefix}_成功")
            return True

        print("    ❌ Turnstile 验证超时失败")
        take_screenshot(sb, account_index, f"{step_prefix}_失败")
        return False
    except Exception as e:
        print(f"    ⚠️ 处理 Turnstile 发生异常: {e}")
        return False

# =========================================================
# 单个账号的处理流程
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
        take_screenshot(sb, account_index, "03-1_登录验证前")
        turnstile_success = handle_turnstile_widget(sb, account_index, step_prefix="03-2_登录验证")
        if not turnstile_success:
            print(f"[{account_index}] ⚠️ 登录验证可能未成功，尝试强行点击登录...")

        # --- 步骤 4：点击登录按钮 ---
        print(f"[{account_index}] 步骤 4: 点击 Sign In 提交...")
        try:
            sb.click('button.bg-emerald-600[type="submit"]')
        except:
            try:
                sb.execute_script('document.querySelector("form").submit()')
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
                        
                        # --- 处理弹窗的修复点 ---
                        print(f"    [{account_index}] 等待重置确认弹窗完全加载...")
                        time.sleep(5)  # 之前是3秒，加长一点确保弹窗动画结束，CF脚本渲染完毕
                        take_screenshot(sb, account_index, f"07_{app_name}_弹窗出现")
                        
                        print(f"    [{account_index}] 处理弹窗 CF 验证...")
                        # 这次一定会揪出它了！
                        handle_turnstile_widget(sb, account_index, step_prefix=f"07_{app_name}_弹窗验证")

                        print(f"    [{account_index}] 点击 Just Reset 确认...")
                        just_reset_selector = "//button[contains(., 'Just Reset')]"
                        try:
                            sb.click(just_reset_selector)
                            time.sleep(5) # 给后端充足的处理时间
                            take_screenshot(sb, account_index, f"08_{app_name}_重置完成")
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
