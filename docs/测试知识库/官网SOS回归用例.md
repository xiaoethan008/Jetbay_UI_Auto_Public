# 官网 SOS 回归用例

维护日期：2026-06-26
来源版本：官网 V4.1.0（SOS）
对应版本资产：`artifacts/官网V4.1.0（SOS）`

## 使用规则

- 本文件只记录建议纳入常规回归的长期用例，执行证据仍放在对应版本 `artifacts` 目录。
- `CRM` 最终提交仅在 dev/uat 环境使用测试数据执行，生产回归不执行最终提交。
- 需求文档中已删除或删除线内容不纳入回归，不作为缺陷判断依据。
- 本版本已确认忽略：`District of Columbia` 表单搜索、`Built for long distance` 文案。
- 当前 22 条用例已纳入 `artifacts/测试用例清单.csv`，编号为 `TC-064` 到 `TC-085`。

## 固定自动化范围

| 用例 ID | 自动化脚本 | 入库原因 |
| --- | --- | --- |
| TC-075 | `tests/test_sos_recommendation_api.py::test_sos_search_result_count_is_limited_to_30` | API 结果数规则稳定，不依赖地图/UI。 |
| TC-076 | `tests/test_sos_recommendation_api.py::test_sos_default_distance_sort_is_ascending` | API 默认距离排序稳定，不依赖地图/UI。 |
| TC-077 | `tests/test_sos_recommendation_api.py::test_sos_price_sort_uses_valid_price_ascending_and_empty_price_last` | API 价格排序稳定，并按“无价格排最后”规则断言。 |
| TC-078 | `tests/test_sos_recommendation_api.py::test_sos_flight_time_sort_is_ascending` | API 飞行时间排序稳定，不依赖地图/UI。 |
| TC-079 | `tests/test_sos_recommendation_api.py::test_sos_stop_values_are_limited_to_direct_or_tech_stop` | API 经停值稳定，可直接判断 Direct/Tech-stop。 |
| TC-080 | `tests/test_sos_recommendation_api.py::test_sos_round_trip_search_smoke` | 往返 API smoke 稳定，不执行 UI 表单。 |
| TC-082 | `tests/test_sos_recommendation_api.py::test_sos_nearby_distance_unit_follows_locale` | Nearby 单位由 locale/API 返回决定，可稳定断言。 |

暂不纳入固定自动化：`TC-064` 到 `TC-074`、`TC-081`、`TC-083` 到 `TC-085`。这些用例依赖页面渲染、地图、浮层、权限或 CRM 提交边界，先保留为常规回归用例，不登记到固定自动化矩阵。

## 常规回归用例

