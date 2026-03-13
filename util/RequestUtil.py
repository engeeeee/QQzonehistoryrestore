import re
import time
import logging
from tqdm import tqdm
import util.LoginUtil as Login
import requests
import json
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
import util.ConfigUtil as Config

# 配置日志
logger = logging.getLogger(__name__)

UA_STRING = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
# 登陆后获取到的cookies
cookies = None
# 获取g_tk
g_tk = None
# 获取uin
uin = None

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 创建自定义SSL上下文
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# 创建session并配置重试策略
session = requests.Session()

# 配置重试策略
retry_strategy = Retry(
    total=3,  # 总重试次数
    backoff_factor=1,  # 重试间隔时间因子
    status_forcelist=[429, 500, 502, 503, 504],  # 需要重试的HTTP状态码
    allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
)

# 创建HTTP适配器
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# 全局header
headers = {
    'authority': 'user.qzone.qq.com',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,'
              'application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'sec-ch-ua': '"Not A(Brand";v="99", "Microsoft Edge";v="121", "Chromium";v="121"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'none',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': UA_STRING,
}


def ensure_login(force_relogin=None):
    global cookies, g_tk, uin
    logger.debug("开始验证登录状态...")
    
    if force_relogin is None:
        force_relogin = Config.force_relogin
    
    logger.debug(f"cookies={cookies is not None}, force_relogin={force_relogin}, selected_user={Config.selected_user_file}")
    
    # 如果已有cookies且不强制重登录，直接返回
    if cookies is not None and not force_relogin:
        logger.debug("使用已有cookies")
        return cookies
    
    # 如果有已选用户文件，先尝试从文件加载
    if Config.selected_user_file and not force_relogin:
        logger.debug(f"尝试从已选用户加载: {Config.selected_user_file}")
        try:
            saved_cookies = Config.read_files_in_folder(force_relogin_override=False)
            if saved_cookies:
                cookies = eval(saved_cookies)
                g_tk = Login.bkn(cookies.get('p_skey'))
                uin = re.sub(r'o0*', '', cookies.get('uin'))
                logger.debug(f"成功从文件加载cookies, uin={uin}")
                return cookies
        except Exception as e:
            logger.debug(f"从文件加载失败: {e}")
    
    # 如果在GUI模式下且没有已选用户，不要进入登录循环
    import os
    if os.environ.get("QZONE_GUI") == "1" and not force_relogin:
        logger.debug("GUI模式下未选择用户，跳过自动登录")
        return None
    
    # 需要登录
    logger.debug("需要获取新的cookies...")
    cookies = Login.cookie(force_relogin=force_relogin)
    if not cookies:
        logger.warning("获取cookies失败")
        return None
    g_tk = Login.bkn(cookies.get('p_skey'))
    uin = re.sub(r'o0*', '', cookies.get('uin'))
    Config.set_force_relogin(False)
    logger.debug(f"登录成功, uin={uin}")
    return cookies


def reset_login():
    global cookies, g_tk, uin
    cookies = None
    g_tk = None
    uin = None


# 获取历史消息列表
def get_message(start, count):
    if not ensure_login():
        return None
    params = {
        'uin': uin,
        'begin_time': '0',
        'end_time': '0',
        'getappnotification': '1',
        'getnotifi': '1',
        'has_get_key': '0',
        'offset': start,
        'set': '0',
        'count': count,
        'useutf8': '1',
        'outputhtmlfeed': '1',
        'scope': '1',
        'format': 'jsonp',
        'g_tk': [
            g_tk,
            g_tk,
        ],
    }

    try:
        response = session.get(
            'https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds2_html_pav_all',
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=(10, 30),  # 增加超时时间
            verify=False,  # 禁用SSL验证
            stream=False
        )
        time.sleep(0.2)  # 进一步减少等待时间
    except (requests.Timeout, requests.exceptions.SSLError, requests.exceptions.ConnectionError) as e:
        print(f"请求发生异常: {e}")
        # 尝试使用更宽松的SSL设置重试
        try:
            response = session.get(
                'https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds2_html_pav_all',
                params=params,
                cookies=cookies,
                headers=headers,
                timeout=(15, 45),
                verify=False,
                stream=False
            )
            time.sleep(0.2)
        except Exception as retry_e:
            print(f"重试请求也失败: {retry_e}")
            return None
    except Exception as e:
        print(f"请求发生未知异常: {e}")
        return None

    return response


