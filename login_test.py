import os
import time
from seleniumbase import SB

# =========================================================
# 准备工作：设置截图保存的文件夹
# 作用：如果没有这个文件夹，程序会自动创建一个，防止保存截图时报错。
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
        # 如果截图失败（比如网页还没加载出来），就默默跳过，不影响主程序运行
        pass

# =========================================================
# 处理 Cloudflare 整页 5 秒盾 (访问网站第一眼看到的那个验证)
# =========================================================
def is_cloudflare_interstitial(sb) -> bool:
    """检查当前页面是否是 Cloudflare 的 5 秒盾等待页"""
    try:
        page_source = sb.get_page_source()
        title = sb.get_title().lower() if sb.get_title() else ""
        # 根据页面上的常见提示词来判断是不是在过盾
        indicators = ["Just a moment", "Verify you are human", "Checking your browser", "Checking if the site connection is secure"]
        for ind in indicators:
            if ind in page_source:
                return True
        if "just a moment" in title or "attention required" in title:
            return True
        
        # 使用立即执行函数 (IIFE) 获取网页内容长度。这里去掉了外层的 return，防止报 SyntaxError
        body_len = sb.execute_script('(function() { return document.body ? document.body.innerText.length : 0; })();')
        
        # 如果网页字很少，且代码里包含 cloudflare 网址，大概率也是在过盾
        if body_len is not None and body_len < 200 and "challenges.cloudflare.com" in page_source:
            return True
        return False
    except:
        return False

def bypass_cloudflare_interstitial(sb, max_attempts=3) -> bool:
    """尝试绕过 Cloudflare 的整页盾"""
    print("  🛡️ 检测到 Cloudflare 整页挑战，尝试绕过...")
    for attempt in range(max_attempts):
        print(f"    ▶ 绕过尝试 {attempt+1}/{max_attempts}")
        try:
            # 使用 SeleniumBase 底层的高级功能：模拟真实鼠标去点击验证码
            sb.uc_gui_click_captcha()
            time.sleep(6)
            # 如果点击后不再是 5 秒盾页面了，说明绕过成功
            if not is_cloudflare_interstitial(sb):
                print("    ✅ Cloudflare 挑战已通过")
                return True
        except Exception as e:
            print(f"    ⚠️ 绕过出错: {e}")
        time.sleep(3)
    return False

# =========================================================
# 处理 Turnstile 组件 (表单里的打钩验证码 / 终极防毒 Token 版)
# =========================================================
def handle_turnstile_verification(sb) -> bool:
    """综合处理登录页和弹窗中的 CF Turnstile 验证码"""
    
    # ==========================================
    # 步骤 1：先干掉左下角烦人的 Cookie 弹窗
    # 作用：防止它挡住后面鼠标点击验证码的路线
    # ==========================================
    try:
        # 使用最精准的 data-cky-tag 属性来定位“Accept All”按钮
        cookie_btn = 'button[data-cky-tag="accept-button"]'
        
        if sb.is_element_visible(cookie_btn):
            print("    🍪 发现 Cookie 弹窗，正在精准点击关闭...")
            sb.click(cookie_btn)
            time.sleep(1) # 等待弹窗消失动画结束
    except:
        pass

    # ==========================================
    # 步骤 2：把验证码移动到屏幕中间
    # 作用：确保鼠标能看得到它，点得到它
    # ==========================================
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

    # ==========================================
    # 步骤 3：检测页面上到底有没有验证码
    # ==========================================
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
        print("    ℹ️ 未检测到 Turnstile 组件，可能已被系统判定为无感安全，直接放行。")
        return True

    print("    🧩 发现 Turnstile 组件，开始执行物理拟人点击策略...")

    verified = False
    
    # ==========================================
    # 步骤 4：循环 3 次，尝试用真实的鼠标轨迹去点击
    # ==========================================
    for attempt in range(1, 4):
        print(f"    ▶ 点击尝试 {attempt}/3")
        
        # 坚决不使用 JS 直接点击 checkbox，防止触发 Cloudflare 的“假币 (假 Token)”陷阱
        # 统一交给底层 CDP 进行真实的物理鼠标拟人点击
        try:
            sb.uc_gui_click_captcha()
        except Exception as e:
            pass
            
        # 等待服务器下发绿色的通行证 (Token)
        for _ in range(10):
            token_len = sb.execute_script('''
                (function() {
                    var inps = document.querySelectorAll('input[name="cf-turnstile-response"]');
                    for(var i=0; i<inps.length; i++) {
                        // 如果 Token 长度大于 20，说明拿到了真正的通行证
                        if(inps[i].value && inps[i].value.length > 20) return inps[i].value.length;
                    }
                    return 0;
                })();
            ''')
            # 增加安全检查，防止因为 JS 返回了空值导致后续 Python 代码报错
            if token_len is not None and token_len > 20:
                print(f"    ✅ Turnstile 物理点击成功！获取到 Token (长度 {token_len})")
                verified = True
                break
            time.sleep(1)
            
        if verified:
            break

    # ==========================================
    # 步骤 5：如果主动点不到，就静静等待它自己绿
    # ==========================================
    if not verified:
        print("    ⏳ 物理点击未立刻生效，可能处于盾牌计算状态，被动等待 Turnstile 自动完成（30 秒）...")
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
            if token_len is not None and token_len > 20:
                print(f"    ✅ Turnstile 自动完成！获取到 Token (长度 {token_len})")
                verified = True
                break
            time.sleep(1)

    if not verified:
        print("    ❌ 验证失败，未能获得有效的 Token。")
        return False
        
    return True

