import os
import time
import json
import urllib.parse
import html
import requests
# 引入 SeleniumBase 高级过盾包
from seleniumbase import SB

SERVER_URL = os.getenv("ICEHOST_SERVER_URL")
ICEHOST_COOKIES = os.getenv("ICEHOST_COOKIES")
GITHUB_EVENT_NAME = os.getenv("GITHUB_EVENT_NAME", "")

def send_tg_notification(message, photo_path=None):
    """发送结果和截图至 Telegram 并详细输出返回结果"""
    token = (os.getenv("TG_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TG_CHAT_ID") or "").strip()
    if not token or not chat_id:
        print(f"⚠️ 未配置完整的 TG 变量 (TG_BOT_TOKEN: {'已设置' if token else '未配置'}, TG_CHAT_ID: {'已设置' if chat_id else '未配置'})，跳过发送 TG 推送。")
        return

    # 1. 发送文本消息
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        resp = requests.post(url, json=payload, timeout=20)
        if resp.status_code == 200:
            print("✅ TG 状态文本通知发送成功。")
        else:
            print(f"❌ TG 状态通知发送失败！HTTP {resp.status_code}，响应: {resp.text}")
    except Exception as e:
        print(f"❌ 发送 TG 消息网络异常: {e}")

    # 2. 发送截图
    if photo_path and os.path.exists(photo_path):
        try:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            with open(photo_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": chat_id, "caption": "IceHost 实时画面"}
                resp_photo = requests.post(url, data=data, files=files, timeout=30)
                if resp_photo.status_code == 200:
                    print("✅ TG 截图发送成功。")
                else:
                    print(f"❌ TG 截图发送失败！HTTP {resp_photo.status_code}，响应: {resp_photo.text}")
        except Exception as e:
            print(f"❌ 发送 TG 截图网络异常: {e}")

def run():
    if not SERVER_URL:
        print("错误: 缺少 ICEHOST_SERVER_URL 环境变量")
        return

    # 1. 启动 SeleniumBase 并开启 UC 免密/防检测模式与 Xvfb 虚拟桌面 (xvfb=True)
    with SB(uc=True, xvfb=True) as sb:
        print(f"正在访问 IceHost 面板: {SERVER_URL}")
        # 使用 UC 专属重连模式访问，能极大缓解首屏 Cloudflare 阻断
        sb.uc_open_with_reconnect(SERVER_URL, reconnect_time=8)
        sb.sleep(5)

        # 2. 注入 Cookies（已升级：智能兼容 JSON 或纯文本格式）
        if ICEHOST_COOKIES:
            try:
                cookies_to_add = []
                raw_cookies_str = ICEHOST_COOKIES.strip()

                # 尝试一：如果 Secret 填的是标准的 JSON 格式
                try:
                    raw_data = json.loads(raw_cookies_str)
                    if isinstance(raw_data, list):
                        cookies_to_add = raw_data
                    elif isinstance(raw_data, dict):
                        cookies_to_add = raw_data.get("cookies", [])
                    print("检测到 JSON 格式 Cookie，正在解析...")
                
                # 尝试二：如果解析失败，说明填的是纯文本
                except json.JSONDecodeError:
                    print("检测到纯文本 Cookie 格式，正在自动提取并生成标准字段...")
                    
                    # 提取真正的 Token 字符串值
                    token_value = raw_cookies_str
                    if "icehostpl_session=" in token_value:
                        token_value = token_value.split("icehostpl_session=")[1].split(";")[0]
                    elif "XSRF-TOKEN=" in token_value:
                        token_value = token_value.split("XSRF-TOKEN=")[1].split(";")[0]
                    
                    token_value = token_value.strip()

                    # 最稳妥策略：自动为 Selenium 生成两个核心的 Cookie 字典
                    cookies_to_add = [
                        {"name": "icehostpl_session", "value": token_value, "domain": "dash.icehost.pl"},
                        {"name": "XSRF-TOKEN", "value": token_value, "domain": "dash.icehost.pl"}
                    ]

                # 统一执行转换与注入
                for c in cookies_to_add:
                    raw_value = c["value"]
                    decoded_value = urllib.parse.unquote(raw_value)
                    
                    cookie_dict = {
                        "name": c["name"],
                        "value": decoded_value,
                        "domain": c.get("domain", "dash.icehost.pl"),
                        "path": c.get("path", "/"),
                        "secure": c.get("secure", True)
                    }
                    if "sameSite" in c:
                        ss = str(c["sameSite"]).lower()
                        if ss in ["lax", "strict", "none"]:
                            cookie_dict["sameSite"] = ss.capitalize()
                    
                    sb.add_cookie(cookie_dict)
                
                print("Cookie 成功注入！")
                
                # 重新刷新加载，应用 Cookie
                sb.refresh()
                sb.sleep(5)
            except Exception as e:
                print(f"注入 Cookie 过程中发生异常，跳过: {e}")

        # 3. 核心过盾：自动寻找并执行系统级物理点击过 Cloudflare Turnstile 验证盾
        sb.save_screenshot("icehost_debug_screenshot.png")
        try:
            print("正在检测并调用系统级 PyAutoGUI 驱动，物理点击 Cloudflare 人机验证码...")
            # 在虚拟桌面上定位验证框并模拟发送系统硬件级点击事件
            sb.uc_gui_click_captcha()
            sb.sleep(10) # 给予 10 秒跳转缓冲
            sb.save_screenshot("icehost_debug_screenshot.png")
        except Exception as e:
            print(f"验证盾已被跳过或点击执行完毕: {e}")

        # 4. 判断登录状态
        current_url = sb.get_current_url()
        # 判断是否停留在登录页
        if "login" in current_url or sb.is_element_visible("input[type='email']"):
            msg = "❌ <b>IceHost 登录失效！</b>\n请在浏览器重新提取并更新 ICEHOST_COOKIES。"
            print(msg)
            send_tg_notification(msg, "icehost_debug_screenshot.png")
            return

        print("✅ 登录状态验证成功！")

        # 5. 登录成功后无论是否续期，都先执行一次 Restart 重启
        restart_btn_selector = "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'restart')]"
        restarted = False
        try:
            print("正在寻找 Restart 重启按钮...")
            sb.wait_for_element_visible(restart_btn_selector, timeout=10)
            print("找到 Restart 按钮，正在点击...")
            sb.click(restart_btn_selector)
            sb.sleep(10)
            sb.save_screenshot("icehost_debug_screenshot.png")
            print("Restart 按钮点击成功！")
            restarted = True
        except Exception as re_e:
            print(f"未能点击 Restart 按钮: {re_e}")

        # 6. 判定波兰语与英语红框限制
        page_source = sb.get_page_source()
        keywords = ["Nie możesz przedłużyć", "niedawno to zrobiłeś", "kolejne 6 godziny", "cannot extend", "recently", "next 6 hours"]
        is_limited = any(kw in page_source for kw in keywords)

        if is_limited:
            print("检测到红框限制提示：说明当前处于冷却保护期，未到可续期时间。")
            # 如果是手动触发 workflow_dispatch，发送 TG 通知告知运行正常
            if GITHUB_EVENT_NAME == "workflow_dispatch":
                msg = "ℹ️ <b>IceHost 运行报告（手动触发）</b>\n当前处于 6 小时冷却保护期内（暂未到续期时间）。登录及重启操作正常。"
                if restarted:
                    msg += "\n🔄 <b>服务器已触发 Restart 重启</b>"
                sb.save_screenshot("icehost_debug_screenshot.png")
                send_tg_notification(msg, "icehost_debug_screenshot.png")
            else:
                print("定时任务检测到冷却期，跳过发送 TG 通知，结束本次运行。")
            return

        # 7. 安全寻找并点击续期按钮
        renew_btn_selector = "//*[not(*) and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'dodaj 6') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add 6'))]"
        
        try:
            print("正在等待续期按钮加载...")
            sb.wait_for_element_visible(renew_btn_selector, timeout=15)
            print("未检测到限制提示，找到续期按钮，正在点击...")
            sb.click(renew_btn_selector)
            
            # 点击后等待 5 秒让请求完成
            sb.sleep(5)
            sb.save_screenshot("icehost_debug_screenshot.png")
            
            # 刷新页面确认续期结果
            print("点击完成，正在刷新页面确认续期结果...")
            sb.refresh()
            sb.sleep(5)
            
            updated_source = sb.get_page_source()
            is_now_limited = any(kw in updated_source for kw in keywords)
            
            if is_now_limited:
                msg = "⚡ <b>IceHost 服务器续期成功！</b>\n服务器已真正成功延长 6 小时有效期。"
            else:
                msg = "ℹ️ <b>IceHost 续期指令已发送</b>\n按钮已点击，请检查下方截图确认是否成功。"
            
            if restarted:
                msg += "\n🔄 <b>服务器已触发 Restart 重启</b>"
            
            print(msg)
            sb.save_screenshot("icehost_debug_screenshot.png")
            send_tg_notification(msg, "icehost_debug_screenshot.png")
                
        except Exception as e:
            error_msg = f"❌ <b>IceHost 续期异常！</b>\n未找到续期按钮或操作失败: {html.escape(str(e))}"
            print(f"未在页面中找到可用的续期按钮: {e}")
            sb.save_screenshot("icehost_debug_screenshot.png")
            send_tg_notification(error_msg, "icehost_debug_screenshot.png")

if __name__ == "__main__":
    run()