def get_login_user_info():
    print("正在获取用户信息...")
    if not ensure_login():
        print("登录验证失败")
        return None
    if uin is None:
        print("用户uin为空")
        return None
    try:
        print(f"请求用户信息: uin={uin}")
        response = session.get('https://r.qzone.qq.com/fcg-bin/cgi_get_portrait.fcg?g_tk=' + str(g_tk) + '&uins=' + uin,
                              headers=headers, cookies=cookies, verify=False, timeout=(5, 15))
        print(f"用户信息响应状态: {response.status_code}")
    except Exception as e:
        print(f"获取用户信息失败: {e}")
        return None
    # 尝试多种编码方式解码
    info = None
    encodings_to_try = ['gbk', 'gb2312', 'gb18030', 'utf-8', 'big5']
    
    for encoding in encodings_to_try:
        try:
            info = response.content.decode(encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    # 如果所有编码都失败，使用错误处理策略
    if info is None:
        try:
            info = response.content.decode('gbk', errors='replace')
            print("警告：使用GBK替换模式解码用户信息，可能丢失部分字符信息")
        except:
            print("严重错误：无法解码用户信息响应内容")
            return None
    
    info = info.strip().lstrip('portraitCallBack(').rstrip(');')
    info = json.loads(info)
    return info


def save_debug_response(response, filename="debug_api_response.txt"):
    """保存API响应到调试文件"""
    import os
    import sys
    try:
        # 获取正确的基础路径（兼容打包后的EXE）
        if getattr(sys, 'frozen', False):
            # 打包后的EXE，使用EXE所在目录
            base_dir = os.path.dirname(sys.executable)
        else:
            # 开发环境，使用项目目录
            base_dir = os.path.dirname(os.path.dirname(__file__))
        
        debug_dir = os.path.join(base_dir, "resource", "temp")
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        debug_path = os.path.join(debug_dir, filename)
        
        logger.debug(f"调试文件保存路径: {debug_path}")
        
        if response and hasattr(response, 'text'):
            with open(debug_path, 'w', encoding='utf-8') as f:
                f.write(f"=== 原始响应 ===\n")
                f.write(response.text)
                f.write(f"\n\n=== 响应长度: {len(response.text)} ===\n")
            print(f"调试响应已保存到: {debug_path}")
            return debug_path
    except Exception as e:
        print(f"保存调试响应失败: {e}")
        import traceback
        traceback.print_exc()
    return None


def check_response_has_data(response, save_debug=False):
    """
    检查API响应是否包含有效的互动消息数据
    返回: (has_data: bool, html_content: str or None)
    """
    import util.ToolsUtil as Tools
    
    if not response:
        logger.debug("response为空")
        return False, None
    if not hasattr(response, 'text') and not hasattr(response, 'content'):
        logger.debug("response没有text或content属性")
        return False, None
    
    try:
        # 获取响应文本
        if hasattr(response, 'text'):
            raw_text = response.text
        else:
            raw_text = response.content.decode('utf-8', errors='replace')
        
        if save_debug:
            logger.debug(f"原始响应长度: {len(raw_text)}")
            logger.debug(f"原始响应前300字符: {raw_text[:300]}")
        
        # 方法1: 直接在原始响应中检查关键标记
        # 互动消息API的JSONP响应中，如果有数据，会包含这些标记
        raw_has_data = False
        
        # 检查原始响应中的关键标记（这些在JSONP中也能匹配）
        if 'f-single' in raw_text or 'f-s-s' in raw_text:
            raw_has_data = True
            if save_debug:
                logger.debug("原始响应中发现f-single/f-s-s标记")
        
        if 'class=\\\"f-single' in raw_text or "class='f-single" in raw_text:
            raw_has_data = True
            if save_debug:
                logger.debug("原始响应中发现转义的f-single标记")
        
        if 'txt-box-title' in raw_text:
            raw_has_data = True
            if save_debug:
                logger.debug("原始响应中发现txt-box-title标记")
        
        if 'info-detail' in raw_text:
            raw_has_data = True
            if save_debug:
                logger.debug("原始响应中发现info-detail标记")
        
        # 检查是否有li标签（可能是转义的）
        if '<li' in raw_text or '\\x3cli' in raw_text or '&lt;li' in raw_text:
            raw_has_data = True
            if save_debug:
                logger.debug("原始响应中发现li标记")
        
        if raw_has_data:
            # 尝试提取HTML内容
            try:
                html_content = Tools.process_old_html(raw_text)
                if save_debug:
                    logger.debug(f"提取的HTML长度: {len(html_content)}")
                    logger.debug(f"提取的HTML前200字符: {html_content[:200]}")
                return True, html_content
            except Exception as e:
                if save_debug:
                    logger.debug(f"提取HTML失败: {e}")
                return True, raw_text  # 即使提取失败，原始数据中有标记也返回True
        
        if save_debug:
            logger.debug("未在原始响应中发现任何有效数据标记")
        return False, None
        
    except Exception as e:
        print(f"检查响应数据时发生异常: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def get_message_count():
    if not ensure_login():
        return 0
    
    print("=" * 50)
    print("正在检测互动消息（调试模式）...")
    print("=" * 50)
    
    # 首先检测是否有任何互动消息
    try:
        response = get_message(0, 10)
        
        # 强制保存第一次响应用于调试
        if response and hasattr(response, 'text'):
            debug_path = save_debug_response(response, "debug_first_response.txt")
            print(f"[调试] 首次API响应已保存")
        
        has_data, html_preview = check_response_has_data(response, save_debug=True)
        
        if not has_data:
            print("=" * 50)
            print("警告: 互动消息API响应中没有找到有效数据")
            print("这可能是因为:")
            print("1. 该账号没有互动消息历史")
            print("2. QQ空间的互动消息功能已关闭")
            print("3. API访问受限")
            print("=" * 50)
            print("将跳过互动消息获取，只获取可见说说...")
            return 0
        
        print("检测到互动消息，开始定位数量...")
        if html_preview:
            preview = html_preview[:200] if len(html_preview) > 200 else html_preview
            print(f"HTML内容预览: {preview}...")
            
    except Exception as e:
        print(f"检测互动消息失败: {e}")
        import traceback
        traceback.print_exc()
        return 0
    
    # 快速探测实际范围
    test_points = [100, 500, 1000, 2000, 5000, 10000]
    actual_upper = 50  # 至少有一些消息
    for point in test_points:
        try:
            response = get_message(point, 10)
            has_data, _ = check_response_has_data(response)
            if has_data:
                actual_upper = point
                print(f"  探测到 {point} 处有数据...")
            else:
                break
        except:
            break
    
    # 使用实际范围进行精确二分
    upper_bound = actual_upper + 500
    lower_bound = 0
    total = upper_bound // 2
    
    print(f"在 0-{upper_bound} 范围内精确查找...")
    with tqdm(desc="精确定位消息数量") as pbar:
        while lower_bound <= upper_bound:
            try:
                response = get_message(total, 100)
                has_data, _ = check_response_has_data(response)

                if has_data:
                    lower_bound = total + 1
                else:
                    upper_bound = total - 1

            except Exception as e:
                print(f"请求发生异常: {e}")
                break

            total = (lower_bound + upper_bound) // 2
            pbar.update(1)

    print(f"互动消息数量: {total}")
    return total
