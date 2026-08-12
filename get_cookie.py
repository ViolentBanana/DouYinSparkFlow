import json
import os
import re
from playwright.sync_api import sync_playwright

def update_env_file(env_key, cookies_json_min):
    env_file = ".env"
    if not os.path.exists(env_file):
        with open(env_file, "w", encoding="utf-8") as f:
            f.write(f"{env_key}='{cookies_json_min}'\n")
        return True

    with open(env_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 检查是否已存在该键
    key_exists = False
    for i, line in enumerate(lines):
        if line.startswith(f"{env_key}="):
            lines[i] = f"{env_key}='{cookies_json_min}'\n"
            key_exists = True
            break
            
    if not key_exists:
        # 如果文件最后一行没有换行符，先加个换行符
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{env_key}='{cookies_json_min}'\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return True

def get_unique_id_from_env():
    env_file = ".env"
    if not os.path.exists(env_file):
        return None
    
    with open(env_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    match = re.search(r'^TASKS=(.*)$', content, re.MULTILINE)
    if match:
        try:
            tasks_str = match.group(1).strip()
            # 移除可能存在的外层引号
            if tasks_str.startswith("'") and tasks_str.endswith("'"):
                tasks_str = tasks_str[1:-1]
            tasks = json.loads(tasks_str)
            if tasks and isinstance(tasks, list):
                return tasks[0].get("unique_id")
        except Exception:
            pass
    return None

def main():
    print("========================================")
    print("抖音 Cookie 一键提取工具")
    print("========================================")
    
    default_id = get_unique_id_from_env()
    
    if default_id:
        print(f"检测到 .env 中 TASKS 配置的 unique_id 为: {default_id}")
        unique_id = input(f"请输入此账号的唯一标识 (直接回车默认使用 {default_id}): ").strip()
        if not unique_id:
            unique_id = default_id
    else:
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
            
        cookies_json_min = json.dumps(cookies, separators=(',', ':'))
        env_key = f"COOKIES_{unique_id.upper()}"
        
        # 自动写入 .env
        update_env_file(env_key, cookies_json_min)
        
        print("\n" + "="*50)
        print("🎉 Cookie 提取成功！")
        print("="*50)
        
        print(f"\n✅ 已经自动将 {env_key} 更新/追加到 .env 文件中，您可以直接运行 python main.py 测试了！")
        
        task_json = {
            "username": "在此填入账号备注",
            "unique_id": unique_id,
            "targets": ["目标好友名称1", "目标好友名称2"]
        }
        task_str = json.dumps([task_json], ensure_ascii=False)
        
        print("\n" + "="*50)
        print("【如果是 GitHub Actions 部署，请复制以下内容】")
        print("1. Secret名称: TASKS")
        print(f"内容: {task_str}")
        print(f"\n2. Secret名称: {env_key}")
        print(f"内容: (双击全选复制下面这行)")
        print(f"{cookies_json_min}")
        print("="*50)
        
        print("\n✅ 操作结束，您可以关闭本窗口。")
        browser.close()

if __name__ == "__main__":
    main()
