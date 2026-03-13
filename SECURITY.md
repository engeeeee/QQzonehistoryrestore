# Security Policy

## Supported Versions

当前仅维护默认分支上的最新代码版本。历史版本与旧版构建文件不保证继续修复安全问题。

## Reporting a Vulnerability

如果你发现了安全问题，请不要在公开 Issue 直接披露细节。

建议使用以下方式之一：

1. 在 GitHub 上创建私密 Security Advisory（推荐）
2. 通过仓库维护者主页联系方式私下联系

提交时请尽量包含：

- 问题影响范围与风险等级
- 可复现步骤（PoC）
- 受影响的版本或提交号
- 修复建议（如有）

## Response Process

- 维护者会在 7 个自然日内确认是否收到报告
- 确认问题后会尽快评估并安排修复
- 修复发布后会在仓库中同步更新说明

## Security Notes for Users

- 本工具会读取并缓存登录态，请妥善保管本地 `resource/user/` 数据
- 不要将包含 Cookie、账号标识或导出隐私数据的文件上传到公开仓库
- 建议在受信任的本机环境运行，并及时更新到最新版本
