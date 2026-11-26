# 展会周转证件夹滑扣回库复测

回展仓 9 名器材管理员回收会议和展览归还的可循环证件夹。不同版型的滑扣有各自的正常行程和空载复位范围。过去按统一上下限处理，容易把薄夹与宽夹的结构差异列为故障，还常漏掉同版型内启动力和复位时间一起偏离的留滞件。

## 启动与权限

```sh
cp .env.example .env
docker compose build backend
docker compose up -d --no-build --wait
curl -fsS http://127.0.0.1:19438/api/spec
```

`backend` 提供 FastAPI，`worker` 执行核边界筛查，PostgreSQL 16 保存台账、运行、复核和审计，Redis 用于唤醒 worker。数据库宿主端口为 `17938`，API 和数据库均绑定本机。`docker compose down` 保留具名卷。演示数据默认自动加载，也可执行 `docker compose exec -T backend python -m scripts.seed_demo` 检查。

| 演示账号 | 密码 | 权限 |
|---|---|---|
| `analyst@demo.local` | `Demo-2611!` | 导入台账、提交计算、查看未签核结果 |
| `admin@demo.local` | `Demo-2611!` | 审阅复测单、确认或拒绝签核、查看审计 |
| `viewer@demo.local` | `Demo-2611!` | 浏览台账与获批结果、导出交接单 |

`POST /api/auth/login` 接受电子邮件和密码，业务接口使用 `Authorization: Bearer <token>`。OpenAPI JSON 位于 `/api/openapi.json`。

1. `GET /api/spec` 查看字段及 `nu`、`reference_quantile` 的参数范围。`GET /api/datasets` 读取演示台账 ID。
2. `POST /api/datasets` 接收 `{"name":"本周证件夹回库","csv":"…"}`。CSV 依次填写 `part_id,bench_lot,partition,clip_variant,stroke_mm,slide_force_n,settle_ms,guide_gap_mm`。
3. `POST /api/runs` 提交 `{"label":"周五复测单","dataset_id":1,"settings":{"nu":0.12,"reference_quantile":0.92}}`。
4. `GET /api/runs/{id}` 检查优先复测、系列待查及记录区间。`POST /api/runs/{id}/review` 提交 `{"decision":"approved","note":"已确认同批复测安排"}`。
5. 从 `/api/runs/{id}/export/badge_retest` 下载扣件、原始读数、复测口径及最近历史参照件。`series_calibration` 和 `calibration_parts` 可单独导出。

## 模型与适用范围

整批区分参考、校准和待检。每个版型至少需要 12 条不同的参考测次。用参考件标准化四个读数并拟合 RBF 一类 SVM，新颖度取模型判别函数的相反数。数值越高，测件越偏离学习到的正常边界。最近参考件只用于追溯人工复测。各系列使用至少 10 条独立校准件，以 `higher` 规则取校准分位作为阈值。分数严格越线的待检件列为优先复测。未知夹体版型、参照或校准量不足时进入人工核查。参照数据、分位配置和版型覆盖共同决定结果。

业务算法、数据约束和报表在 `backend/src/domain`。`reference`、`calibration` 和 `pending` 在 `settings.py` 定义，并由 `records.py` 校验。`Role`、`RunStatus` 和 `Decision` 位于 `backend/src/constants/workflow.py`，供权限与运行签核流程共用。环境变量样例位于 `.env.example`。第三方依赖采用各自的许可证。
