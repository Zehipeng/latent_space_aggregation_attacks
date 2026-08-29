# AutoDL阶段C：离线资产锁定与P0 2-key smoke准备

目标代码：`main`，提交 `a00448064a28260f8846b91d89a78cbfea4f2e9d`。后续若本文件随修订提交，必须以交付消息中的最新完整SHA为准。

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
python scripts/operations/prepare_offline_assets.py \
  --inventory local_assets/autodl_inventory.json \
  --output local_assets/assets.lock.json

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export DIFFUSERS_OFFLINE=1
export HF_DATASETS_OFFLINE=1

python scripts/main_methods/run_budget_selection_pilot.py \
  --config configs/smoke/p0_2key.yaml \
  --assets-lock local_assets/assets.lock.json \
  --offline \
  --preflight-only
```

preflight失败时停止；不得删指标、换模型、换revision或联网回退。

## 5. P0 2-key smoke门槛

P0 smoke只使用`pilot_key_000/pilot_key_001`、三个水印、跨模型、Proposed伪造与移除，保持每100步检测和早停。它必须验证：两任务完成、在线累计ASR链路、最终离线重算、resume恢复、行数/hash、临时图清理。攻击成功不是smoke通过条件。

当前仓库的硬门禁会在三种水印runtime adapter、真实样本manifest或本地资产缺失时停止。不得把`--preflight-only`成功误写成GPU smoke通过，也不得自动进入100-key P0。

## 6. 失败时保留并返回

```bash
git rev-parse HEAD
git status --short
nvidia-smi
python --version
python -m pytest -q
```

同时返回资产preflight输出、smoke命令、退出码、日志末尾、manifest、预期/实际文件数量和异常。失败后必须停止，不能进入100-key P0或正式实验。
