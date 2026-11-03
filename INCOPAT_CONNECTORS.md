# IncoPat 接入项目核查与本次采用方式

核查日期：2026-11-03。用户确认目前只有机构网页登录权限，没有确认合享开放平台 API 授权。

| 项目 | 实际能力 | 本次判断 |
| --- | --- | --- |
| [mylib / incopat_api.py](https://github.com/gaoxingkele/mylib/blob/4be991fac12800007e616c648e69e2d172d3d9fa/paa/skills/incopat-search/scripts/incopat_api.py) | 第三方 Python 客户端，调用官方检索、法律状态、全文等 API，处理令牌和批量调用。 | 需要用户自己的 API 授权；项目测试授权自述截至 2026-08-31，且未发现明确 LICENSE。本次不引入代码、不使用其测试身份。 |
| [TD-Sky/incopat-collector](https://github.com/TD-Sky/incopat-collector) | MIT；在已登录的原生导出页分批点击下载，并合并 Excel。 | 没有管理员身份、法律变化比较、完整批次审计。旧脚本只勾部分著录字段，代理域名也需要适配。保留现有更完整的原生导入／审计流程。 |
| [BetterIncoPat.js](https://github.com/xylinkun/BetterIncoPat.js) | GPL-3.0；复制公开号／名称／链接、打开专利局来源和改善 PDF 下载。 | 辅助查看，不是状态变动监控库；本次不安装或复制。 |
| [web-ai-capability-hub](https://github.com/LT-0I/web-ai-capability-hub) | 有 IncoPat 浏览器和 MCP 适配描述。 | 核查的通用导出 handler 仅返回 handled / artifact:null，适配标为 experimental；不能按模块名称认定全量导出已实现。 |

[合享官方开放平台](https://open.incopat.com/)确实列有专利检索和法律状态等接口，并说明按客户需求确定服务方案、测试和联调。机构网页登录成功不足以证明已获得 API 接口权限。本轮没有新增 API 凭据、请求接口授权或安装第三方采集脚本。

本次实现采用：**管理员在已有机构授权浏览器中检索、导出 → 私有工作台导入／校验／比较 → 管理员人工核对 → 保存私有观察基线或导出脱敏摘要**。不设置自动任务，不自动访问 Incopat，不直接发布网站。
