"""自动获取抖音登录后的 Cookie。
浏览器打开后用户扫码登录，脚本自动检测登录成功并提取 cookies 写入 .env。
"""
import json, os, sys, time
from playwright.sync_api import sync_playwright

ENV_KEY = "COOKIES_84606466778"

def update_env(cookies_json):
    env_path = ".env"
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write(f"{ENV_KEY}='{cookies_json}'\n")
        return
    with open(env_path, "r") as f:
        lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{ENV_KEY}="):
            lines[i] = f"{ENV_KEY}='{cookies_json}'\n"
            found = True
            break
    if not found:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{ENV_KEY}='{cookies_json}'\n")
    with open(env_path, "w") as f:
        f.writelines(lines)

def main():
    print("="*50)
    print("自动获取抖音 Cookie")
    print("="*50)

    # 用独立 profile 目录，避免和用户 Chrome 冲突
    profile_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome-AutoCookie")
    os.makedirs(profile_dir, exist_ok=True)

    with sync_playwright() as p:
        # 用 launch_persistent_context 才能指定 user-data-dir
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ],
        )
        page = context.new_page()
        page.goto("https://www.douyin.com/chat")

        print("\n✅ Chrome 已打开，请用抖音 App 扫码登录")
        print("⏳ 脚本会自动检测登录状态...\n")

        # 自动检测登录成功：cookies 中出现 sessionid 或 uid_tt，或 URL 变化
        max_wait = 180  # 最多等 3 分钟
        start = time.time()
        while time.time() - start < max_wait:
            try:
                cookies = context.cookies()
                names = {c["name"] for c in cookies}
                if "sessionid" in names or "uid_tt" in names:
                    print(f"🎉 检测到登录成功！({time.time()-start:.1f}s)")
                    cookies_json = json.dumps(cookies, separators=(",", ":"))
                    update_env(cookies_json)
                    print(f"✅ 已写入 {len(cookies)} cookies 到 .env ({ENV_KEY})")
                    break
            except Exception as e:
                pass
            time.sleep(1)
        else:
            print("❌ 超时未检测到登录成功")

        context.close()

if __name__ == "__main__":
    main()
