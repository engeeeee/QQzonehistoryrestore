import configparser
import os
import sys

def resolve_config_path():
    cwd_path = os.path.join(os.getcwd(), 'resource', 'config', 'config.ini')
    if os.path.exists(cwd_path):
        return cwd_path
    module_base = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    module_path = os.path.join(module_base, 'resource', 'config', 'config.ini')
    if os.path.exists(module_path):
        return module_path
    base_dir = getattr(sys, '_MEIPASS', os.getcwd())
    return os.path.join(base_dir, 'resource', 'config', 'config.ini')


config = configparser.ConfigParser()
config.read(resolve_config_path())

temp_path = config.get('File', 'temp')
user_path = config.get('File', 'user')
result_path = config.get('File', 'result')

selected_user_file = None
force_relogin = False


def set_selected_user_file(file_name):
    global selected_user_file
    selected_user_file = file_name


def set_force_relogin(value):
    global force_relogin
    force_relogin = bool(value)


def save_user(cookies):
    with open(user_path + cookies.get('uin'), 'w') as f:
        f.write(str(cookies))


def init_flooder():
    # 初始化temp文件夹
    if not os.path.exists(temp_path):
        os.makedirs(temp_path)
        print(f"Created directory: {temp_path}")

    # 初始化user文件夹
    if not os.path.exists(user_path):
        os.makedirs(user_path)
        print(f"Created directory: {user_path}")

    # 初始化result文件夹
    if not os.path.exists(result_path):
        os.makedirs(result_path)
        print(f"Created directory: {result_path}")


def read_files_in_folder(force_relogin_override=None):
    if force_relogin_override is None:
        force_relogin_override = force_relogin
    if force_relogin_override:
        return None
    # 获取文件夹下的所有文件
    files = os.listdir(user_path)
    # 如果文件夹为空
    if not files:
        return None
    if selected_user_file and selected_user_file in files:
        file_path = os.path.join(user_path, selected_user_file)
        with open(file_path, 'r') as file:
            content = file.read()
        return content
    # 输出文件列表
    print("已登录用户列表:")
    for i, file in enumerate(files):
        print(f"{i + 1}. {file}")

    # 选择文件
    while True:
        try:
            choice = int(input("请选择要登录的用户序号，重新登录输入0: "))
            if 1 <= choice <= len(files):
                break
            elif choice == 0:
                return None
            else:
                print("无效的选择，请重新输入。")
        except ValueError:
            print("无效的选择，请重新输入。")

    # 读取选择的文件
    selected_file = files[choice - 1]
    file_path = os.path.join(user_path, selected_file)
    with open(file_path, 'r') as file:
        content = file.read()

    return content
