import json
import math
import os
import re
import sys
import time

import requests
from tqdm import tqdm
import urllib3

from util import RequestUtil as Request
from util import LoginUtil
from util import ToolsUtil as Tool

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USER_QZONE_INFO = 'user_qzone_info.json'
QZONE_MOMENTS_ALL = 'qzone_moments_all.json'


def get_workdir():
    Request.ensure_login()
    qq_number = Request.uin
    return f"./resource/fetch-all/{qq_number}"


# 进度回调函数
progress_callback = None

def set_progress_callback(callback):
    global progress_callback
    progress_callback = callback

def report_progress(current, total, message=""):
    if progress_callback:
        progress_callback(current, total, message)
    print(f"进度: {current}/{total} {message}")


# 获取所有可见的未删除的说说+高清图片（包含2014年之前）
def get_visible_moments_list(force_refresh=False):

    Request.ensure_login()
    workdir = get_workdir()

    # 如果强制刷新，删除缓存文件
    if force_refresh:
        print("强制刷新模式：清除本地缓存...")
        cache_files = [USER_QZONE_INFO, QZONE_MOMENTS_ALL]
        for cache_file in cache_files:
            cache_path = os.path.join(workdir, cache_file)
            if os.path.exists(cache_path):
                os.remove(cache_path)
                print(f"已删除缓存: {cache_file}")

    # 1. 获取说说总条数
    user_qzone_info = Tool.read_txt_file(workdir, USER_QZONE_INFO)
    if not user_qzone_info:
        # 样本缓存未找到，开始请求获取样本
        qq_userinfo_response = get_user_qzone_info(1)
        if not qq_userinfo_response:
            print("获取QQ空间信息失败: 请求为空")
            return None
        Tool.write_txt_file(workdir, USER_QZONE_INFO, qq_userinfo_response)
        user_qzone_info = Tool.read_txt_file(workdir, USER_QZONE_INFO)

    if not Tool.is_valid_json(user_qzone_info):
        print("获取QQ空间信息失败")
        return None
    json_dict = json.loads(user_qzone_info)
    total_moments_count = json_dict['total']
    print(f'你的未删除说说总条数{total_moments_count}')

    # 当前未删除说说总数为0, 直接返回
    if total_moments_count == 0:
        return None

    # 2. 获取所有说说数据
    print("开始获取所有未删除说说")
    qzone_moments_all = Tool.read_txt_file(workdir, QZONE_MOMENTS_ALL)
    if not qzone_moments_all:
        # 缓存未找到，开始请求获取所有未删除说说
        # qq_userinfo_response = get_user_qzone_info(totalMomentsCount)
        # Tool.write_txt_file(WORKDIR, QZONE_MOMENTS_ALL, qq_userinfo_response)
        # qzone_moments_all = Tool.read_txt_file(WORKDIR, QZONE_MOMENTS_ALL)
        default_page_size = 30  # 默认一页30条
        total_page_num = math.ceil(total_moments_count / default_page_size)  # 总页数
        all_page_data = []  # 用于存储所有页的数据
        for current_page_num in range(0, total_page_num):
            # 数据偏移量
            pos = current_page_num * default_page_size
            report_progress(current_page_num + 1, total_page_num, f"获取第{current_page_num + 1}/{total_page_num}页")
            qq_userinfo_response = get_user_qzone_info(default_page_size, pos)
            if not qq_userinfo_response:
                print("获取QQ空间说说失败: 请求为空")
                return None
            current_page_data = json.loads(qq_userinfo_response)["msglist"]
            if current_page_data:
                all_page_data.extend(current_page_data)
            time.sleep(0.02)
        qq_userinfo = json.dumps({"msglist": all_page_data}, ensure_ascii=False, indent=2)
        Tool.write_txt_file(workdir, QZONE_MOMENTS_ALL, qq_userinfo)
        qzone_moments_all = Tool.read_txt_file(workdir, QZONE_MOMENTS_ALL)

    if not Tool.is_valid_json(qzone_moments_all):
        print("获取QQ空间说说失败")
        return None
    json_dict = json.loads(qzone_moments_all)
    qzone_moments_list = json_dict['msglist']
    print(f'已获取到数据的说说总条数{len(qzone_moments_list)}')

    # 3. 添加说说列表
    texts = []
    for item in tqdm(qzone_moments_list, desc="获取未删除说说", unit="条"):
        content = item['content'] if item['content'] else ""
        nickname = item['name']
        create_time = Tool.format_timestamp(item['created_time'])
        pictures = ""
        # 如果有图片
        if 'pic' in item:
            for index, picture in enumerate(item['pic']):
                pictures += picture['url1'] + ","
        if 'video' in item:
            for index, picture in enumerate(item['video']):
                pictures += picture['url1'] + ","

        # 去除最后一个逗号
        pictures = pictures[:-1] if pictures != "" else pictures
        comments = []
        if 'commentlist' in item:
            for index, commentToMe in enumerate(item['commentlist']):
                comment_content = commentToMe['content']
                comment_create_time = commentToMe['createTime2']
                comment_nickname = commentToMe['name']
                comment_uin = commentToMe['uin']
                # 时间，内容，昵称，QQ号
                comments.append([comment_create_time, comment_content, comment_nickname, comment_uin])

        # 格式：时间、内容、图片链接、转发内容、评论内容
        texts.append([create_time, f"{nickname} ：{content}", pictures, comments])
    return texts


# 获取用户QQ空间相关信息
def get_user_qzone_info(page_size, offset=0):
    Request.ensure_login()
    url = 'https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6'
    cookies = Request.cookies
    g_tk = LoginUtil.bkn(cookies.get('p_skey'))
    qqNumber = re.sub(r'o0*', '', cookies.get('uin'))
    skey = cookies.get('skey')
    p_uin = cookies.get('p_uin')
    pt4_token = cookies.get('pt4_token')
    p_skey = cookies.get('p_skey')
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'cookie': f'uin={p_uin};skey={skey};p_uin={p_uin};pt4_token={pt4_token};p_skey={p_skey}',
        'priority': 'u=1, i',
        'referer': f'https://user.qzone.qq.com/{qqNumber}/main',
        'sec-ch-ua': '"Not;A=Brand";v="24", "Chromium";v="128"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Linux"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
    }

    params = {
        'uin': f'{qqNumber}',
        'ftype': '0',
        'sort': '0',
        'pos': f'{offset}',
        'num': f'{page_size}',
        'replynum': '100',
        'g_tk': f'{g_tk}',
        'callback': '_preloadCallback',
        'code_version': '1',
        'format': 'jsonp',
        'need_private_comment': '1'
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=(10, 30), verify=False)
    except Exception as e:
        print(f"获取QQ空间说说请求失败: {e}")
        return None
    if not response or not hasattr(response, 'text'):
        print("获取QQ空间说说请求失败: 无响应")
        return None
    rawResponse = response.text
    # 使用正则表达式去掉 _preloadCallback()，并提取其中的 JSON 数据
    raw_txt = re.sub(r'^_preloadCallback\((.*)\);?$', r'\1', rawResponse, flags=re.S)
    # 再转一次是为了去掉响应值本身自带的转义符http:\/\/ 
    try:
        json_dict = json.loads(raw_txt)
    except Exception as e:
        print(f"获取QQ空间说说解析失败: {e}")
        return None
    if json_dict['code'] != 0:
        print(f"错误 {json_dict['message']}")
        sys.exit(1)
    return json.dumps(json_dict, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    get_visible_moments_list()
