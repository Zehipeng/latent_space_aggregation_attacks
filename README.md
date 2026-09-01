# Latent Space Aggregation Attacks

本项目是 `formal_protocol_v1.15` 的正式代码项目。权威协议快照位于
`docs/protocols/formal_protocol_v1.15.md`；历史项目
`jain_multiref_latent_experiment/` 只作为算法回归来源，不是正式运行入口。

正式伪造与移除的固定预算均已冻结为1500步，移除beta网格冻结为`[1.0,1.5,2.0]`，
主设置为`beta=1.0`。用户已取消后续P0与50-key固定预算确认；v1.14的P0和诊断配置及
结果只读保留，不并入正式统计。正式批次仍必须先通过同配置2-key smoke。

## 威胁模型

攻击进程只可访问同密钥水印参考图、公开 SD1.4 代理 VAE、非配对干净图和待攻击图。
它不得导入、初始化或调用目标检测器。正式攻击固定运行至任务级预算
`T_forgery_formal`或`T_removal_formal`；检测与质量评价
由独立进程在攻击完成后执行。历史P0允许在线检测并早停，但v1.15不再执行P0。

## 目录

- `configs/budget_pilot/`：只读保留的v1.14伪造/移除P0配置。
- `configs/diagnostics/`：不并入P0或正式统计的预注册参数诊断。
- `configs/formal/formal_v1p15.yaml`：冻结为双任务1500步的200-key正式配置。
- `configs/smoke/`：P0或正式2-key smoke配置。
- `src/.../core/`：配置、seed、manifest、原子I/O、ledger、resume、锁、smoke gate。
- `src/.../data/`：200-key正式集合、50-key P0子集及嵌套参考集合。
- `src/.../models/`：离线资产锁和本地模型加载。
- `src/.../watermarks/`：Tree-Ring、RingID、Gaussian Shading统一接口。
- `src/.../methods/proposed/`：Proposed伪造/移除与检测器无关的优化器。
- `src/.../methods/baselines/`：Jain、RGB Simple Averaging、E6、E7。
- `src/.../evaluation/`：最终指标、错误身份、资格、统计与spool校验。
- `src/.../plotting/`：固定列结构和五张2×3轨迹图。
- `scripts/`：轻量CLI；算法权威实现只在 `src/`。

## 脚本索引

| 脚本 | 用途 | 主要输入 | 主要输出 |
|---|---|---|---|
| `main_methods/run_forgery.py` | Proposed固定预算伪造 | config、assets lock、manifest | 最终图、resume、ledger |
| `main_methods/run_removal.py` | Proposed固定预算移除 | 同上 | 同上 |
| `main_methods/run_forgery_budget_pilot.py` | 伪造P0在线早停 | 伪造P0 config/manifest | 伪造P0 CSV、曲线、总结 |
| `main_methods/run_removal_budget_pilot.py` | 移除P0在线早停 | 移除P0 config/manifest | 移除P0 CSV、曲线、总结 |
| `main_methods/run_removal_beta_diagnostic.py` | beta=1.5固定预算移除诊断 | 10-key诊断config/manifest | ASR、质量、优化进度、最终图 |
| `baselines/run_jain_forgery.py` | Jain伪造 | 正式输入 | 最终输出 |
| `baselines/run_jain_removal.py` | Jain移除 | 正式输入 | 最终输出 |
| `baselines/run_simple_averaging.py` | RGB非配对均值差、γ=1 | R/C manifest | 最终输出 |
| `baselines/run_distortion_removal.py` | 五种固定E6变换 | 水印目标 | 最终输出 |
| `evaluation/evaluate_final.py` | 独立最终评价 | evaluation spool、manifest | 最终逐key/汇总/统计CSV |
| `evaluation/evaluate_detector_trajectories.py` | E3–E5离线轨迹评价 | curve spool | 两份轨迹CSV |
| `evaluation/build_tables_and_figures.py` | 固定主表和论文图 | 评价CSV | 表格、PNG/PDF |
| `operations/run_formal_batch.py` | 唯一正式编排入口 | 冻结配置、资产锁 | smoke→200-key→评价→表图 |
| `operations/prepare_offline_assets.py` | 锁定已准备的本地资产 | 资产inventory | `assets.lock.json` |
| `operations/build_manifests.py` | 校验预注册清单 | JSON spec | 校验报告 |
| `operations/build_prompt_manifest.py` | 从锁定的 Gustavosta train parquet 构造互不重叠的 P0/正式 64-candidate banks | parquet、固定SHA-256 | 19200行提示词manifest |
| `operations/build_coco_manifests.py` | 从val2017构造P0/正式目标、clean-prior及角色重叠审计 | val2017、instances JSON | 五份CSV manifest |
| `operations/run_tree_ring_regression.py` | 在GPU上用相同输入比较新旧Tree-Ring、预处理、目标与10步优化 | 新资产锁、只读旧项目 | JSON等价性报告 |
| `operations/estimate_runtime.py` | P50/P90 ETA与磁盘预算输入检查 | 实测记录 | ETA JSON/报告 |
| `operations/inspect_run.py` | 只读检查配置 | config | 协议/hash/规模 |
| `operations/build_cleanup_inventory.py` | 仅生成dry-run清理清单 | run目录 | JSON清单，不删除 |

