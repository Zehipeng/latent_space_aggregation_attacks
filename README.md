# Latent Space Aggregation Attacks

本项目是 `formal_protocol_v1.21` 的正式代码项目。权威协议增量快照位于
`docs/protocols/formal_protocol_v1.21.md`，其基线为v1.20；历史项目
`jain_multiref_latent_experiment/` 只作为算法回归来源，不是正式运行入口。

正式伪造与移除的固定预算均已冻结为150步，移除beta网格冻结为`[1.0,1.5,2.0]`，
主设置为`beta=1.5`。用户已取消后续P0与50-key固定预算确认；v1.14的P0和诊断配置及
结果只读保留，不并入正式统计。正式批次仍必须先通过同配置2-key smoke。

## 威胁模型

攻击进程只可访问同密钥水印参考图、公开 SD1.4 代理 VAE、非配对干净图和待攻击图。
它不得导入、初始化或调用目标检测器。正式攻击固定运行至任务级预算
`T_forgery_formal`或`T_removal_formal`；检测与质量评价
由独立进程在攻击完成后执行。历史P0允许在线检测并早停，但v1.21不再执行P0。

## 目录

- `configs/current/`：唯一当前配置；含v1.21正式与2-key smoke。
- `configs/archive/`：v1.15/v1.16、P0、诊断和模板配置，只读保留。
- `src/.../attack.py`：标量与批量固定预算攻击优化器，主攻击函数的最浅入口。
- `src/.../latent_targets.py`：Proposed伪造/移除latent目标定义。
- `src/.../formal/`：正式生命周期，固定为`prepare → attack → evaluate → orchestrate`。
- `src/.../core/`：仅保留配置、seed、manifest、原子I/O、ledger、resume、锁和门禁等通用基础设施。
- `src/.../archive/`：历史P0运行时，只读且不进入v1.21正式路径。
- `src/.../data/`：200-key正式集合、50-key P0子集及嵌套参考集合。
- `src/.../models/`：离线资产锁和本地模型加载。
- `src/.../watermarks/`：Tree-Ring、RingID、Gaussian Shading统一接口。
- `src/.../methods/baselines/`：Jain、RGB Simple Averaging、E6、E7。
- `src/.../evaluation/`：通用质量指标与资格判定；正式评价入口在`formal/evaluate.py`。
- `src/.../plotting/`：固定列结构的最终结果表图。
- `scripts/run_formal.py`：唯一正式运行入口。
- `scripts/validate_tree_ring.py`：正式GPU回归门禁。`validate_batching.py`仅用于追溯v1.17失败门禁，不属于v1.21启动链。
- `scripts/operations/`：资产与manifest准备、检查和清理清单工具。
- `scripts/archive/`：历史P0入口和未接线占位脚本；不属于当前运行路径。

## 脚本索引

| 脚本 | 用途 | 主要输入 | 主要输出 |
|---|---|---|---|
| `run_formal.py` | 唯一正式编排入口 | 冻结配置、资产锁 | smoke→200-key→评价→表图 |
| `operations/prepare_offline_assets.py` | 锁定已准备的本地资产 | 资产inventory | `assets.lock.json` |
| `operations/build_manifests.py` | 校验预注册清单 | JSON spec | 校验报告 |
| `operations/build_prompt_manifest.py` | 从锁定的 Gustavosta train parquet 构造互不重叠的 P0/正式 64-candidate banks | parquet、固定SHA-256 | 19200行提示词manifest |
| `operations/build_coco_manifests.py` | 从val2017构造P0/正式目标、clean-prior及角色重叠审计 | val2017、instances JSON | 五份CSV manifest |
| `validate_tree_ring.py` | 在GPU上用相同输入比较新旧Tree-Ring、预处理、目标与10步优化 | 新资产锁、只读旧项目 | JSON等价性报告 |
| `validate_batching.py` | 追溯v1.17标量与批量失败门禁 | 归档v1.17 config、资产锁 | 历史诊断JSON，不进入v1.21门禁 |
| `operations/estimate_runtime.py` | P50/P90 ETA与磁盘预算输入检查 | 实测记录 | ETA JSON/报告 |
| `operations/inspect_run.py` | 只读检查配置 | config | 协议/hash/规模 |
| `operations/build_cleanup_inventory.py` | 仅生成dry-run清理清单 | run目录 | JSON清单，不删除 |

