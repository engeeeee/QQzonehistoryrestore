import platform
import sys
import os
import subprocess

import requests
from PIL import Image
import urllib3

try:
    from pyzbar.pyzbar import decode
    import_success = True
except Exception as e:
    print("无法找到 zbar 共享库。请确保安装了 zbar。")
    decode = None
    import_success = False

    if platform.system() == "Linux":
        print("对于基于 RPM 的系统（如 Fedora), 您可以运行以下命令:")
        print("sudo dnf install -y zbar")
    elif platform.system() == "Darwin":
        print("MacOS 安装 zbar 请参考:")
        print("https://github.com/LibraHp/GetQzonehistory/issues/23#issuecomment-2349269027")
        
        try:
            subprocess.check_call(["brew", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print("检测到您已安装 Homebrew。是否通过 Homebrew 安装 zbar？ (y/n)")
            user_input = input().strip().lower()
            
            if user_input == "y":
                # 安装 zbar
                subprocess.check_call(["brew", "install", "zbar"])

                # 创建 lib 目录和符号链接
                if not os.path.exists("lib"):
                    os.makedirs("lib")

                zbar_lib_path = os.path.join(subprocess.check_output(["brew", "--prefix", "zbar"], text=True).strip(), "lib", "libzbar.dylib")
                subprocess.check_call(["ln", "-s", zbar_lib_path, "./lib/libzbar.dylib"])
                print("zbar 安装并配置成功。")
                
                # 尝试导入 pyzbar
                from pyzbar.pyzbar import decode
                import_success = True
        except FileNotFoundError:
            print("未检测到 Homebrew。请先安装 Homebrew 或参考文档手动安装 zbar。")
        except subprocess.CalledProcessError:
            print("检测 Homebrew 版本时出错，请确保 Homebrew 正常安装。")
        except Exception as install_error:
            print(f"安装过程中发生错误: {install_error}")
    
    if not import_success:
        print("有关更多安装指南，请参考 zbar 的官方文档或您的发行版文档。")

import time
import re
import util.ConfigUtil as Config
import threading

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOGIN_SESSION_ID = 0
LOGIN_SESSION_LOCK = threading.Lock()


def new_login_session():
    global LOGIN_SESSION_ID
    with LOGIN_SESSION_LOCK:
        LOGIN_SESSION_ID += 1
        return LOGIN_SESSION_ID


def get_login_session_id():
    return LOGIN_SESSION_ID


def _is_session_valid(session_id):
    if session_id is None:
        return True
    return session_id == LOGIN_SESSION_ID


def bkn(pSkey):
    # 计算bkn
    t, n, o = 5381, 0, len(pSkey)

    while n < o:
        t += (t << 5) + ord(pSkey[n])
        n += 1

    return t & 2147483647


def ptqrToken(qrsig):
    # 计算ptqrtoken
    n, i, e = len(qrsig), 0, 0

    while n > i:
        e += (e << 5) + ord(qrsig[i])
        i += 1

    return 2147483647 & e


def _build_qr_urls():
    t = str(time.time())
    return [
        ("qzone", f"https://ssl.ptlogin2.qq.com/ptqrshow?appid=549000912&e=2&l=M&s=3&d=72&v=4&t={t}&daid=5&pt_3rd_aid=0"),
        ("qzone-http", f"https://ptlogin2.qq.com/ptqrshow?appid=549000912&e=2&l=M&s=3&d=72&v=4&t={t}&daid=5&pt_3rd_aid=0"),
        ("qq", f"https://ssl.ptlogin2.qq.com/ptqrshow?appid=716027609&e=2&l=M&s=3&d=72&v=4&t={t}&daid=383&pt_3rd_aid=0"),
        ("qq-http", f"https://ptlogin2.qq.com/ptqrshow?appid=716027609&e=2&l=M&s=3&d=72&v=4&t={t}&daid=383&pt_3rd_aid=0"),
    ]


def debug_qr_endpoints():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://qzs.qq.com/qzone/v5/loginsucc.html?para=izone",
    }
    results = []
    proxy_modes = [
        ("no-proxy", {"http": None, "https": None}),
        ("env-proxy", None),
    ]
    for name, url in _build_qr_urls():
        for proxy_name, proxies in proxy_modes:
            try:
                r = requests.get(url, headers=headers, timeout=(5, 10), verify=False, proxies=proxies)
                qrsig = requests.utils.dict_from_cookiejar(r.cookies).get('qrsig')
                content_ok = r.content.startswith(b'\x89PNG')
                results.append(
                    f"[{name}/{proxy_name}] status={r.status_code} qrsig={'yes' if qrsig else 'no'} png={'yes' if content_ok else 'no'} len={len(r.content)}"
                )
            except Exception as exc:
                results.append(f"[{name}/{proxy_name}] error={exc}")
    return results


def QR(session_id=None):
    # 获取 qq空间 二维码
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://qzs.qq.com/qzone/v5/loginsucc.html?para=izone",
    }
    qr_file = os.path.join(Config.temp_path, 'QR.png')
    os.makedirs(os.path.dirname(qr_file), exist_ok=True)

    proxy_modes = [
        ("no-proxy", {"http": None, "https": None}),
        ("env-proxy", None),
    ]

    for name, url in _build_qr_urls():
        for proxy_name, proxies in proxy_modes:
            if not _is_session_valid(session_id):
                print("二维码获取已取消")
                return None
            try:
                print(f"尝试二维码地址[{name}/{proxy_name}]: {url}")
                r = requests.get(url, headers=headers, timeout=(5, 10), verify=False, proxies=proxies)
                if r.status_code != 200:
                    print(f"二维码获取失败[{name}/{proxy_name}]: 状态码 {r.status_code}")
                    continue
                qrsig = requests.utils.dict_from_cookiejar(r.cookies).get('qrsig')
                if not qrsig:
                    print(f"二维码获取失败[{name}/{proxy_name}]: qrsig 为空")
                    continue
                if not r.content.startswith(b'\x89PNG'):
                    print(f"二维码获取失败[{name}/{proxy_name}]: 响应非PNG")
                    continue
                with open(qr_file, 'wb') as f:
                    f.write(r.content)

                im = Image.open(qr_file)
                im = im.resize((350, 350))
                print(time.strftime('%H:%M:%S'), f'登录二维码获取成功 ({name}/{proxy_name})')

                if import_success and decode and os.environ.get("QZONE_GUI") != "1":
                    decoded_objects = decode(im)
                    if decoded_objects:
                        print("二维码已生成 (终端模式)")
                else:
                    print(f"已保存二维码图片，请用QQ扫一扫: {qr_file}")

                return qrsig
            except Exception as e:
                print(f"二维码获取异常[{name}/{proxy_name}]: {e}")

    return None


