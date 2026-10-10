import traceback
from utils.logger import setup_logger
from utils.config import get_config, get_userData
from utils import norm
from core.msg_builder import build_message, build_message_with_openai
from core.browser import get_browser
from playwright.sync_api import Response
import time

config = get_config()
userData = get_userData()
logger = setup_logger(level=config.get("logLevel", "Info"))
matchMode = config.get("matchMode", "nickname")
userIDDict = {}

CONVERSATION_ITEM_SELECTOR = ".conversationConversationItemwrapper"
CONVERSATION_TITLE_SELECTOR = ".conversationConversationItemtitle"
CONVERSATION_LIST_SELECTOR = ".conversationConversationListwrapper"
CHAT_EDITOR_SELECTOR = ".messageEditorimChatEditorContainer"


def handle_response(response: Response):
    """
    只监听你要的那个接口响应
    """
    global userIDDict
    # 精准匹配目标接口 URL
    if "aweme/v1/web/im/user/info" in response.url:
        # print(f"URL: {response.url}")
        # print(f"状态码: {response.status}")
        try:
            # 获取接口返回的 JSON 数据（就是你在 Network 里看到的内容）
            json_data = response.json()
            # print("\n📦 响应 JSON 数据：")
            # print(json.dumps(json_data, indent=4, ensure_ascii=False))
            for item in json_data.get("data", []):
                short_id = item.get("short_id")
                unique_id = item.get("unique_id")
                sec_uid = item.get("sec_uid", "")
                nickname = norm(item.get("nickname"))
                remark_name = norm(item.get("remark_name", nickname))
                userIDDict[remark_name] = [short_id, unique_id, sec_uid, nickname, remark_name]
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)
            last = tb[-1]
            print(f"解析响应失败: {e}")
            print(f"文件: {last.filename}, 行号: {last.lineno}, 函数: {last.name}")


def retry_operation(name, operation, retries=3, delay=2, *args, **kwargs):
    """
    通用的重试逻辑
    :param name: 操作名称（用于日志记录）
    :param operation: 要执行的异步操作
    :param retries: 最大重试次数
    :param delay: 每次重试之间的延迟（秒）
    :param args: 传递给操作的参数
    :param kwargs: 传递给操作的关键字参数
    """
    for attempt in range(retries):
        try:
            return operation(*args, **kwargs)
        except Exception as e:
            if attempt < retries - 1:
                logger.warning(f"{name} 失败，正在重试第 {attempt + 1} 次，错误：{e}")
                time.sleep(delay)
            else:
                logger.error(f"{name} 失败，已达到最大重试次数，错误：{e}")
                raise

def checkTargetName(targetName, targets):
    """检查targetName是否为目标
    """
    
    targetSymbol = None
    
    targetName = norm(targetName)
    
    if targetName in userIDDict:
        matched = next((v for v in userIDDict[targetName] if v and v in targets), None)
        if matched is not None:
            targetSymbol = matched
    else:
        if targetName in targets:
            targetSymbol = targetName
    return targetSymbol


