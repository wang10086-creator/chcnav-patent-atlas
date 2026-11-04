# IncoPat 状态快照上线说明

本次最小公开映射来自已交接的 2026-11-03 IncoPat 数据；原执行环境及独立审计已核对 10 份原件。本执行环境验证交接映射 SHA、字段白名单、逐公告号及申请号匹配，不声称在本环境重新读取原 Excel。

映射 SHA256：faccd8054418d12a100ae992ee775f3bd46a414c3690b8150295698d4256dfbf。
938 文献、807 申请全匹配，重复/缺失/新增/申请内状态冲突均 0。

|来源状态原值|文献|申请|
|---|---:|---:|
|授权|491|360|
|未缴年费|112|112|
|驳回|213|213|
|实质审查|104|104|
|撤回|6|6|
|全部无效|3|3|
|期限届满|4|4|
|公开|3|3|
|避重放弃|2|2|

来源有效性：文献有效 491、失效 340、审中 107；申请有效 360、失效 340、审中 107。137 条 A 文献的来源快照为授权/有效；这不把 A 文献变成授权文本，也不推定已取得可核验的授权公告号。

## 最小公开数据

新增 site-overrides/data/incopat-status-snapshot.json。逐条仅 publicationId、applicationNumber、statusRaw、validityRaw、jurisdiction；全局为 schemaVersion、source、snapshotDate、officialVerified、verificationLabel。未公开原 Excel、原生批次、历史长文、权利人、私有文件引用、路径或账户资料。构建对新增映射执行精确白名单和固定 SHA 校验。

原 portfolio-current.json 保持字节不变。来源快照、原资料基线及其他历史第三方线索分别展示；不自动认定来源差异就是变化。来源有效性/状态原值/文献阶段/地域按同一文献组合筛选。无快照、加载失败、标识冲突或申请内版本冲突时，不应用可疑快照，并显示异常说明。

未官方核验，不是实时状态，不自动填入已核实有效地域；中国地域不意味着已确认中国权利有效。状态事件日期与实际官方核验日期保持未知，不拿快照日期替代。2333 条历史记录没有加入公开文件，不称为新增事件。

## 验证与维护

- scripts/check_status_snapshot.py：938/807 对应、统计、版本一致性、SHA 及隐私字段白名单。
- scripts/test_status_snapshot.py：真实数据详情/列表/统计/筛选、137 条公开版本交集、多版本、历史来源差异、异常与移动端。
- scripts/test_panorama.py、scripts/test_workspace.py：原导图与响应式布局回归。
- Pages 部署后 scripts/check_public_status_release.py 从执行发布的 GitHub runner 真实访问公开 URL；比较 HTML、JS、CSS 和状态 JSON 的字节 SHA。不绕过本地网络限制，不使用身份或抓取 IncoPat。

新增日期的快照须另行验证逐条对应及原件来源，更新映射审计、固定 SHA 和统计预期；不能只改日期。公开展示范围依用户此次授权，不声明获得供应商新增许可。
