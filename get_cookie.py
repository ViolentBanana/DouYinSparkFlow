import json
from playwright.sync_api import sync_playwright

def main():
    print("========================================")
    print("抖音 Cookie 一键提取工具")
    print("========================================")
    unique_id = input("请输入此账号的唯一标识 (例如: account1, 纯英文字母/数字即可): ").strip()
    if not unique_id:
        unique_id = "default_account"
        
    print(f"\n👉 即将打开浏览器...")
    print("👉 请在弹出的浏览器中完成登录（建议使用 App 扫码登录）。")
    print("========================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        page.goto("https://www.douyin.com/chat")
        
        input("\n[等待中] 登录成功（看到聊天界面）后，在此处按下 【回车键(Enter)】 继续提取 Cookie...")
        
        cookies = context.cookies()
        
        if not cookies:
            print("❌ 未获取到 Cookie，可能尚未登录或页面未完成加载！")
            return
            
        # 生成单行 JSON，去除了多余空格和换行，极大方便直接粘贴到 .env 或 GitHub Secrets 中
        cookies_json_min = json.dumps(cookies, separators=(',', ':'))
        env_key = f"COOKIES_{unique_id.upper()}"
        
        print("\n" + "="*50)
        print("🎉 Cookie 提取成功！请根据下方提示进行复制粘贴：")
        print("="*50)
        
        task_json = {
            "username": "在此填入账号备注",
            "unique_id": unique_id,
            "targets": ["目标好友名称1", "目标好友名称2"]
        }
        task_str = json.dumps([task_json], ensure_ascii=False)
        
        print("\n【方案一：本地 .env 配置】")
        print("1. 修改 .env 中的 TASKS 变量:")
        print(f"TASKS={task_str}")
        print("\n2. 将 Cookie 追加到 .env 文件末尾 (直接复制下面这一长行):")
        print(f"{env_key}={cookies_json_min}")
        
        print("\n" + "="*50)
        print("【方案二：GitHub Actions 部署配置】")
        print("1. 在 GitHub Secrets 中新建或更新 Secret: TASKS")
        print(f"内容: {task_str}")
        
        print(f"\n2. 在 GitHub Secrets 中新建或更新 Secret: {env_key}")
        print(f"内容: (双击全选复制下面这行)")
        print(f"{cookies_json_min}")
        print("="*50)
        
        print("\n✅ 操作结束，您可以关闭本窗口。")
        browser.close()

if __name__ == "__main__":
    main()