| 用例 ID | 原候选 ID | 优先级 | 模块 | 场景 | 前置条件/数据 | 步骤摘要 | 预期结果 | 建议方式 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TC-064 | REG-SOS-001 | P0 | 页面入口 | SOS 多语言入口可访问 | dev/uat 环境 | 访问 `/sos`、`/en-us/sos`、`/zh-cn/sos` | 页面加载成功，显示 SOS Request、SOS Jets Nearby、地图区域 | UI 自动化 |
| TC-065 | REG-SOS-002 | P1 | SEO | SOS 基础 title 校验 | 英文/中文 locale | 读取页面 title | 英文 title 为 SOS 医疗转运相关文案，中文 title 为紧急私人飞机与医疗转运相关文案 | DOM 自动化 |
| TC-066 | REG-SOS-003 | P0 | 首屏布局 | 桌面 Focus Layout | 1600x900 视口 | 打开 `/en-us/sos` | 顶部导航、地图、Nearby 列表、SOS Request 表单可见 | UI 截图 |
| TC-067 | REG-SOS-004 | P0 | SOS Request | From/To 常规城市和机场代码搜索 | Washington/New York/Beijing/Los Angeles/KTEB/ZBAA | 在 From/To 输入城市和机场代码并选择候选 | 可返回并选择正确候选；忽略 `District of Columbia` 特殊城市 | UI + network |
| TC-068 | REG-SOS-005 | P0 | SOS Request | 单程 Request SOS 进入结果页 | Washington -> New York，日期默认当天 | 填 From/To，点击 Request SOS | 进入预估结果区，请求 `searchList` 成功，`tripType=1`、`pax=2`、日期正确 | UI + network |
| TC-069 | REG-SOS-006 | P0 | 结果页 | Search Bar 回填与重新搜索 | 已进入结果页 | 检查 From/To/Date/Passengers；修改目的地后重搜 | UI 回填正确，重搜重新请求 `searchList` | UI + network |
| TC-070 | REG-SOS-007 | P0 | 结果页 | 结果页基础控件展示 | Washington -> New York | 完成搜索后检查页面 | 显示 Back To Map、Distance、Price、Filter、结果列表 | UI 自动化 |
| TC-071 | REG-SOS-008 | P0 | 结果卡片 | 推荐卡片字段展示 | Washington -> New York | 检查前几条结果卡片 | Most Recommended、Direct/Tech-stop、Flight Time、距离、价格、Aircraft Image、Select this flight 可见 | UI 自动化 |
| TC-072 | REG-SOS-009 | P1 | 结果卡片 | Aircraft Image 图片层 | 有结果卡片 | 点击 `Aircraft Image` | 图片层或图片入口打开，不阻塞页面操作 | UI 自动化 |
| TC-073 | REG-SOS-010 | P0 | 报价弹窗 | Select this flight 打开报价弹窗 | 有结果卡片 | 点击第一条 `Select this flight` | 打开 `Request Medical Evacuation Support` 弹窗，显示行程、推荐飞机、联系人表单 | UI 自动化 |
| TC-074 | REG-SOS-011 | P0 | CRM | dev/uat 最终提交 | 仅 dev/uat，测试邮箱和测试手机号 | 填联系人、勾选 consent、Submit | `lead/submitInquiryClueV2` 返回 `success=true`，跳转 `/thankyou`，`sourceChannel=web_medevac` | UI + network |
| TC-075 | REG-SOS-012 | P0 | 推荐逻辑 | 推荐结果数上限 | 多路线 API：Washington-New York、Beijing-Los Angeles、Singapore-Sydney | 调用 `web/sos/search/searchList` | 返回结果数 `<=30` | API 自动化 |
| TC-076 | REG-SOS-013 | P0 | 推荐逻辑 | 默认 Distance 排序 | `orderType=0` 多路线 | 调用 `searchList` 并提取距离字段 | 距离按升序排列 | API 自动化 |
| TC-077 | REG-SOS-014 | P0 | 推荐逻辑 | Price 排序 | `Beijing -> Los Angeles`，`orderType=1` | 点击 Price 或直接 API 请求 | 有效价格从低到高；无价格排最后 | API + UI |
| TC-078 | REG-SOS-015 | P1 | 推荐逻辑 | Flight Time 排序 | `orderType=2` API | 调用 `searchList` | 飞行时间升序 | API 自动化 |
| TC-079 | REG-SOS-016 | P0 | 推荐逻辑 | Direct/Tech-stop 与经停过滤 | 长短途混合路线 | 调用 `searchList`，检查 stop 值和标签 | `stop=0` 为 Direct，`stop=1` 为 Tech-stop，不出现 `stop>1` | API 自动化 |
| TC-080 | REG-SOS-017 | P1 | 往返 | Round Trip API smoke | Washington -> New York，returnTime 次日 | `tripType=2` 请求 `searchList` | 接口成功，结果数 `<=30`，距离排序通过 | API 自动化 |
| TC-081 | REG-SOS-018 | P0 | Nearby | Nearby 列表和 tabs | 默认定位/IP fallback | 打开页面，检查 All/Parked/Scheduled/In Flight | tabs 可见，All 默认可用，列表有分页/卡片 | UI 自动化 |
| TC-082 | REG-SOS-019 | P0 | Nearby | 单位规则 | `en-us` Washington、`en-ca` Toronto、`en-sg` Singapore | 调用 `nearbyAircraft` 或页面检查 | 北美为 `mi`，非北美为 `km` | API 自动化 |
| TC-083 | REG-SOS-020 | P1 | Nearby | 卡片字段和详情 | Nearby 有数据 | 点击第一条 Nearby 卡片 | 显示机型、状态、机场/位置、距离、Category、Range、Recent flights | UI 截图 |
| TC-084 | REG-SOS-021 | P1 | 定位权限 | 定位被阻止提示 | headless/blocked 权限 | 打开页面并阻止定位 | 显示 `Location access is blocked...` 和 `Try again` | UI 自动化 |
| TC-085 | REG-SOS-022 | P1 | 移动端 | 移动端入口 smoke | 390x844 视口 | 打开 `/en-us/sos` | SOS Request 折叠入口、地图、Nearby 卡片可见 | 移动端 UI |

## 不纳入常规回归

| 场景 | 原因 | 建议处理 |
| --- | --- | --- |
| Google Maps Unavailable 强制 fallback | 难稳定模拟真实区域不可用或 12s 超时 | 专项人工/网络代理场景 |
| 地图 marker hover/click、飞线、高亮 | headless 下 Google Maps 渲染不稳定 | 人工浏览器复核或独立地图专项 |
| Try again 后重新授权 | 依赖真实浏览器站点权限恢复 | 人工专项 |
| marker 1min/2min 刷新频率 | 需要长时间观察，且依赖地图稳定 | 性能/稳定性专项 |
| 停场飞机无机场、信号丢失、In Flight 无目的地、无结果页 | 当前 dev 数据不稳定覆盖 | 后端造数后做专项 |
| Nearby 距离小数位 | 文档正文与批注冲突 | 产品确认后再入回归 |
| `District of Columbia` 表单搜索 | 用户确认忽略 | 不纳入本版本回归 |
| `Built for long distance` 文案 | 用户确认忽略 | 不纳入本版本回归 |
| 删除线中的低密度默认隐藏/View more | 已删除需求 | 不测试 |

## 关联索引

| 资产 | 路径 |
| --- | --- |
| 版本执行记录 | `artifacts/官网V4.1.0（SOS）/测试执行记录/测试执行记录_20260624_135557.md` |
| 需求覆盖矩阵 | `artifacts/官网V4.1.0（SOS）/需求分析/需求覆盖矩阵_20260624_执行结果.md` |
| 问题清单 | `artifacts/官网V4.1.0（SOS）/问题清单` |
| 回归候选来源 | `artifacts/官网V4.1.0（SOS）/需求分析/回归测试用例候选_20260626.md` |
| 总用例清单 | `artifacts/测试用例清单.csv` |
