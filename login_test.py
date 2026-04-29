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
    最终文件名类似: screenshots/acc1_01_访问初始页.png
    """
    file_path = os.path.join(SCREENSHOT_DIR, f"acc{account_index}_{step_name}.png")
    try:
        sb.save_screenshot(file_path)
        print(f"  📸 截图已保存: {file_path}")
    except Exception as e:
        print(f"  ⚠️ 截图失败 {step_name}: {e}")

# =========================================================
# 移植的 Cloudflare 整页挑战 (5秒盾) 处理逻辑
# =========================================================
def is_cloudflare_interstitial(sb) -> bool:
    """判断当前页面是否为 CF 的 5 秒盾拦截页"""
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
    """尝试绕过 CF 5秒盾"""
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
# 移植的 Cloudflare Turnstile (登录页内嵌) 处理逻辑
# =========================================================
def _wait_login_turnstile_token(sb, timeout=30) -> bool:
    """等待后台生成真正的验证通过凭证 (Token)"""
    last_len = 0
    for _ in range(timeout):
        token_len = sb.execute_script('''
            var inp = document.querySelector('input[name="cf-turnstile-response"]');
            return inp ? inp.value.length : 0;
        ''')
        if token_len > 20: 
            print(f"    ✅ Turnstile token 已生成 (长度 {token_len})")
            return True
        if token_len != last_len:
            last_len = token_len
        time.sleep(1)
    print(f"    ❌ 超时未得到 token，最终长度 {last_len}")
    return False

def handle_login_turnstile(sb, account_index) -> bool:
    """处理登录页面的内嵌验证码"""
    try:
        for _ in range(15):
            if sb.execute_script("return !!document.querySelector('.cf-turnstile');"):
                break
            time.sleep(1)
        else:
            print("    ℹ️ 页面上未检测到 Turnstile 组件，无需验证。")
            return True

        print("    🧩 发现 Turnstile 组件，准备点击...")
        clicked = sb.execute_script('''
            var cb = document.querySelector('.cf-turnstile input[type="checkbox"]');
            if(cb){ cb.click(); return true; }
            return false;
        ''')
        
        if not clicked:
            sb.execute_script('''
                var label = document.querySelector('.cf-turnstile label');
                if(label) label.click();
            ''')

        if not clicked:
            try:
                sb.uc_gui_click_captcha()
            except Exception as e:
                print(f"    ⚠️ uc_gui_click_captcha 失败: {e}")

        print("    ⏳ 等待 Turnstile 完成验证...")
        if _wait_login_turnstile_token(sb, timeout=30):
            take_screenshot(sb, account_index, "03-2_内嵌验证_成功")
            return True

        print("    ❌ Turnstile 验证超时失败")
        take_screenshot(sb, account_index, "03-2_内嵌验证_失败")
        return False
    except Exception as e:
        print(f"    ⚠️ 处理登录 Turnstile 发生异常: {e}")
        return False

# =========================================================
# 单个账号的处理流程（将以前的主流程封装成了函数）
# =========================================================
def process_account(account_index, username, password):
    """
    处理单个账号的登录测试
    :param account_index: 账号的序号（例如 1, 2, 3...）
    :param username: 用户名/邮箱
    :param password: 密码
    """
    print(f"\n[{account_index}] 🚀 开始启动浏览器测试账号...")
    
    # 每次调用这个函数，都会启动一个全新的浏览器，保证各个账号环境隔离
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
                return # 拦截失败，直接退出当前账号测试，进入下一个账号
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

        # --- 步骤 3：处理页面内嵌的人机验证 (Turnstile) ---
        print(f"[{account_index}] 步骤 3: 处理 CF 内嵌验证...")
        take_screenshot(sb, account_index, "03-1_验证前的状态")
        turnstile_success = handle_login_turnstile(sb, account_index)
        if not turnstile_success:
            print(f"[{account_index}] ⚠️ 内嵌验证可能未成功，尝试强行点击登录...")

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
        time.sleep(4)
        take_screenshot(sb, account_index, "05_最终应用页")
        print(f"[{account_index}] 🎉 当前账号测试流程执行完毕！")

# =========================================================
# 程序入口：解析配置并循环执行
# =========================================================
def main():
    # 1. 从环境变量获取多账号配置字符串
    # 预期的格式: 账号1:密码1,账号2:密码2
    accounts_str = os.environ.get("TEST_ACCOUNTS", "")
    
    if not accounts_str:
        print("❌ 错误：环境变量 TEST_ACCOUNTS 为空！请检查 GitHub Secrets。")
        return

    # 2. 解析这段字符串，把它变成一个列表
    # 结果例子: [("账号1", "密码1"), ("账号2", "密码2")]
    account_list = []
    
    # 按照逗号分割字符串，得到每一个 "账号:密码"
    for pair in accounts_str.split(','):
        pair = pair.strip() # 去除可能多余的空格
        if not pair:
            continue
            
        # 按照冒号分割账号和密码
        if ':' in pair:
            # 只分割第一次出现的冒号，防止密码里本身带有冒号
            username, password = pair.split(':', 1) 
            account_list.append((username.strip(), password.strip()))
        else:
            print(f"⚠️ 警告: 发现格式不对的账号配置跳过: {pair}")

    print(f"✅ 成功解析到 {len(account_list)} 个待测试账号。")

    # 3. 开始循环测试每一个账号
    # enumerate(account_list, 1) 会给每个账号一个从 1 开始的序号
    for index, (username, password) in enumerate(account_list, 1):
        print("=" * 60)
        # 为了保护隐私，在日志里给邮箱打个小码 (比如 admin@xxx.com)
        masked_user = username
        if "@" in username:
            parts = username.split("@")
            masked_user = parts[0][:2] + "***@" + parts[1]
            
        print(f"▶ 正在处理第 {index} 个账号: {masked_user}")
        
        try:
            # 调用我们上面写好的处理单个账号的函数
            process_account(index, username, password)
        except Exception as e:
            print(f"❌ 处理账号 {masked_user} 时发生严重异常: {e}")
            
        # 如果还有下一个账号，休息 5 秒钟再继续，避免被目标网站拦截过快请求
        if index < len(account_list):
            print(f"等待 5 秒后继续测试下一个账号...")
            time.sleep(5)

    print("\n🎊 全部账号测试完毕！请下载 artifacts 查看所有截图。")

if __name__ == "__main__":
    main()