## 固定方法定义

- Proposed伪造：参考VAE latent先转FP32后直接算术平均。
- Proposed移除：`z_target - beta * (mean(z_w)-mean(z_c))`。
- Jain伪造：索引0单参考latent。
- Jain移除：目标图全局像素均值构成的常量图，经同一代理VAE编码。
- Simple Averaging：RGB域非配对均值差，`gamma=1`。
- 优化：单阶段、element-wise mean MSE、无动量像素梯度下降、学习率0.02。

## 离线资产准备

联网下载与正式运行必须物理分离。`prepare_offline_assets.py` 本身不会下载，只把用户已明确
准备的绝对路径、revision、大小和SHA-256写入锁文件。正式命令必须使用 `--offline`；
缺失路径、错误哈希、未锁定模型/水印代码会立即失败。禁止运行期联网回退。

## 断点续跑

最小单元为 `condition_id + key_id + method`。每50步覆盖保存图像tensor、step、loss、
Python/NumPy/PyTorch CPU/CUDA RNG、分项时间和协议/配置/Git/输入hash。状态通过临时文件、
flush/fsync和原子替换写入。COMPLETE单元经完整性校验后跳过；损坏状态只重跑该单元并应
记录 recovery event。smoke pass 与五项hash签名绑定，签名不匹配禁止进入200-key阶段。

## 结果目录

每个run严格使用协议第11节目录。除 `evaluation_spool/` 和 `curve_checkpoint_spool/` 外，
批量清理都必须先生成清单并获得用户授权。三项可视化key为 `key_000/key_100/key_199`。

## 保留与清理

| 类别 | 内容 |
|---|---|
| 提交Git | `src/`、`scripts/`、`configs/`、`tests/`、README、依赖锁、小型schema、协议快照 |
| 不提交 | 模型、数据、密钥tensor、图片、checkpoint、日志、结果包、缓存、凭据 |
| 永久研究记录 | 配置/协议快照、manifest、最终逐key与汇总CSV、轨迹CSV、表图、hash、一次最终总结 |
| 协议允许自动清理 | 两个spool中通过行数/hash/图校验且不属于三个可视化key的文件 |
| 仅清单候选 | 完成单元resume、下载碎片、构建缓存；工具不得直接删除 |

## 测试

```bash
python -m pytest -q
python scripts/operations/inspect_run.py --config configs/formal/formal_v1p15.yaml
python scripts/operations/inspect_run.py --config configs/smoke/formal_v1p15_2key.yaml
```

## 历史P0与诊断

下列v1.14命令只用于追溯已经完成的实验，不再作为v1.15待运行流程，也不能使用v1.15代码
重新写入原run目录：

```bash
python scripts/main_methods/run_removal_beta_diagnostic.py \
  --config configs/diagnostics/removal_beta_1p5_10key.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --run-id removal_beta15_v114_r1
```

该命令自动先跑2-key smoke，再跑10-key、30单元固定预算诊断。攻击过程不检测、不早停，
不保存检查点PNG；最终汇总列固定为ASR、l2、linf、LPIPS、SSIM、PSNR和
`optimization_progress_pct`。用户审阅诊断结果后再决定是否升级移除P0的beta。

伪造P0与移除P0必须分别运行，不能复用同一run-id或结果目录：

```bash
python scripts/main_methods/run_forgery_budget_pilot.py \
  --config configs/budget_pilot/p0_forgery.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --run-id p0_forgery_v114_r1

python scripts/main_methods/run_removal_budget_pilot.py \
  --config configs/budget_pilot/p0_removal.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --run-id p0_removal_v114_r1
```

中断后原样重跑同一命令和`run-id`即可续跑；完整单元直接跳过，活动单元从最近50步状态恢复。
P0不持久保存参考PNG；参考图在需要时按预注册prompt/seed重新生成并核对规范RGB8哈希。
每个任务的2-key smoke保存6张攻击终点PNG，50-key P0保存150张攻击终点PNG，并只生成
本任务的一张累计ASR曲线。伪造失败单元保存第3000步终点；移除失败单元保存当前第15000步
终点。两个任务的CSV和曲线不得混合。

v1.15后续GPU验收从正式2-key smoke开始。smoke必须使用
`configs/smoke/formal_v1p15_2key.yaml`并跑满1500步；通过后同一编排流程才可进入200-key正式实验。

## 当前明确门禁

正式资产与manifest仍须显式锁定Tree-Ring为`channel=0,radius=16,p<=0.05`、RingID的`p<=0.05`、
Gaussian Shading官方ChaCha20变体及FPR=`1e-6`对应的bit-accuracy阈值。每个key和水印
从64个预注册有序候选中选择最先通过正式阈值的5张参考，并持久记录全部已测试候选及
选中图像哈希；不足25张时批次失败。启动时同时核对三种官方代码revision。正式配置中的
`T_forgery_formal/T_removal_formal`必须均为1500，移除beta网格必须为`[1.0,1.5,2.0]`。

当前`run_formal_batch.py`仍是显式门禁占位实现：配置已经冻结不等于正式编排链已经完成。
在编排器、正式方法入口和独立评价链完成并通过GPU smoke前，不得声称200-key正式实验已可运行。
