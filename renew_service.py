import os
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- 全局配置 ---
HIDENCLOUD_COOKIE = os.environ.get('HIDENCLOUD_COOKIE')
HIDENCLOUD_EMAIL = os.environ.get('HIDENCLOUD_EMAIL')
HIDENCLOUD_PASSWORD = os.environ.get('HIDENCLOUD_PASSWORD')

# 目标网页 URL
BASE_URL = "https://dash.hidencloud.com"
LOGIN_URL = f"{BASE_URL}/auth/login"
SERVICE_URL = f"{BASE_URL}/service/71309/manage"
RENEW_API_URL = f"{BASE_URL}/service/71309/renew" 

# Cookie 名称
COOKIE_NAME = "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d"

def log(message):
    """打印带时间戳的日志"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def login(page):
    """
    处理登录逻辑。
    1. 优先尝试使用 Cookie 登录。
    2. 如果 Cookie 失效或不存在，则使用账号密码进行登录。
    """
    log("开始登录流程...")

    # --- 方案一：Cookie 登录 ---
    if HIDENCLOUD_COOKIE:
        log("检测到 HIDENCLOUD_COOKIE，尝试使用 Cookie 登录。")
        try:
            page.context.add_cookies([{
                'name': COOKIE_NAME, 'value': HIDENCLOUD_COOKIE,
                'domain': 'dash.hidencloud.com', 'path': '/',
                'expires': int(time.time()) + 3600 * 24 * 365,
                'httpOnly': True, 'secure': True, 'sameSite': 'Lax'
            }])
            log("Cookie 已设置。正在访问服务管理页面...")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)

            if "auth/login" in page.url:
                log("Cookie 登录失败或会话已过期，将回退到账号密码登录。")
                page.context.clear_cookies()
            else:
                log("✅ Cookie 登录成功！")
                return True
        except Exception as e:
            log(f"使用 Cookie 访问时发生错误: {e}")
            log("将回退到账号密码登录。")
            page.context.clear_cookies()
    else:
        log("未提供 HIDENCLOUD_COOKIE，直接使用账号密码登录。")

    # --- 方案二：账号密码登录 ---
    if not HIDENCLOUD_EMAIL or not HIDENCLOUD_PASSWORD:
        log("❌ 错误: Cookie 无效/未提供，且未提供邮箱和密码。无法继续登录。")
        return False

    log("正在尝试使用邮箱和密码登录...")
    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=60000)
        log("登录页面已加载。")

        page.fill('input[name="email"]', HIDENCLOUD_EMAIL)
        page.fill('input[name="password"]', HIDENCLOUD_PASSWORD)
        log("邮箱和密码已填写。")

        log("正在处理 Cloudflare Turnstile 人机验证...")
        turnstile_frame = page.frame_locator('iframe[src*="challenges.cloudflare.com"]')
        checkbox = turnstile_frame.locator('input[type="checkbox"]')
        
        checkbox.wait_for(state="visible", timeout=30000)
        checkbox.click()
        log("已点击人机验证复选框，等待验证结果...")
        
        page.wait_for_function(
            "() => document.querySelector('[name=\"cf-turnstile-response\"]') && document.querySelector('[name=\"cf-turnstile-response\"]').value",
            timeout=60000
        )
        log("✅ 人机验证成功！")

        page.click('button[type="submit"]:has-text("Sign in to your account")')
        log("已点击登录按钮，等待页面跳转...")

        page.wait_for_url(f"{BASE_URL}/dashboard", timeout=60000)

        if "auth/login" in page.url:
            log("❌ 账号密码登录失败，请检查凭据是否正确。")
            page.screenshot(path="login_failure.png")
            return False

        log("✅ 账号密码登录成功！")
        return True
    except PlaywrightTimeoutError as e:
        log(f"❌ 登录过程中超时: {e}")
        page.screenshot(path="login_timeout_error.png")
        return False
    except Exception as e:
        log(f"❌ 登录过程中发生未知错误: {e}")
        page.screenshot(path="login_general_error.png")
        return False

def renew_service(page):
    """执行续费流程"""
    try:
        log("开始执行续费任务...")
        if page.url != SERVICE_URL:
            log(f"当前不在目标页面，正在导航至: {SERVICE_URL}")
            page.goto(SERVICE_URL, wait_until="networkidle", timeout=60000)
        
        log("服务管理页面已加载。")

        # +++ 解决方案：(方案十四) 完美复刻API请求 +++
        
        # 步骤 1: 从页面的 meta 标签中抓取 CSRF 令牌
        log("步骤 1: 正在从页面抓取 CSRF 令牌...")
        csrf_token_locator = page.locator('meta[name="csrf-token"]')
        csrf_token = csrf_token_locator.get_attribute('content')

        if not csrf_token:
            log("❌ 错误：未能从 <meta name=\"csrf-token\"> 标签中找到 CSRF 令牌。")
            page.screenshot(path="csrf_token_not_found.png")
            raise Exception("CSRF Token not found in meta tag.")
            
        log(f"✅ 成功抓取到 CSRF 令牌。 (令牌开头: {csrf_token[:6]}...)")

        # 步骤 2: 准备 "完美" 的请求头和表单数据
        
        # +++ 语法错误修复：将外层 " 改为 ' +++
        log('步骤 2: 绕过UI，准备发送 "完美复刻" 的POST请求...')
        
        # 准备请求头 (Headers)
        headers = {
            'X-CSRF-TOKEN': csrf_token,
            'Referer': SERVICE_URL, # 添加 Referer
            'Accept': 'text/vnd.turbo-stream.html, text/html, application/xhtml+xml' # 模拟 Turbo 请求
        }

        # 准备表单数据 (Form Data / Payload)
        form_data = {
            '_token': csrf_token, # 在正文中也需要令牌
            'days': '7'          # 在正文中指定 '7' 天
        }

        response = page.request.post(
            RENEW_API_URL,
            headers=headers,
            form=form_data,      # <--- 关键修改：使用 'form' 来发送 'application/x-www-form-urlencoded'
            fail_on_status_code=False
        )
        
        log(f"API 响应状态: {response.status}")

        # 检查是否是我们预期的 302 Found
        if response.status == 302:
            invoice
