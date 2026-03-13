# QQzonehistoryrestore

QQ 空间历史动态导出与还原工具（Windows EXE + Python 源码版）。

本仓库是对原项目的改进版，重点优化了稳定性与可用性，适合用于备份本人账号可访问的 QQ 空间历史数据。

## 功能特性

- 扫码登录 QQ 空间并拉取历史动态数据
- 支持导出内容、图片、评论等信息到本地结果目录
- 提供图形界面（GUI）和命令行两种使用方式
- 提供 Windows 单文件 EXE，开箱即用
- 针对网络波动、编码异常、SSL 异常做了鲁棒性处理

## 快速开始（EXE 版）

1. 在 Release 页面下载最新 `GetQzonehistoryGUI.exe`
2. 双击运行程序
3. 使用二维码登录
4. 点击“开始获取”
5. 导出结果默认保存到 `resource/result/`

如果你从源码目录直接运行，现成构建文件位于 `dist/GetQzonehistoryGUI.exe`。

## 源码运行

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt
python gui_app.py
```

命令行模式：

```bash
python main.py
```

## 打包 EXE（Windows）

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name "GetQzonehistoryGUI" --add-data "resource;resource" gui_app.py
```

构建结果：`dist/GetQzonehistoryGUI.exe`

## 项目结构

```text
.
|-- gui_app.py                # GUI 入口
|-- main.py                   # CLI 入口
|-- fetch_all_message.py      # 可见动态补充抓取脚本
|-- util/                     # 业务与工具模块
|-- resource/
|   |-- config/config.ini     # 路径配置
|   |-- temp/                 # 临时文件
|   |-- user/                 # 登录缓存
|   `-- result/               # 导出结果
|-- dist/                     # 已构建 EXE
`-- build_gui.spec            # PyInstaller 配置
```

## 免责声明

- 本项目仅用于学习、研究与个人数据备份。
- 使用者应确保行为符合所在地法律法规及平台规则。
- 请勿用于未经授权的数据采集、传播或任何违法用途。

## 安全

安全策略与漏洞提交流程见 `SECURITY.md`。

## 致谢

- 原项目作者与社区贡献者
- QQ 空间扫码登录相关实现思路参考公开技术资料

## 许可证

本项目使用 MIT License，详见 `LICENSE`。