def scroll_and_select_user(page, username, targets):
    """尝试滚动并查找用户名"""
    # 定义目标元素和滚动容器的选择器
    target_selector = CONVERSATION_ITEM_SELECTOR
    scrollable_friends_selector = CONVERSATION_LIST_SELECTOR

    # [修复] 使用模糊匹配 no-more-tip- 前缀，不再依赖精确哈希后缀
    # 同时增加文本匹配作为兜底
    # no_more_selector = 'xpath=//div[contains(@class, "no-more-tip-")]'
    # loading_selector = 'xpath=//div[contains(@class, "semi-spin")]'

    logger.debug(f"账号 {username} 开始查找目标好友列表")
    logger.debug(f"账号 {username} 目标好友列表: {targets}")

    try:
        # 预先等待列表容器加载完成，设置 15 秒超时，避免默认的 120 秒死等
        page.wait_for_selector(scrollable_friends_selector, timeout=15000)
    except Exception as e:
        error_msg = f"账号 {username} 未能加载好友列表容器，可能页面未正确加载或选择器失效: {e}"
        logger.error(error_msg)
        # === 修复：失败时截图 + 主动发飞书 ===
        try:
            import os
            from datetime import datetime
            screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
            os.makedirs(screenshot_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            fail_shot = os.path.join(screenshot_dir, f"friend_list_fail_{ts}.png")
            page.screenshot(path=fail_shot, full_page=False)
            logger.error(f"好友列表加载失败截图: {fail_shot}")
        except Exception as se:
            logger.error(f"截图失败: {se}")
            fail_shot = None
        # 发飞书报警
        import subprocess
        alert_msg = f"🚨 抖音火花 - 好友列表加载失败\n\n账号: {username}\n目标: {targets}\nURL: {page.url}\n错误: {str(e)[:200]}"
        for attempt in range(1, 3):
            try:
                cmd = [
                    'openclaw', 'message', 'send',
                    '--channel', 'feishu',
                    '--target', 'ou_5e2c5ce15f2c29c6859f839d13cadc67',
                    '-m', alert_msg,
                ]
                if fail_shot:
                    cmd.extend(['--media', fail_shot])
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    logger.info(f"好友列表失败已报警 (第 {attempt} 次)")
                    break
                else:
                    logger.warning(f"飞书发送失败 ({attempt}/2): {result.stderr.strip()}")
            except Exception as fe:
                logger.warning(f"飞书异常 ({attempt}/2): {fe}")
        return

    found_targets = set()
    # [修改] 复制一份目标列表用于追踪进度
    remaining_targets = set(targets)

    # [修复] 新增：连续空滚动计数器（滚动后没有发现新好友的次数）
    empty_scroll_count = 0
    MAX_EMPTY_SCROLLS = 10  # 连续10次滚动没有新好友，认为到底了

    while True:
        # 查找所有目标元素
        target_elements = page.locator(target_selector).all()

        # [修复] 记录本轮循环前已发现的好友数，用于判断是否有新发现
        prev_found_count = len(found_targets)

        for element in target_elements:
            try:
                # 查找子元素 span，模糊匹配 class
                span = element.locator(CONVERSATION_TITLE_SELECTOR)
                targetName = span.inner_text()

                if targetName in found_targets:
                    continue  # 已处理过，跳过
                found_targets.add(targetName)

                logger.debug(f"账号 {username} 找到好友 {targetName}")
                
                targetSymbol = checkTargetName(targetName, targets)

                if targetSymbol:
                    element.click()
                    
                    yield targetSymbol

                    # [修改] 标记已找到，如果全找到了直接退出
                    if targetSymbol in remaining_targets:
                        remaining_targets.remove(targetSymbol)
                    if len(remaining_targets) == 0:
                        logger.debug(f"账号 {username} 所有目标好友均已找到，停止搜索")
                        return
                    break
            except Exception as e:
                traceback.print_exc()
        else:
            # [修复] 检查本轮是否有新好友被发现
            new_found = len(found_targets) > prev_found_count
            if new_found:
                empty_scroll_count = 0  # 有新发现，重置计数器
            else:
                empty_scroll_count += 1  # 无新发现，递增计数器

            # [修复] 状态检测逻辑（多重兜底）

            # # 1. 检查是否到底（"没有更多了" —— 使用模糊类名匹配）
            # if page.locator(no_more_selector).count() > 0:
            #     logger.info(f"账号 {username} 检测到'没有更多了'标志，已到达底部")
            #     if len(remaining_targets) > 0:
            #         logger.warning(
            #             f"账号 {username} 搜索结束，仍有以下好友未找到: {remaining_targets}"
            #         )
            #     break

            # 2. [修复] 检查连续空滚动次数，防止死循环
            if empty_scroll_count >= MAX_EMPTY_SCROLLS:
                logger.warning(
                    f"账号 {username} 连续 {MAX_EMPTY_SCROLLS} 次滚动未发现新好友，判定已到达底部"
                )
                if len(remaining_targets) > 0:
                    logger.warning(
                        f"账号 {username} 搜索结束，仍有以下好友未找到: {remaining_targets}"
                    )
                break

            # 3. 检查是否正在加载
            # if page.locator(loading_selector).count() > 0:
            #     logger.debug(f"账号 {username} 列表正在加载中 (Loading)...")
            #     time.sleep(1.5)  # 给加载留点时间
            #     # 不 break，继续去滚动以触发后续内容

            # 4. 滚动容器
            try:
                scrollable_element = page.locator(
                    scrollable_friends_selector
                ).element_handle(timeout=5000)
            except Exception as e:
                logger.error(f"账号 {username} 在滚动时无法获取容器元素，退出滚动: {e}")
                break

            if scrollable_element:
                # [修复] 记录滚动前的 scrollTop，用于检测是否真的滚动了
                scroll_top_before = page.evaluate(
                    "(element) => element.scrollTop", scrollable_element
                )

                page.evaluate(
                    "(element) => element.scrollTop += 800", scrollable_element
                )

                # [修复] 检测滚动后的 scrollTop
                time.sleep(0.3)
                scroll_top_after = page.evaluate(
                    "(element) => element.scrollTop", scrollable_element
                )

                if scroll_top_before == scroll_top_after:
                    # scrollTop 没有变化，说明已经到底了
                    empty_scroll_count += 2  # 加速判定到底
                    logger.debug(
                        f"账号 {username} scrollTop 未变化 ({scroll_top_before})，可能已到底 (空滚动计数: {empty_scroll_count}/{MAX_EMPTY_SCROLLS})"
                    )
                else:
                    logger.debug(
                        f"账号 {username} 滚动好友列表以加载更多好友 (scrollTop: {scroll_top_before} -> {scroll_top_after})"
                    )

                time.sleep(1.5)
            else:
                logger.error(f"账号 {username} 未找到滚动容器，退出")
                break


def do_user_task(browser, username, cookies, targets):
    context = browser.new_context()  # 每个任务使用独立的上下文
    context.set_default_navigation_timeout(
        config["browserTimeout"]
    )  # 设置导航超时时间为 120 秒
    context.set_default_timeout(
        config["browserTimeout"]
    )  # 设置所有操作的默认超时时间为 120 秒

    page = context.new_page()

    page.on("response", handle_response)  # 监听响应，收集好友完整信息用于匹配

    # 注入 Cookie
    context.add_cookies(cookies)

    # 打开抖音网页聊天页面
    retry_operation(
        "打开抖音网页聊天页面",
        page.goto,
        retries=config["taskRetryTimes"],
        delay=5,
        url="https://www.douyin.com/chat",
    )

    time.sleep(5)  # 等待5秒让过可能存在的弹窗

    # ============ Cookie 过期检测（真实 DOM 检测）============
    # 问题：之前只检查 URL，cookie 失效时 URL 还是 douyin.com/chat（登录弹窗覆盖页面），
    # 导致检测不生效。
    # 修复：同时检查 1) URL 2) 实际登录态元素 (好友列表 / 聊天输入框)。
    current_url = page.url
    login_indicators = [
        'text=扫码登录',                      # 二维码登录提示
        'text=登录到抖言',                       # 扫话“登录到抖言”
        'text=未登录',                          # 未登录提示
        'text=请先登录',                         # 请先登录
        'canvas',                              # QR 码 canvas 元素
        '[class*="login"]',                   # 任何含 login 的 class
        '[class*="qrcode"]',                  # 任何含 qrcode 的 class
    ]
    is_login_modal = False
    for sel in login_indicators:
        try:
            if page.locator(sel).count() > 0:
                is_login_modal = True
                logger.debug(f"检测到登录弹窗元素: {sel}")
                break
        except Exception:
            pass

    # 实际登录态验证：能否找到好友列表 或 聊天输入框
    is_logged_in = False
    login_state_selectors = [
        CONVERSATION_LIST_SELECTOR,   # 好友列表容器
        CHAT_EDITOR_SELECTOR,         # 聊天输入框
    ]
    for sel in login_state_selectors:
        try:
            if page.locator(sel).count() > 0:
                is_logged_in = True
                logger.debug(f"找到登录态元素: {sel}")
                break
        except Exception:
            pass

    # 三重判断：URL 不对 / 有登录弹窗 / 都没拿到登录态元素 → Cookie 过期
    if ("douyin.com/chat" not in current_url) or is_login_modal or (not is_logged_in):
        import os, subprocess
        from datetime import datetime
        screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
        os.makedirs(screenshot_dir, exist_ok=True)
        # 用时间戳命名，保留历史
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        screenshot_path = os.path.join(screenshot_dir, f"douyin_qrcode_{ts}.png")
        try:
            page.screenshot(path=screenshot_path, full_page=True)
        except Exception as e:
            logger.error(f"截图失败: {e}")
            screenshot_path = None

        # 记录原因
        reasons = []
        if "douyin.com/chat" not in current_url:
            reasons.append(f"URL={current_url}")
        if is_login_modal:
            reasons.append("页面出现登录弹窗")
        if not is_logged_in:
            reasons.append("未找到登录态元素（好友列表/聊天输入框）")
        reason_str = "; ".join(reasons)
        logger.warning(f"账号 {username} Cookie 已过期，{reason_str}，截图: {screenshot_path}")

        # 写本地标记文件（连飞书都发不出去时，cron 下一轮可以读到）
        try:
            flag_path = os.path.join(screenshot_dir, "NEED_COOKIE_UPDATE.flag")
            with open(flag_path, "w") as f:
                f.write(f"{datetime.now().isoformat()}\nusername={username}\nreasons={reason_str}\n")
        except Exception as e:
            logger.error(f"写 flag 失败: {e}")

        # 发飞书通知（重试2次）
        alert_text = (
            f'账号 {username} Cookie 已过期\n\n'
            f'原因: {reason_str}\n'
            f'时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
            f'处理: 运行 python3 auto_get_cookie.py 扫码更新 🐟'
        )
        for attempt in range(1, 3):
            try:
                cmd = [
                    'openclaw', 'message', 'send',
                    '--channel', 'feishu',
                    '--target', 'ou_5e2c5ce15f2c29c6859f839d13cadc67',
                    '-m', alert_text,
                ]
                if screenshot_path:
                    cmd.extend(['--media', screenshot_path])
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    logger.info(f"飞书通知已发送 (第 {attempt} 次)")
                    # 发成功后删 flag（避免重复报警）
                    try:
                        os.remove(flag_path)
                    except Exception:
                        pass
                    break
                else:
                    logger.warning(f"飞书发送失败 (第 {attempt}/2 次): {result.stderr.strip()}")
            except Exception as e:
                logger.warning(f"飞书发送异常 (第 {attempt}/2 次): {e}")
        context.close()
        return
    logger.debug(f"账号 {username} 页面已加载，Cookie 有效，URL={current_url}")
    logger.debug(f"账号 {username} 页面已加载，Cookie 有效，URL={current_url}")

    logger.debug(f"账号 {username} 开始发送消息")
    # 滚动并选择用户
    send_failures = []  # 记录发送失败的账号
    for username in scroll_and_select_user(page, username, targets):
        target = username  # 目标好友昵称
        logger.debug(f"账号 {target} 已选中好友 {target} 发送消息")
        # 等待聊天输入框元素加载完成，使用更稳定的属性选择器
        chat_input_selector = CHAT_EDITOR_SELECTOR
        page.wait_for_selector(chat_input_selector, timeout=config["browserTimeout"])
        chat_input = page.locator(chat_input_selector)

        # 在 chat-input-dccKiL 中输入内容
        message = build_message()
        for line in message.split("\\n"):
            chat_input.type(line)  # 输入每一行
            # 如果不是最后一行，模拟 Shift+Enter 插入换行
            if line != message.split("\\n")[-1]:
                chat_input.press("Shift+Enter")  # 模拟 Shift+Enter 插入换行

        logger.debug(f"账号 {target} 准备发送消息给好友 {target}：\n\t{message}")
        # 实际发送：按回车
        chat_input.press("Enter")

        # === 关键修复：验证消息是否真的出现 ===
        time.sleep(3)  # 等待消息出现

        # 验证逻辑：检查聊天记录中是否出现今日消息的关键词
        # 消息模板含 "[盖瑞]今日火花[加一]" - 截取作为验证
        verify_keyword = "今日火花"  # 消息中必有这个串
        try:
            # 获取聊天历史区域的内容（页面 body 文本）
            page_text = page.locator('body').inner_text(timeout=5000)
            sent_verified = verify_keyword in page_text
        except Exception as e:
            logger.warning(f"验证异常: {e}")
            sent_verified = False

        if sent_verified:
            logger.info(f"✅ 账号 {target} 消息已成功发送（验证通过）")
        else:
            # 重试：点发送按钮（不只靠回车）
            logger.warning(f"⚠️ 账号 {target} 验证未通过，尝试点发送按钮...")
            try:
                send_btn_selectors = [
                    'button:has-text("发送")',
                    '[class*="send"]:not([class*="sender"])',
                    '[class*="sendBtn"]',
                    '[data-testid="send"]',
                ]
                for sel in send_btn_selectors:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.click(timeout=2000)
                        logger.info(f"   点发送按钮: {sel}")
                        break
                time.sleep(3)
                page_text = page.locator('body').inner_text(timeout=5000)
                sent_verified = verify_keyword in page_text
            except Exception as e:
                logger.error(f"重试点击发送按钮异常: {e}")
                sent_verified = False

        if sent_verified:
            logger.info(f"✅ 账号 {target} 重试后成功")
        else:
            # 验证彻底失败
            error_msg = f"❌ 账号 {target} 火花发送失败（验证未通过）"
            logger.error(error_msg)
            send_failures.append({"username": target, "message": message})
            # 截图现场
            try:
                fail_shot = os.path.join(screenshot_dir, f"send_fail_{target}_{int(time.time())}.png")
                page.screenshot(path=fail_shot, full_page=False)
                logger.error(f"失败截图: {fail_shot}")
            except:
                pass

    context.close()  # 任务完成后关闭上下文

    # === 失败汇总：如果有发送失败，发飞书报警 ===
    if send_failures:
        alert_msg = f"🚨 抖音火花续火失败报告 ({len(send_failures)} 个账号)\n\n"
        for f in send_failures:
            alert_msg += f"• 账号 {f['username']}: 消息未送出\n"
        alert_msg += "\n请检查：1) Cookie 2) 抖音 UI 变更 3) 网络"
        logger.error(alert_msg)
        # 主动发飞书
        for attempt in range(1, 3):
            try:
                result = subprocess.run(
                    [
                        'openclaw', 'message', 'send',
                        '--channel', 'feishu',
                        '--target', 'ou_5e2c5ce15f2c29c6859f839d13cadc67',
                        '-m', alert_msg,
                    ],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0:
                    logger.info(f"失败报告已发飞书 (第 {attempt} 次)")
                    break
                else:
                    logger.warning(f"飞书发送失败 (第 {attempt}/2 次): {result.stderr.strip()}")
            except Exception as e:
                logger.warning(f"飞书发送异常 (第 {attempt}/2 次): {e}")


def runTasks():
    playwright, browser = get_browser()
    try:
        # 检查是否启用多任务和任务数量
        # 创建信号量以限制并发任务数量
        logger.info("开始执行任务")
        logger.debug(f"当前配置如下：")
        logger.debug(f"消息模板: {config.get('messageTemplate', '未找到消息模板')}")
        logger.debug(f"一言类型: {config['hitokotoTypes']}")
        for user in userData:
            logger.debug(
                f"用户: {user.get('username', '未知用户')}, 目标好友: {user['targets']}"
            )

        for user in userData:
            cookies = user["cookies"]
            targets = user["targets"]
            username = user.get("username", "未知用户")
            logger.info(f"开始处理账号 {username}")
            # 创建任务
            do_user_task(browser, username, cookies, targets)
            logger.info(f"账号 {username} 任务完成")
    except Exception as e:
        # === 修复：顶层异常也发飞书，不再静默 ===
        error_msg = f"🚨 抖音火花 - runTasks 顶层崩溃\n\n错误: {type(e).__name__}: {str(e)[:300]}"
        logger.error(f"runTasks 顶层异常: {e}", exc_info=True)
        try:
            import subprocess
            result = subprocess.run(
                [
                    'openclaw', 'message', 'send',
                    '--channel', 'feishu',
                    '--target', 'ou_5e2c5ce15f2c29c6859f839d13cadc67',
                    '-m', error_msg,
                ],
                capture_output=True, text=True, timeout=30,
            )
            logger.info(f"runTasks 崩溃已发飞书: rc={result.returncode}")
        except Exception as fe:
            logger.error(f"连飞书都发不出去: {fe}")
    finally:
        # 关闭浏览器实例
        try:
            browser.close()
        except:
            pass
        try:
            playwright.stop()
        except:
            pass