# =========================================================
# 单个账号的处理主流程 (核心业务逻辑)
# =========================================================
def process_account(account_index, username, password):
    print(f"\n[{account_index}] 🚀 开始启动浏览器测试账号...")
    
    # 启用 uc (Undetected ChromeDriver) 防检测模式，伪装成普通用户
    with SB(uc=True, test=True, locale="en", chromium_arg="--disable-blink-features=AutomationControlled") as sb:
        
        # --- 第 1 步：访问面板网址 ---
        print(f"[{account_index}] 步骤 1: 访问网址 https://justrunmy.app/panel")
        sb.uc_open_with_reconnect("https://justrunmy.app/panel", reconnect_time=8)
        time.sleep(4)
        take_screenshot(sb, account_index, "01_访问初始页")

        # 看第一眼是不是遇到 5 秒盾了
        if is_cloudflare_interstitial(sb):
            if not bypass_cloudflare_interstitial(sb):
                print(f"[{account_index}] ❌ 无法绕过 CF 整页拦截，该账号测试终止。")
                take_screenshot(sb, account_index, "01-1_整页拦截失败")
                return 
            time.sleep(3) 

        # --- 第 2 步：填写账号和密码 ---
        print(f"[{account_index}] 步骤 2: 填写账号密码...")
        try:
            # 找到输入框并自动打字进去
            sb.wait_for_element_visible('input[type="email"], input[type="text"]', timeout=10)
            sb.type('input[type="email"], input[type="text"]', username)
            sb.type('input[type="password"]', password)
            take_screenshot(sb, account_index, "02_表单填写完毕")
        except Exception as e:
            print(f"[{account_index}] ❌ 未能找到账号密码输入框: {e}")
            take_screenshot(sb, account_index, "02_未找到输入框报错")
            return

        # --- 第 3 步：处理登录框下面的验证码 ---
        print(f"[{account_index}] 步骤 3: 处理登录页 CF 验证...")
        handle_turnstile_verification(sb)

        # --- 第 4 步：点击绿色的 Sign In 按钮 ---
        print(f"[{account_index}] 步骤 4: 点击 Sign In 提交...")
        try:
            sb.click('button.bg-emerald-600[type="submit"]')
        except:
            try:
                # 备用方案：如果按钮点不到，直接让表单提交
                sb.execute_script('(function() { document.querySelector("form").submit(); })();')
            except Exception as e:
                print(f"[{account_index}] ❌ 点击登录失败: {e}")

        time.sleep(6) # 给网页一点时间跳转
        take_screenshot(sb, account_index, "04_提交登录后")

        # --- 第 5 步：跳转到应用列表页 ---
        print(f"[{account_index}] 步骤 5: 访问应用页 https://justrunmy.app/panel/applications")
        sb.open("https://justrunmy.app/panel/applications")
        time.sleep(5)
        take_screenshot(sb, account_index, "05_应用列表页")

        # --- 第 6 步：找到所有应用，准备重置时间 ---
        print(f"[{account_index}] 步骤 6: 查找所有应用并准备挨个重置...")
        try:
            # 寻找页面上代表应用的卡片标题
            app_card_selector = "div.cursor-pointer h3.font-semibold"
            
            if sb.is_element_visible(app_card_selector):
                elements = sb.find_elements(app_card_selector)
                app_count = len(elements)
                print(f"[{account_index}] 📊 统共发现 {app_count} 个应用！准备开始批量处理...")

                # 挨个点进去处理
                for i in range(app_count):
                    # 【重要防坑】：每次循环重新抓取网页上的元素，防止页面跳来跳去后找不到原来的卡片
                    cards = sb.find_elements(app_card_selector)
                    current_card = cards[i]
                    app_name = current_card.text
                    
                    print(f"  -> [{account_index}] 正在处理第 {i+1}/{app_count} 个应用: [{app_name}]")
                    current_card.click()
                    time.sleep(4) 
                    take_screenshot(sb, account_index, f"06_{app_name}_详情页")

                    # 寻找重置按钮
                    reset_btn_selector = "//button[contains(., 'Reset Timer')]"
                    if sb.is_element_visible(reset_btn_selector):
                        print(f"    [{account_index}] 点击橙色的 Reset Timer 按钮...")
                        sb.click(reset_btn_selector)
                        
                        # ==================================================
                        # 处理弹窗里的验证码
                        # ==================================================
                        print(f"    [{account_index}] 等待重置确认弹窗完全加载...")
                        time.sleep(5)  
                        take_screenshot(sb, account_index, f"07_{app_name}_弹窗出现")
                        
                        print(f"    [{account_index}] 处理弹窗 CF 验证...")
                        # 再次调用我们上面写好的强大神仙函数处理验证码
                        handle_turnstile_verification(sb)
                        
                        take_screenshot(sb, account_index, f"08_{app_name}_验证码处理后状态")

                        print(f"    [{account_index}] 点击 Just Reset 确认...")
                        try:
                            # 通过 JS 找名字包含 "Just Reset" 的按钮点下去
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
                            time.sleep(5) # 稍微等一下，让服务器收到指令
                            take_screenshot(sb, account_index, f"09_{app_name}_重置完成")
                            print(f"    [{account_index}] ✅ 应用 [{app_name}] 重置成功！")
                        except Exception as e:
                            print(f"    [{account_index}] ❌ [{app_name}] 点击 Just Reset 失败: {e}")
                    else:
                        print(f"    [{account_index}] ℹ️ 未找到 Reset Timer 按钮，可能时间还没到。")
                    
                    # 退出来，准备处理下一个
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
# 程序入口点 (脚本刚开始运行的地方)
# =========================================================
def main():
    # 尝试从系统环境变量里拿出我们的多账号长字符串
    accounts_str = os.environ.get("TEST_ACCOUNTS", "")
    
    if not accounts_str:
        print("❌ 错误：环境变量 TEST_ACCOUNTS 为空！请检查 GitHub Secrets。")
        return

    account_list = []
    # 按照英文逗号，把一长串字符串切成一段段的账号密码对
    for pair in accounts_str.split(','):
        pair = pair.strip()
        if not pair:
            continue
        # 再用冒号把账号和密码拆开
        if ':' in pair:
            username, password = pair.split(':', 1) 
            account_list.append((username.strip(), password.strip()))
        else:
            print(f"⚠️ 警告: 发现格式不对的账号配置跳过: {pair}")

    print(f"✅ 成功解析到 {len(account_list)} 个待测试账号。")

    # 开始遍历刚才整理好的列表，挨个干活
    for index, (username, password) in enumerate(account_list, 1):
        print("=" * 60)
        # 给控制台显示的账号打个码，保护你的隐私
        masked_user = username
        if "@" in username:
            parts = username.split("@")
            masked_user = parts[0][:2] + "***@" + parts[1]
            
        print(f"▶ 正在处理第 {index} 个账号: {masked_user}")
        
        try:
            # 调用前面写好的核心业务流程
            process_account(index, username, password)
        except Exception as e:
            print(f"❌ 处理账号 {masked_user} 时发生严重异常: {e}")
            
        # 两个账号之间歇一会儿，别把服务器惹火了
        if index < len(account_list):
            print(f"等待 5 秒后继续测试下一个账号...")
            time.sleep(5)

    print("\n🎊 全部账号测试完毕！请前往 GitHub Artifacts 下载截图。")

# 这是一个标准的 Python 规范，意思是“如果是直接运行这个文件，就执行 main()”
if __name__ == "__main__":
    main()