历史P0入口位于`scripts/archive/p0/`；未接入正式编排的5行占位脚本位于
`scripts/archive/placeholders/`。它们不属于当前CLI索引，也不会被正式流程调用。

## 固定方法定义

- Proposed伪造：参考VAE latent先转FP32后直接算术平均。
- Proposed移除：`z_target - beta * (mean(z_w)-mean(z_c))`。
- Jain伪造：索引0单参考latent。
- Jain移除：目标图全局像素均值构成的常量图，经同一代理VAE编码。
- Simple Averaging：RGB域非配对均值差，`gamma=1`。
- 优化：单阶段、element-wise mean MSE、无动量像素梯度下降、学习率0.02。
- v1.21沿用v1.20的标量执行：攻击优化、DDIM反演和参考VAE编码的batch size均固定为1。v1.17的FP16真批量设置未通过GPU等价性门禁，不得用于v1.21。
- v1.21不保存检测轨迹检查点，也不生成检测轨迹图；只评价冻结终点的目标密钥和图像质量，不报告RMSE或Wilson置信区间。
- 参考latent缓存以模型设置、水印、key、参考图SHA-256和预处理契约为键，只保存FP32张量；不同哈希绝不复用。

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

AutoDL统一输出根目录为`/root/autodl-tmp/outputs`。其中：

- `budget_selection_pilot/`：历史P0的smoke、50-key预算曲线、首次成功步数和总结；伪造与移除物理分开。
- `diagnostics/`：不并入P0或正式统计的参数诊断，例如beta=1.5的10-key移除诊断。
- `launch_logs/`：启动命令、stdout/stderr、后台进程状态和退出码；日志本身不是实验结论。
- `regression/`：新旧实现、预处理、水印生成/检测和短步优化的一致性回归报告。
- `smoke/`：2-key门禁结果，用于验证资产、配置、恢复和评价链；不得并入200-key正式统计。
- 后续正式实验按`outputs/<experiment_id>/<run_id>/`建立不可覆盖目录。

每个run严格使用协议第11节目录。除 `evaluation_spool/` 外，
批量清理都必须先生成清单并获得用户授权。三项可视化key为 `key_000/key_100/key_199`。

## 保留与清理

| 类别 | 内容 |
|---|---|
| 提交Git | `src/`、`scripts/`、`configs/`、`tests/`、README、依赖锁、小型schema、协议快照 |
| 不提交 | 模型、数据、密钥tensor、图片、checkpoint、日志、结果包、缓存、凭据 |
| 永久研究记录 | 配置/协议快照、manifest、最终逐key与汇总CSV、最终表图、hash、一次最终总结 |
| 协议允许自动清理 | `evaluation_spool/`中通过行数/hash校验且不属于三个可视化key的文件 |
| 仅清单候选 | 完成单元resume、下载碎片、构建缓存；工具不得直接删除 |

## 测试

```bash
python -m pytest -q
python scripts/operations/inspect_run.py --config configs/current/formal_v1p21.yaml
python scripts/operations/inspect_run.py --config configs/current/smoke_v1p21_2key.yaml
```

## 正式伪造运行

正式伪造只通过`scripts/run_formal.py`启动。编排器为准备、攻击、评价分别创建
独立Python进程；攻击进程只加载SD1.4代理VAE，不导入或调用目标检测器。首次命令完成
同配置2-key smoke并生成GPU实测ETA与磁盘估计，不会自动进入200-key：

先在本次提交、正式配置和资产锁上完成新旧Tree-Ring等价性门禁：

```bash
python scripts/validate_tree_ring.py \
  --config configs/current/formal_v1p21.yaml \
  --assets-lock local_assets/assets.lock.json \
  --legacy-project /root/autodl-tmp/project/jain_multiref_latent_experiment_legacy \
  --output /root/autodl-tmp/outputs/regression/tree_ring_v1p21.json \
  --offline
```

回归报告必须为`PASSED`，且Git、配置和资产锁会由正式编排器再次核对。然后运行smoke：

```bash
python scripts/run_formal.py \
  --config configs/current/formal_v1p21.yaml \
  --smoke-config configs/current/smoke_v1p21_2key.yaml \
  --assets-lock local_assets/assets.lock.json \
  --tree-ring-regression-report /root/autodl-tmp/outputs/regression/tree_ring_v1p21.json \
  --task forgery \
  --run-id <run_id> \
  --offline \
  --smoke-only
```