def cookie(force_relogin=None, session_id=None):
    Config.init_flooder()
    if force_relogin is None:
        force_relogin = Config.force_relogin
    if session_id is None:
        session_id = get_login_session_id()
    if not _is_session_valid(session_id):
        print("登录已取消")
        return None
    select_user = Config.read_files_in_folder(force_relogin_override=force_relogin)
    if select_user:
        return eval(select_user)
    # 获取 QQ空间 cookie
    qrsig = QR(session_id=session_id)
    if not qrsig:
        print("二维码生成失败，请检查网络后重试")
        return None
    ptqrtoken = ptqrToken(qrsig)

    while True:
        if not _is_session_valid(session_id):
            print("登录已取消")
            return None
        url = 'https://ssl.ptlogin2.qq.com/ptqrlogin?u1=https%3A%2F%2Fqzs.qq.com%2Fqzone%2Fv5%2Floginsucc.html%3Fpara' \
              '%3Dizone&ptqrtoken=' + str(ptqrtoken) + '&ptredirect=0&h=1&t=1&g=1&from_ui=1&ptlang=2052&action=0-0-' \
              + str(time.time()) + '&js_ver=20032614&js_type=1&login_sig=&pt_uistyle=40&aid=549000912&daid=5&'
        cookies = {'qrsig': qrsig}
        try:
            r = requests.get(url, cookies=cookies)
            if '二维码未失效' in r.text:
                # print(time.strftime('%H:%M:%S'), '二维码未失效')
                pass
            elif '二维码认证中' in r.text:
                print(time.strftime('%H:%M:%S'), '二维码认证中')
            elif '二维码已失效' in r.text:
                print(time.strftime('%H:%M:%S'), '二维码已失效')
            elif '登录成功' in r.text:
                print(time.strftime('%H:%M:%S'), '登录成功')
                cookies = requests.utils.dict_from_cookiejar(r.cookies)
                uin = requests.utils.dict_from_cookiejar(r.cookies).get('uin')
                regex = re.compile(r'ptsigx=(.*?)&')
                sigx = re.findall(regex, r.text)[0]
                url = 'https://ptlogin2.qzone.qq.com/check_sig?pttype=1&uin=' + uin + '&service=ptqrlogin&nodirect=0' \
                                                                                      '&ptsigx=' + sigx + \
                      '&s_url=https%3A%2F%2Fqzs.qq.com%2Fqzone%2Fv5%2Floginsucc.html%3Fpara%3Dizone&f_url=&ptlang' \
                      '=2052&ptredirect=100&aid=549000912&daid=5&j_later=0&low_login_hour=0&regmaster=0&pt_login_type' \
                      '=3&pt_aid=0&pt_aaid=16&pt_light=0&pt_3rd_aid=0'
                try:
                    r = requests.get(url, cookies=cookies, allow_redirects=False)
                    target_cookies = requests.utils.dict_from_cookiejar(r.cookies)
                    p_skey = requests.utils.dict_from_cookiejar(r.cookies).get('p_skey')
                    Config.save_user(target_cookies)
                    break

                except Exception as e:
                    print(e)
            else:
                print(time.strftime('%H:%M:%S'), '用户取消登录')

        except Exception as e:
            print(e)

        time.sleep(3)

    return target_cookies
