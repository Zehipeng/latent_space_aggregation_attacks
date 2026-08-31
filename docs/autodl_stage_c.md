# AutoDL阶段C：离线资产锁定与P0执行

目标代码：`main`。必须以每次交付消息中的最新完整SHA为准，不使用本文档历史版本里的旧SHA。

## 1. 同步完全相同的提交

```bash
source /etc/network_turbo
mkdir -p /root/autodl-tmp/project
cd /root/autodl-tmp/project
git clone https://github.com/Zehipeng/latent_space_aggregation_attacks.git
cd latent_space_aggregation_attacks
git config http.version HTTP/1.1
git switch main
git pull --ff-only
git rev-parse HEAD
git status --short
```

`git rev-parse HEAD`必须等于本次交付SHA，`git status --short`必须为空。

## 2. 先做只读缓存预检

固定HF缓存根目录：`/root/autodl-tmp/cache/huggingface/hub`。不要先下载。检查：

```bash
export HF_HOME=/root/autodl-tmp/cache/huggingface
export HF_HUB_CACHE=/root/autodl-tmp/cache/huggingface/hub
export HUGGINGFACE_HUB_CACHE=/root/autodl-tmp/cache/huggingface/hub
find "$HF_HUB_CACHE" -maxdepth 3 -type d -name 'snapshots' -print
find /root/autodl-tmp/assets /root/autodl-tmp/data -maxdepth 3 -type d -print 2>/dev/null
```

将模板复制为不提交Git的本机inventory，并把所有`REPLACE_*`替换为实际绝对路径/revision：

```bash
mkdir -p local_assets
cp configs/assets/autodl_inventory.template.json local_assets/autodl_inventory.json
```

## 3. 仅补齐缺失资产的独立联网阶段

只在缓存预检确认缺失后执行。加载`/etc/network_turbo`，临时取消离线变量；模型必须按协议固定revision下载到指定HF缓存。三种水印官方代码锁定为：

- Tree-Ring：`3015283d9cf82e90b628f02ad2121bd37408ca9a`
- RingID：`45631a59aecd7d63ccdb640aaaf3e616fdb89fb9`
- Gaussian Shading：`09c678fadc7545acf7be12647ddf2a5e66f6a9dc`

禁止关闭SSL验证，禁止使用浮动HEAD代替上述commit。下载结束后逐项实际加载一次，然后退出联网阶段。

## 4. 生成并验证资产锁

```bash
mkdir -p /root/autodl-tmp/assets/manifests/formal_protocol_v1.10_coco

PROMPT_SHA=$(python -c 'import json; p=json.load(open("local_assets/assets.lock.json")); print(next(x["sha256"] for x in p["assets"] if x["name"]=="stable-diffusion-prompts-train"))')

python scripts/operations/build_prompt_manifest.py \
  --train-parquet /root/autodl-tmp/cache/huggingface/hub/datasets--Gustavosta--Stable-Diffusion-Prompts/snapshots/d816d4a05cb89bde39dd99284c459801e1e7e69a/data/train.parquet \
  --output /root/autodl-tmp/assets/manifests/formal_protocol_v1.10_prompt_manifest.csv \
  --expected-sha256 "$PROMPT_SHA"

python scripts/operations/build_coco_manifests.py \
  --val-dir /root/autodl-tmp/data/coco2017/val2017 \
  --instances /root/autodl-tmp/data/coco2017/annotations/instances_val2017.json \
  --output-dir /root/autodl-tmp/assets/manifests/formal_protocol_v1.10_coco

cp configs/assets/autodl_inventory.template.json local_assets/autodl_inventory.json

python scripts/operations/prepare_offline_assets.py \
  --inventory local_assets/autodl_inventory.json \
  --output local_assets/assets.lock.json

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export DIFFUSERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1

python scripts/main_methods/run_forgery_budget_pilot.py \
  --config configs/smoke/p0_forgery_2key.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --preflight-only

python scripts/main_methods/run_removal_budget_pilot.py \
  --config configs/smoke/p0_removal_2key.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --preflight-only

python scripts/main_methods/run_removal_beta_diagnostic.py \
  --config configs/diagnostics/removal_beta_1p5_10key.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --preflight-only

python scripts/operations/run_tree_ring_regression.py \
  --config configs/budget_pilot/p0_forgery.yaml \
  --assets-lock local_assets/assets.lock.json \
  --legacy-project /root/autodl-tmp/project/jain_multiref_latent_experiment \
  --output /root/autodl-tmp/实验结果/regression/tree_ring_v110.json \
  --offline
```

preflight失败时停止；不得删指标、换模型、换revision或联网回退。

## 5. beta=1.5诊断与两个独立P0

三个入口各自先使用`pilot_key_000/pilot_key_001`完成smoke。伪造P0上限3000，移除P0当前上限15000，均每100步在线检测早停；每个P0 smoke应有6张攻击终点PNG和1张本任务曲线。beta诊断固定3000步、不中途检测、不早停、不保存检查点PNG，其smoke验证最终ASR、质量与优化进度评价链。

三种水印runtime与P0编排器已经接通。只运行smoke时增加`--smoke-only`；退出码为0且
`smoke_report.json`为`PASSED`才表示真实GPU smoke通过。preflight成功仍不等于smoke通过。

```bash
python scripts/main_methods/run_removal_beta_diagnostic.py \
  --config configs/diagnostics/removal_beta_1p5_10key.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --run-id removal_beta15_v114_r1

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

每个命令都会先复用或完成本入口自己的smoke，再进入10-key诊断或50-key P0。中断时只原样重跑对应命令；禁止把三个run-id或输出目录混用。

## 6. 失败时保留并返回

```bash
git rev-parse HEAD
git status --short
nvidia-smi
python --version
python -m pytest -q
```

同时返回资产preflight输出、smoke命令、退出码、日志末尾、manifest、预期/实际文件数量和异常。失败后必须停止，不能进入50-key P0或正式实验。