检查`outputs/smoke/formal_forgery/<run_id>_smoke/smoke_report.json`为`PASSED`，并审阅同目录
`runtime_estimate.json`中的P50/P90与spool磁盘估计。确认后以相同run-id执行：

```bash
python scripts/run_formal.py \
  --config configs/current/formal_v1p21.yaml \
  --smoke-config configs/current/smoke_v1p21_2key.yaml \
  --assets-lock local_assets/assets.lock.json \
  --tree-ring-regression-report /root/autodl-tmp/outputs/regression/tree_ring_v1p21.json \
  --task forgery \
  --run-id <run_id> \
  --offline \
  --approve-full-run
```

第二条命令复核回归报告及五项smoke签名后才运行200-key。中断后原样重跑：完整单元经图像
哈希校验后跳过，活动迭代单元从最近50步状态恢复。评价临时spool仅在持久CSV、
表图和哈希全部验证后自动清理，并写入清理inventory与ledger；三个可视化key的持久图不受
影响。当前正式编排范围为伪造E0/E1/E3/E4/E7；正式移除入口仍未开放。

## 历史P0与诊断

下列v1.14命令只用于追溯已经完成的实验，不再作为v1.17待运行流程，也不能使用v1.17代码
重新写入原run目录：

```bash
python scripts/archive/p0/run_removal_beta_diagnostic.py \
  --config configs/archive/diagnostics/removal_beta_1p5_10key.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --run-id removal_beta15_v114_r1
```

该命令自动先跑2-key smoke，再跑10-key、30单元固定预算诊断。攻击过程不检测、不早停，
不保存检查点PNG；最终汇总列固定为ASR、l2、linf、LPIPS、SSIM、PSNR和
`optimization_progress_pct`。用户审阅诊断结果后再决定是否升级移除P0的beta。

伪造P0与移除P0必须分别运行，不能复用同一run-id或结果目录：

```bash
python scripts/archive/p0/run_forgery_budget_pilot.py \
  --config configs/archive/budget_pilot/p0_forgery.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --run-id p0_forgery_v114_r1

python scripts/archive/p0/run_removal_budget_pilot.py \
  --config configs/archive/budget_pilot/p0_removal.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --run-id p0_removal_v114_r1
```

中断后原样重跑同一命令和`run-id`即可续跑；完整单元直接跳过，活动单元从最近50步状态恢复。
P0不持久保存参考PNG；参考图在需要时按预注册prompt/seed重新生成并核对规范RGB8哈希。
每个任务的2-key smoke保存6张攻击终点PNG，50-key P0保存150张攻击终点PNG，并只生成
本任务的一张累计ASR曲线。伪造失败单元保存第3000步终点；移除失败单元保存当前第15000步
终点。两个任务的CSV和曲线不得混合。

v1.21 GPU验收先运行Tree-Ring回归门禁，再进入正式2-key smoke。smoke使用
`configs/current/smoke_v1p21_2key.yaml`以逐张方式跑满150步；通过、审阅ETA并显式批准后，
同一编排流程才可进入200-key正式实验。

## 当前明确门禁

正式资产与manifest仍须显式锁定Tree-Ring为`channel=0,radius=16,p<=0.05`、RingID的`p<=0.05`、
Gaussian Shading官方ChaCha20变体及FPR=`1e-6`对应的bit-accuracy阈值。每个key和水印
从64个预注册有序候选中选择最先通过正式阈值的25张参考，并持久记录全部已测试候选及
选中图像哈希；不足25张时批次失败。启动时同时核对三种官方代码revision。正式配置中的
`T_forgery_formal/T_removal_formal`必须均为150，移除beta网格必须为`[1.0,1.5,2.0]`，正式移除主设置必须为`main_beta=1.5`。

`scripts/run_formal.py`已接通正式伪造的准备、三方法攻击、独立最终目标密钥/质量/FID评价、
最终表图、恢复和smoke门禁。v1.21不计算错误密钥接受率、Target rank、Top-1、RMSE、Wilson置信区间、配对检验或Holm校正，也不保存第100步轨迹检查点或生成轨迹六面板图。实际GPU smoke通过前不得启动200-key；正式移除
仍须在其独立执行链完成后另行开放。
