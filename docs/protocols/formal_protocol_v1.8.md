# 基于多参考潜空间聚合的扩散模型水印黑盒伪造与移除：正式实验设置

## Material Passport

- Origin Skill: academic-research-suite / experiment-agent
- Origin Mode: plan
- Protocol Version: `formal_protocol_v1.8`
- Protocol Date: 2026-08-29
- Verification Status: `UNVERIFIED`（本文件是正式实验预注册协议，不是实验结果）
- Source Draft: `C:\Users\dell\Desktop\实验设置.docx`
- Research Code: `C:\Users\dell\Desktop\codex学习文档\jain_multiref_latent_experiment`

### v1.8 变更记录（2026-08-29）

- 修正第5.2节本文移除方法的重复粘贴：保留一次水印方向与目标latent定义，并将误重复的第三个公式块恢复为单阶段优化目标。
- 本次仅修正文档公式，不改变移除方向、$\beta$、参考集合、质量约束、实验矩阵或评价协议。

### v1.7 变更记录（2026-08-29）

- 为Proposed伪造与移除攻击新增五组“检测统计量—迭代步数”线型图：伪造$\lambda$、伪造$N$、移除$\lambda$、移除$N$、移除$\beta$。
- 每张图采用2行模型设置 × 3列水印的六面板布局；每个面板只绘制对应超参数的三根线。Tree-Ring/RingID纵轴为p值，Gaussian Shading纵轴为bit accuracy，横轴为每100步评价点。
- 正式攻击仍为零查询固定预算。所有200-key中间图像只临时保存并在攻击完成后由独立评价进程计算曲线，永久保留曲线CSV和图，不把检测反馈传回攻击进程。

### v1.6 变更记录（2026-08-29）

- P0预算选择实验只运行跨模型设置；正式E0–E7同时运行同模型和跨模型设置。
- 将四类结果表拆成用户指定的独立列结构：$\lambda$表、$N$表、方法表和$\beta$表；各表均保留 `Watermark` 与 `Model` 列，并横向报告ASR、失真、感知质量、FID和时间。
- 因正式实验恢复两种模型设置且常规外部变换也覆盖两种设置，正式唯一输出规模更新为34800，其中21600个为固定预算迭代攻击。

### v1.5 变更记录（2026-08-29）

- 删除同模型实验，P0、主实验、敏感性实验和外部基线统一只保留跨模型设置：目标生成/检测模型为 SD2-base，攻击代理为 SD1.4 VAE。
- 按用户提供的论文表格版式重构结果表：按水印分组、按方法与参数展开，并横向报告 ASR、$l_2$、$l_\infty$、LPIPS、SSIM、PSNR、FID 和时间；参考图中的数值不作为本项目数据。
- 相应将正式唯一输出规模从 31800 下调为 17400，固定预算迭代攻击单元从 21600 下调为 10800；P0 在线早停阶段为 600 个攻击单元，每次候选固定预算确认另需 600 个单元。

### v1.4 变更记录（2026-08-29）

- 在正式实验前新增 100-key 迭代预算选择实验，分别运行本文伪造与移除方法，采用主设置、$N=5$ 和候选上限 1500 步。
- 预算选择实验允许每 100 步调用一次检测器并在成功后早停，输出 100–1500 步的累计 ASR；该在线反馈协议只用于冻结正式固定预算，不属于正式黑盒结果。
- 在线早停累计 ASR 只用于提出候选预算；冻结前必须用同100个pilot key完成一次无检测、无早停的固定预算确认，避免把“曾经成功”误当成固定步数成功率。
- 预算选择所用 100 个逻辑 key 与正式 200-key 测试集严格不重叠。正式预算确定后必须升级协议并锁定一个所有正式方法共享的固定 $T_{\mathrm{formal}}$，正式实验仍禁止检测器查询和早停。

### v1.3 变更记录（2026-08-29）

- 将实验复现主种子锁定为 `master_seed=205`，并同步更新稳定子种子派生字符串。
- 明确移除攻击目标固定为参与 $R_N$ 聚合的第一张水印参考图，即索引 0，且 `target_in_reference_aggregate=true`。
- 正式实验的ASR、质量和成本主结论只评价固定预算最终输出：取消每50步永久数值日志、通用逐检查点评价和确定性逐步重放；每50步仅保留覆盖式临时恢复状态。v1.7另行预注册的五组p值/bit accuracy轨迹是唯一正式迭代趋势例外。
- 最终研究产物精简为紧凑的最终逐 key 指标表、条件级最终汇总、论文所需最终表图和每个 run 的一次最终总结。

### v1.2 变更记录（2026-08-29）

- 当时计划为全部 200 keys 保存每 50 步数值日志和全部最终评价指标；其中每 50 步永久数值日志及逐步评价已由 v1.3 取消。
- 3 个 key 固定为 `key_000`、`key_100`、`key_199`；迭代方法每 150 步保存一次 PNG。
- 每个正式实验批次先用 `key_000`、`key_001` 完成一次同配置小规模 smoke test；通过后由同一工作流直接启动 200-key 正式实验。

### v1.1 变更记录（2026-08-29）

- 将随机种子拆分为实验主种子、生成噪声种子、水印密钥种子和变换/控制种子，并采用稳定命名空间派生。
- 增加正式运行前 ETA 估计、运行中剩余时间更新、完全离线运行和断点续跑契约。
- 锁定未来重构项目名为 `latent_space_aggregation_attacks`，规定主方法、基线、评价和工具脚本分层。
- 中间检查点 PNG 只永久保存少量预注册 key；该规则已由 v1.2 收紧为 3 个 key、每 150 步保存。v1.3 取消其他 key 的离线逐步重放。

## 1. 文档地位与执行原则

本文件是本项目后续正式实验、正式代码配置、正式结果评价和论文实验部分的最高优先级执行规范。历史方案、预实验配置、学习卡片和论文初稿只用于解释研究演变，不得覆盖本文件。

若代码、配置、README、旧实验清单或旧结论与本文件冲突，必须停止正式运行并先修正实现或由用户明确批准升级协议版本；不得静默改变样本、参数、阈值、预算或统计口径。任何协议变更必须：

1. 形成新的版本号和变更记录；
2. 在运行前完成，不能观察结果后追溯修改；
3. 不覆盖旧配置、旧日志或旧结果；
4. 在论文中披露与本协议的差异。

## 2. 研究问题、假设与证据边界

### 2.1 研究问题

在不能访问目标生成模型参数、目标水印密钥和攻击过程检测器反馈的黑盒条件下，攻击者能否仅利用少量同密钥水印参考图像、公开代理 VAE 和非配对干净图像，高效完成潜在噪声扩散水印的伪造与移除？

### 2.2 预注册假设

- H1（伪造）：在相同固定优化预算下，多参考潜空间平均比 Jain 单参考潜空间目标获得更高的伪造 ASR，或在 ASR 相当时产生更小的图像扰动。
- H2（移除）：多参考水印 latent 均值与非配对干净 latent 均值的差分方向，可在与 Jain 相同固定预算下实现更好的 ASR—图像质量折中。
- H3（样本效率）：本文方法在主设置 $N=5$ 下已能体现相对优势；$N\in\{1,5,25\}$ 的单因素实验用于测量参考数量影响，不预设 $N=25$ 必然最优。
- H4（跨水印）：在固定跨模型代理设置下，Tree-Ring 上的阶段性结果能否迁移至 RingID、Gaussian Shading，属于待验证问题。

### 2.3 已验证与待验证

- 已有阶段性证据：Tree-Ring 伪造预实验中，五参考 latent 平均优于 Jain 单参考基线；该结果来自历史小样本和在线检测协议，不是本文件定义的正式固定预算结论。
- 已有小规模证据：Tree-Ring 跨模型移除的 10-key、$T=1000$、$\beta=1$ 试验中，`mean_shift` 与 Jain 均达到 100% ASR，但 `mean_shift` 图像质量更好；该结论不外推至 200 keys、其他水印或正式协议。
- 待验证：跨模型正式零查询固定预算结果、RingID、Gaussian Shading、$\lambda/N/\beta$ 敏感性和常规变换基线。
- 禁止预写为结论：多参考“一定更好”、五参考“最优”、移除已全面有效、对所有潜在噪声水印普遍有效。

## 3. 威胁模型与攻击权限

### 3.1 攻击者可以获得

- 同一目标密钥下的少量水印参考图像；
- 公开代理 VAE；
- 与水印图像不配对的公开干净图像；
- 待伪造的干净目标图像，或待移除的带水印目标图像。

### 3.2 攻击者不能获得

- 目标生成模型参数；
- 目标水印检测器、检测分数、阈值反馈和密钥；
- 参考水印图像对应的配对干净原图；
- 攻击过程中的任何在线成功/失败反馈。

### 3.3 严格零查询要求

- 攻击进程只允许加载执行攻击所需的代理 VAE；不得导入、初始化或调用目标检测器。
- 正式实验固定运行至预算选择实验后冻结的 $T_{\mathrm{formal}}$，不得依据检测结果早停、调参或选择中间图像。当前 1500 仅为预算选择实验的候选上限，不是已经冻结的正式预算。
- 检测和质量评价由独立离线进程在全部攻击完成后执行。
- 参考图像不得按检测结果筛选、替换或重生成。原始参考图的真实检测率应作为实验控制报告。
- “首次达到成功的步数”只允许在预算选择实验中计算。正式实验的ASR、质量、成本和输出选择只使用$T_{\mathrm{formal}}$最终输出；第10.2节的p值/bit accuracy轨迹仅作离线诊断，不能用于早停、选择输出或替代最终主结果。

## 4. 数据、模型和实验单元

### 4.1 数据集与图像规格

- 参考图提示词：`Gustavosta/Stable-Diffusion-Prompts`，按预先生成的 manifest 固定顺序使用。
- 伪造目标：MS-COCO 2017 validation 中 200 张互不重复图像。
- 非配对干净先验：MS-COCO 2017 train 中 5000 张互不重复图像，按密钥切分为互不重叠的 25 张一组。
- 伪造目标与干净先验集合不得重叠。
- 所有图像统一为 $512\times512$ RGB；预处理、颜色空间、插值和像素范围必须写入 resolved config。

### 4.2 密钥、参考图与嵌套抽样

- 密钥数：$K=200$，统一编号 `key_000` 至 `key_199`。
- 每个密钥预生成 25 张水印参考图，顺序在实验前固定。
- 参考集合严格嵌套：
  \[
  R_1\subset R_5\subset R_{25}.
  \]
- $R_1$ 使用索引 0；$R_5$ 使用索引 0–4；$R_{25}$ 使用索引 0–24。
- 每个密钥的干净先验同样按前 1、5、25 张形成嵌套集合 $C_1\subset C_5\subset C_{25}$。
- 每个 key 在所有方法、$\lambda$、$N$、$\beta$、水印和模型设置中共享相同提示词、参考顺序、目标图像、干净先验和随机种子。
- 实验复现主种子 `master_seed` 固定为 `205`。该数值由实验设计者在运行前写入协议和配置，不由模型、数据集或 GPU 自动提供。
- 所有子种子通过 SHA-256 稳定派生：对 UTF-8 字符串 `formal_protocol_v1.8|205|<namespace>|<identifiers>` 计算 SHA-256，取前 8 字节按无符号大端整数解释，再对 $2^{63}-1$ 取模。禁止使用 Python `hash()`、当前时间、进程号或未记录的系统随机源。
- 命名空间固定为：
  - `generation`：扩散初始高斯噪声，标识符为 `key_id|reference_index`，不包含 watermark/model，使相同参考位置在不同水印与模型间共享生成 seed；
  - `watermark_key`：水印模式、密钥或 bit message，标识符为 `watermark|key_id`；
  - `data_order`：COCO 和提示词清单的确定性抽样；
  - `transform`：裁剪、随机噪声和常规变换，标识符为 `condition_id|key_id`；
  - `budget_pilot`：P0 专用的 key、目标、参考和攻击随机流，标识符包含 `task|watermark|model_setting|pilot_key_id`，不得与正式 key 复用；
  - `worker`：并行 worker 的局部 RNG 流，不得改变样本级结果。
- 派生出的实际整数 seed 必须写入 manifest；程序同时设置 Python `random`、NumPy、PyTorch CPU、PyTorch CUDA 和显式 `torch.Generator`。生成噪声 seed 与水印 key seed 必须相互独立。
- 断点续跑时必须恢复当前实验单元保存的 Python/NumPy/PyTorch CPU/CUDA RNG 状态，不能仅重新调用全局 `manual_seed` 后假定结果相同。
- 各水印系统的实际密钥对象、bit message 或 seed 必须由 `key_manifest.json` 明确映射，不依赖目录顺序推断。

### 4.3 移除目标与参考关系

- 每个密钥的移除目标固定为 $R_N$ 中的第一张水印参考图，即索引 0；该图同时参与 $N$ 张水印 latent 的聚合。
- 配置必须显式记录 `removal_target_reference_index=0` 和 `target_in_reference_aggregate=true`。
- 论文和结果摘要必须披露该设置；不得把它描述为 target-excluded 协议。
- 非配对干净先验与目标、参考图无语义配对关系，不得针对目标人工选择。

### 4.4 模型设置

攻击代理编码器始终固定为SD v1.4 VAE；`Model`表示生成带水印图像并执行检测的目标模型。

| 适用阶段 | 设置 | 目标生成/检测模型 | 攻击代理编码器 | 含义 |
|---|---|---|---|---|
| P0预算选择 | 仅跨模型 | Stable Diffusion v2-base | SD v1.4 VAE | 用于在主要黑盒迁移条件下选择正式预算 |
| 正式E0–E7 | 同模型 | Stable Diffusion v1.4 | SD v1.4 VAE | 代理与目标模型家族一致，但攻击过程仍不访问检测器 |
| 正式E0–E7 | 跨模型 | Stable Diffusion v2-base | SD v1.4 VAE | 公开代理VAE与目标模型不同，不访问目标模型参数或攻击过程检测器反馈 |

- SD v2-base 锁定 revision：`f5bc1bd97485577aa0b946fa8a9004e2ec147402`。
- SD v1.4 锁定 revision：`133a221b8aa7292a167afc5127cb63fb5005638b`。
- 目标水印：Tree-Ring、RingID、Gaussian Shading。
- P0 的 `model_setting` 固定为 `cross_model_sd2_target_sd14_vae_proxy`。
- 正式E0–E7包含 `same_model_sd14_target_sd14_vae_proxy` 和 `cross_model_sd2_target_sd14_vae_proxy`；P0结果不得并入正式跨模型结果。
- 正式运行前必须分别锁定三种水印的代码 commit、检测参数、生成参数和密钥格式。

## 5. 方法定义与固定优化设置

### 5.1 本文伪造方法

\[
\bar z_w^{(N)}=\frac1N\sum_{i=1}^{N}E_\phi(x_i^w),
\]
\[
\min_\delta\;\operatorname{MSE}\!\left(E_\phi(x^c+\delta),\bar z_w^{(N)}\right)
+\lambda\operatorname{MSE}(x^c+\delta,x^c).
\]

latent 聚合必须先转换为 FP32，再做直接算术平均；不使用加权、异常剔除、稳健筛选或两阶段优化。

### 5.2 本文移除方法

\[
\bar z_w^{(N)}=\frac1N\sum_{i=1}^{N}E_\phi(x_i^w),\qquad
\bar z_c^{(N)}=\frac1N\sum_{i=1}^{N}E_\phi(x_i^c),
\]
\[
\hat r_w=\bar z_w^{(N)}-\bar z_c^{(N)},\qquad
z_{\mathrm{rm}}=E_\phi(x_t^w)-\beta\hat r_w,
\]
\[
\min_\delta\;\operatorname{MSE}\!\left(E_\phi(x_t^w+\delta),z_{\mathrm{rm}}\right)
+\lambda\operatorname{MSE}(x_t^w+\delta,x_t^w).
\]

第一版只保留 latent MSE 与像素 MSE，不把 LPIPS 加入优化目标，也不进行二阶段优化。

### 5.3 Jain 基线

- 伪造：使用一张同密钥参考图的 latent 作为优化目标，即 $E_\phi(x_1^w)$。
- 移除：将目标水印图像的全局像素均值扩展为常量图像 $\mu_{x_t^w}$，以 $E_\phi(\mu_{x_t^w})$ 作为优化目标。
- Jain 是单图方法，参考数固定为 1，不因 $N$ 敏感性实验重复改变其定义。
- 与本文方法共享梯度更新、$\lambda$、$T$、输入样本、随机种子、设备和数值精度。

### 5.4 Can Simple Averaging 基线

在 RGB 像素域计算：

\[
\hat\delta_w^{(N)}=\frac1N\sum_i x_i^w-\frac1N\sum_i x_i^c.
\]

- 伪造：$\hat x^w=\operatorname{clip}(x^c+\hat\delta_w^{(N)},0,1)$。
- 移除：$\hat x^c=\operatorname{clip}(x_t^w-\hat\delta_w^{(N)},0,1)$。
- 放大系数固定为 $\gamma=1$，不利用检测器搜索最佳强度。
- 该方法是一次性像素运算，不虚构 $\lambda$、迭代步数或中间检查点；单独报告其参考聚合与运算时间。

### 5.5 优化与数值设置

- 正式主预算：$T_{\mathrm{formal}}$ 次梯度更新，由第 6.1 节预算选择实验确定并在正式实验开始前通过新协议版本冻结；候选初始上限为 1500。
- 更新规则：与当前 Jain 复现一致的无动量像素梯度下降。
- 学习率：$\alpha=0.02$。
- 主设置：$\lambda=1\times10^4$、$N=5$、移除 $\beta=1.0$。
- $\lambda$ 网格：$\{1\times10^4,2\times10^4,5\times10^4\}$。
- $N$ 网格：$\{1,5,25\}$。
- $\beta$ 网格：$\{0.5,1.0,2.0\}$。
- 每一步输出裁剪到固定模型输入范围；实际实现使用 element-wise mean reduction 的 MSE，不能在 sum/mean reduction 间切换后仍沿用同一 $\lambda$。
- 所有方法必须使用相同的 VAE 编码定义（posterior mode、scaling factor、dtype 和归一化）。

## 6. 正式实验组与规模

所有正式单因素实验均覆盖200个密钥、三个水印、同模型和跨模型两个设置。除被研究因素外，其余参数保持主设置。重复条件只运行一次并由统一结果索引复用。P0是唯一只运行跨模型的预算选择实验。

### P0：正式实验前的迭代预算选择实验

**目的**：观察本文方法在候选上限 1500 步内每 100 步的累计攻击成功率，用独立开发数据决定正式固定预算 $T_{\mathrm{formal}}$。P0 是允许检测器反馈的协议设计实验，不是正式黑盒攻击实验。

- 方法：只运行本文多参考潜空间聚合的伪造方法和移除方法；不在 P0 中比较 Jain 或 Can。
- 参数：$N=5$、$\lambda=10^4$、移除$\beta=1.0$、候选最大步数$T_{\max}=1500$；模型固定为正式实验的跨模型分支（SD2-base目标/SD1.4 VAE代理），其余生成、预处理和优化设置与正式主设置一致。
- 覆盖：三种水印、仅跨模型设置、伪造与移除两个任务。使用同一组100个逻辑pilot key，编号 `pilot_key_000` 至 `pilot_key_099`；每种水印由manifest映射为各自的真实密钥对象。在线早停阶段共计 $3\times2\times100=600$ 个攻击单元，不运行P0同模型版本。
- 数据隔离：P0 的 100 个 pilot key、目标图像和参考清单不得与正式 200-key 测试集重叠。使用 `master_seed=205`，但子种子额外加入 `budget_pilot` 命名空间，避免与正式样本冲突。
- 在线检测：在 100, 200, …, 1500 步调用目标检测器。样本第一次成功后记录 `first_success_step` 并立即早停；尚未成功的样本继续至下一检查点或 1500 步。
- 成功定义与正式实验一致；ASR 分母仍为攻击前满足资格条件的样本，必须同时报告 `eligible_n/100`。
- 第 $t$ 步累计 ASR 定义为：`first_success_step <= t` 的资格样本数除以资格样本总数。已经早停的成功样本在后续步数继续计为成功，因此可得到 100–1500 步的完整累计 ASR 曲线。
- 该累计曲线回答“在线检测并早停时，截至某步有多少样本曾成功”，不等于“所有样本持续优化到该步时的固定预算 ASR”；成功后继续优化可能重新跌出阈值，因此不能只凭累计曲线直接声明某个固定预算的ASR。
- 每个任务、水印和模型设置输出 `pilot_asr_by_step.csv`，字段至少包括 `step`、`eligible_n`、`new_success_n`、`cumulative_success_n`、`cumulative_asr` 和 Wilson 95% CI；另保存 `pilot_first_success.csv` 和伪造/移除分开的 `pilot_asr_curve.png`。
- P0 仅报告 ASR、资格样本数、首次成功步数和实际攻击时间；不承担正式图像质量、FID、错误密钥或方法优越性结论。由于存在在线检测和早停，其时间不得与正式固定预算成本直接比较。

**预算冻结门槛**：

1. 本版本不预先把“理想 ASR”写成任意阈值，也不自动选择步数；P0 在线早停曲线完成后，由用户查看全部设置并提出一个全局候选预算 $T_{\mathrm{candidate}}$。
2. 若 1500 步累计 ASR 仍不理想，正式实验不得启动；先提高候选上限，在相同 P0 样本上从保存状态继续并补充新的 100 步检查点。
3. 若 1500 步前已经达到用户认可的效果，可提出更小的、100 的整数倍作为 $T_{\mathrm{candidate}}$。
4. 冻结前必须在相同100个pilot key、三种水印和跨模型设置上执行一次固定预算确认，共600个单元：从头运行至 $T_{\mathrm{candidate}}$，攻击过程中不调用检测器、不早停，只在结束后离线计算ASR，输出 `pilot_fixed_budget_confirmation.csv`。这一步用于检验在线累计ASR是否高估固定预算效果；不增加同模型确认。
5. 如果固定预算确认结果不理想，返回步骤 1–4 重新选择或扩展预算；如果确认可接受，才将 $T_{\mathrm{candidate}}$ 冻结为 $T_{\mathrm{formal}}$。
6. 选定预算必须对 Jain、本文方法以及所有正式水印、模型设置和任务统一适用，不得为不同方法挑选各自最有利的步数。Can 是非迭代方法，不受该预算影响。
7. 预算、选择依据、完整 P0 曲线和固定预算确认结果必须写入新的协议版本后才能开始正式 200-key 实验；P0 的 100-key 结果不得并入正式主表、显著性检验或正式 ASR。

### E0：原始检测与数据有效性控制

对每种水印和模型设置报告：

- 200 张原始水印目标的目标密钥真阳性率；
- 200 张原始 COCO cover 的目标密钥假阳性率；
- Tree-Ring/RingID 的连续检测分数、ROC-AUC 和 TPR@1% FPR；
- Gaussian Shading 的 bit accuracy、官方阈值下的接受率和干净图观察假阳性率；
- 不用 200 张干净图重新“估计” $10^{-6}$ FPR 阈值。论文必须说明该阈值来自原方法，200 张控制图只能报告观察结果，不能证明 $10^{-6}$ FPR。

### E1：伪造主实验

- 方法：Jain、Can Simple Averaging、本文方法。
- 本文与 Can 使用 $N=5$；Jain 使用其原始单参考定义。
- Jain 与本文使用 $\lambda=10^4$、共同的 $T_{\mathrm{formal}}$；Can 使用 $\gamma=1$。
- 规模：3水印 × 2模型设置 × 200 keys × 3方法 = 3600个最终输出。

### E2：移除主实验

- 方法和主参数同 E1；本文方法使用 $\beta=1$。
- 规模：3水印 × 2模型设置 × 200 keys × 3方法 = 3600个最终输出。

### E3：λ 单因素实验

- 方法：Jain、本文方法；Can 不包含 $\lambda$。
- $\lambda\in\{10^4,2\times10^4,5\times10^4\}$，本文固定 $N=5$，移除固定 $\beta=1$。
- 同时覆盖伪造和移除、三个水印、同模型与跨模型、全部200 keys。
- 条件总数：14400；其中主设置条件复用E1/E2，不重复运行。

### E4：参考数 $N$ 单因素实验

- 方法：本文方法、Can Simple Averaging；Jain 作为固定单参考水平线，不为 $N=5,25$ 构造非原始变体。
- $N\in\{1,5,25\}$，本文固定 $\lambda=10^4$，移除固定 $\beta=1$；Can 固定 $\gamma=1$。
- 同时覆盖伪造和移除、三个水印、同模型与跨模型、全部200 keys。
- 条件总数：14400；$N=5$主设置复用E1/E2。

### E5：移除强度 β 单因素实验

- 仅本文移除方法。
- $\beta\in\{0.5,1.0,2.0\}$，固定 $N=5$、$\lambda=10^4$。
- 覆盖三个水印、同模型与跨模型、全部200 keys。
- 条件总数：3600；$\beta=1$条件复用E2。

### E6：常规外部移除基线

- 在同模型和跨模型两个正式设置运行，覆盖三个水印和全部200 keys。
- 每类只用一个预注册强度，不进行检测器驱动的强度搜索：
  - JPEG：quality=25；
  - 随机裁剪：保留 75% 面积后双三次插值回 $512\times512$，裁剪位置由样本 seed 固定；
  - 缩放：先缩至 $384\times384$，再双三次插值回 $512\times512$；
  - Gaussian blur：PIL 等价 radius=8.0；
  - Gaussian noise：在 $[0,1]$ 像素域加入 $\sigma=0.1$ 的独立高斯噪声后裁剪。
- 规模：3水印 × 2模型设置 × 200 keys × 5变换 = 6000个最终输出。
- 这些是补充基线，不能替代 Jain 和 Can 的主要比较。

### E7：逐图匹配扰动随机噪声控制

- 对 E1–E5 每一个唯一最终攻击输出，生成一个独立高斯噪声控制。
- 将噪声缩放到与对应攻击图像相同的预裁剪 $l_2$ 扰动，再裁剪到合法像素范围；同时记录裁剪后的真实 $l_2$ 与 $l_\infty$。
- 使用第 4.2 节 `transform` 命名空间派生的固定 seed。
- 报告检测率和全部质量指标，用于区分“结构化攻击方向”与“同等扰动量随机噪声”的效果。
- 不把随机噪声控制计入攻击方法 ASR 排名。

### 6.2 去重后的正式实验规模

- 主实验：7200个唯一输出。
- λ网格新增：9600个唯一输出。
- $N$网格新增：9600个唯一输出。
- β网格新增：2400个唯一输出。
- 常规变换：6000个唯一输出。
- 总计：34800个唯一攻击/变换输出，其中21600个为固定 $T_{\mathrm{formal}}$ 的迭代攻击。
- 不再为全部 200 keys 永久保存最终图或中间检查点图像。每个实验条件只永久保留 `key_000`、`key_100`、`key_199` 的最终图；迭代方法对这 3 个 key 每 150 步保存 PNG，并额外确保保存 $T_{\mathrm{formal}}$ 最终 PNG。
- 其余 197 个 key 的最终图只在独立评价完成前进入临时 `evaluation_spool/`；检测、质量和 FID 特征写入持久的最终指标文件并通过哈希/行数校验后，临时图按协议清除。
- 全部200 keys永久保存$T_{\mathrm{formal}}$最终评价指标和最终输出哈希；不永久保存每50步数值日志。唯一的全key逐步数据是第10.2节五组图所需、每100步离线计算的目标key p值或目标消息bit accuracy；不生成逐步ASR、质量或FID指标，因此最终统计样本量和主表规模不变。

## 7. 检测成功定义与评价指标

### 7.1 资格样本与 ASR

- Tree-Ring/RingID 接受规则：`p_value <= 0.05`。
- Tree-Ring/RingID 伪造成功：原始 cover 对目标密钥不接受，最终攻击图对目标密钥接受。
- Tree-Ring/RingID 移除成功：原始水印目标对目标密钥接受，最终攻击图对目标密钥不接受；为与当前代码边界一致，移除成功使用 `p_value >= 0.05`，并单独报告恰等于阈值的样本。
- Gaussian Shading：使用原实现按 FPR=$10^{-6}$ 定义的 bit-accuracy 阈值；伪造和移除分别按阈值跨越方向判断。
- 主 ASR 分母是攻击前满足资格条件的样本；同时报告 `eligible_n / 200` 和全部 200 样本的最终目标接受/拒绝率，防止条件化分母掩盖原始检测失败。
- 所有方法在同一 `(watermark, model_setting)` 下必须使用资格集合交集进行成对显著性比较。

### 7.2 逐图指标

每张原始图和 $T_{\mathrm{formal}}$ 最终图至少记录：

- 目标密钥检测分数、接受状态和成功指示量；
- 其余 199 个错误密钥/消息的检测结果；
- `any_wrong_key_accept`、错误密钥接受数量、目标密钥排名和 top-1 身份；
- Gaussian Shading 的 bit accuracy；
- $l_2$、$l_\infty$、RMSE、LPIPS、SSIM、PSNR；
- 真实扰动大小必须在裁剪后的最终像素上重算。

质量指标统一相对于被攻击输入计算：伪造相对于原始 COCO cover，移除相对于原始水印目标。实现固定为：LPIPS-Alex、SSIM/PSNR 的 data range=1、RGB float32；具体库版本必须进入 manifest。

### 7.3 集合级指标

- ASR、原始 TPR/FPR、最终接受率；
- Tree-Ring/RingID 的 ROC-AUC 与 TPR@1% FPR；
- 质量指标均值、标准差、中位数和 95% 置信区间；
- FID：每个完整 200 图条件在“原始输入集合—攻击输出集合”之间计算一次。FID 不是逐图指标，不报告伪造的单图 FID；$n=200$ 的 FID 仅作描述性质量证据，不承担唯一主结论。
- 错误密钥身份漂移：任意错误密钥接受图像率、每图错误接受数、目标 key top-1 率。

#### 7.3.1 $l_2$、$l_\infty$ 与 FID 的报告目的

- $l_2$ 衡量整张图像所有像素改动的总体能量，用于判断攻击是否依赖大量累积扰动，并与 Jain 原论文的扰动规模直接对齐。它会随分辨率和通道数变化，因此只能在统一 $512\times512$ RGB 与统一像素范围下比较。
- $l_\infty$ 衡量任一像素通道上的最大绝对改动，用于暴露局部极端修改、裁剪饱和或少量特别明显的像素异常。它不能替代感知指标，但能补充 $l_2$ 对最坏局部扰动不敏感的问题。
- FID 衡量一组攻击图像与对应原始图像在 Inception 特征分布上的整体偏移，用于检查攻击是否造成系统性的分布级质量变化。它不能说明某一张图是否自然，也不是逐图指标。
- 三者均不是攻击成功指标。论文必须把它们与 LPIPS、SSIM、PSNR、定性图和 ASR 联合解释，不能单凭某一个数值宣称图像质量更好。
- FID 固定使用同一实现、同一 Inception-v3 pool3 2048 维特征和同一预处理；库名、版本和特征缓存哈希写入 manifest。由于每组只有 200 张图，FID 只作描述性辅助证据。

### 7.4 成本指标

必须拆分并记录：

- `reference_compute_time`：参考编码、均值/差分构造；
- `optimization_compute_time`：前向、反向和像素更新，CUDA 计时前后同步；
- `attack_compute_time = reference_compute_time + optimization_compute_time`；
- `checkpoint_io_time`；
- `offline_evaluation_time`；
- `total_wall_clock_time`；
- 峰值 GPU 显存、代理 VAE 调用次数、实际完成迭代数。

正文成本主表报告 `attack_compute_time`，复现材料同时提供总墙钟、I/O 与离线评价时间。Can 和常规变换按其真实一次性计算过程计时，不与 $T_{\mathrm{formal}}$ 步优化混为一谈。

## 8. 运行状态、可视化检查点与最终评价

- 步骤 0 只在 manifest 中记录输入、配置和哈希，不保存攻击指标或检测结果。
- 每 50 步原子覆盖一次临时 `resume_state`，仅用于中断续跑；它不是永久攻击日志，不进入论文分析，实验单元完成并校验后即可按契约清除。
- 仅为 3 个预注册可视化 key（`key_000`、`key_100`、`key_199`）永久保存最终图；迭代方法每 150 步保存无损 PNG，并额外保存 $T_{\mathrm{formal}}$ 最终 PNG。若最终步已是 150 的整数倍，不重复保存副本。
- 每150步永久PNG只用于观察优化过程和制作定性图，不据此早停或选择输出。
- 为生成第10.2节规定的五组检测统计量曲线，仅对Proposed的E3–E5相关条件，将全部200 keys在步骤0、100、200、…、$T_{\mathrm{formal}}$的图像临时写入 `curve_checkpoint_spool/`；若$T_{\mathrm{formal}}$不是100的整数倍，额外写入最终步。攻击进程不得加载或调用检测器。
- 一个条件的攻击全部完成后，由物理分离的离线评价进程读取临时检查点：Tree-Ring和RingID计算目标key p值，Gaussian Shading计算目标消息bit accuracy。评价结果写入 `detector_trajectory_per_key.csv` 和 `detector_trajectory_summary.csv`，不得反向影响攻击、早停、预算或输出选择。
- 曲线数据和哈希校验完成后，除`key_000`、`key_100`、`key_199`已按可视化规则永久保留的PNG外，`curve_checkpoint_spool/`中的其他中间图像自动清除并写入ledger。清理前必须验证200-key × 预期步数的评价行数完整。
- 其余197个key的$T_{\mathrm{formal}}$输出先原子写入`evaluation_spool/`。独立评价器对最终图计算目标/错误密钥检测、$l_2$、$l_\infty$、LPIPS、SSIM、PSNR和FID特征；最终指标与哈希校验完成后，临时图可按协议清除并记录清除事件。
- 全部200 keys永久保留`final_per_key_metrics.csv`和`final_condition_summary.csv`；E3–E5 Proposed条件额外永久保留上述两份检测统计量轨迹CSV。除这些指定轨迹外，不生成逐检查点质量指标、FID或ASR趋势。
- 最终总结、统计检验和论文表图全部基于 $T_{\mathrm{formal}}$ 输出；不得按 key 选择“最佳检查点”。
- Can、常规变换等非迭代方法同样只评价最终输出，并只永久保存上述 3 个 key 的图像。

## 9. 统计分析计划

- ASR 和各比例报告 Wilson 95% 置信区间及有效分母。
- 方法间 ASR 使用成对 McNemar 检验，并报告配对成功率差及 95% bootstrap 置信区间。
- $l_2$、$l_\infty$、LPIPS、SSIM、PSNR 和时间采用同 key 配对比较；主检验为双侧 Wilcoxon signed-rank，并同时报告中位配对差和 bootstrap 95% CI。
- 同一实验族内的多重比较使用 Holm 校正；实验族分别定义为主伪造、主移除、$\lambda$、$N$、$\beta$ 和常规变换。
- FID 只报告组级点估计，不对其使用逐图显著性检验。
- 主论文结论以 E1/E2 预注册主设置为依据；E3–E7 仅用于敏感性、解释和控制，不能观察后替换主设置。
- 先报告原始样本量、失败/缺失数和未经挑选的结果，再报告显著性；不得只展示成功样本或最好水印/模型。

## 10. 最终必须生成的表格与图像

本节规定论文最终必须生成的表图。第10.1节表格、最终ASR、质量和成本结果均来自$T_{\mathrm{formal}}$最终输出；第10.2节另行规定五组离线检测统计量轨迹。P0预算选择曲线单独保存，不属于正式200-key正文主结果。

### 10.1 四类实验结果表

所有结果表参考用户提供图片的组织方式：`Watermark`使用跨行分组，同一水印内先列 `Model=SDv1.4`，再列 `Model=SDv2.0`，随后展开该表唯一变化的因素。图片中的实验数字只作为版式示例，不复制到本项目。

`Model`列表示目标生成/检测模型：`SDv1.4`对应同模型，`SDv2.0`对应跨模型；攻击代理在两种设置中始终是SD1.4 VAE。每张表按伪造和移除分别生成，除表中显示的变量外，其余参数在表题或表注中写明并固定。

1. **不同 $\lambda$ 实验表（E3）**

   | Watermark | Model | $\lambda$ | ASR↑ | $l_2$↓ | $l_\infty$↓ | LPIPS↓ | SSIM↑ | PSNR↑ | FID↓ | Time↓ |
   |---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

   对Jain与Proposed、伪造与移除分别出表或分面，表题写明固定的 `Method`、$N$ 和移除 $\beta$；不在表内增加Method或N列。每个Watermark/Model块内按 $5\times10^4$、$2\times10^4$、$1\times10^4$ 排列。

2. **不同 $N$ 实验表（E4）**

   | Watermark | Model | $N$ | ASR↑ | $l_2$↓ | $l_\infty$↓ | LPIPS↓ | SSIM↑ | PSNR↑ | FID↓ | Time↓ |
   |---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

   对Proposed与Simple Averaging、伪造与移除分别出表或分面，表题写明固定的 `Method`、$\lambda$、$\beta$或$\gamma$；不在表内增加Method或$\lambda$列。$N$按1、5、25排列。

3. **不同攻击方法实验表（E1/E2主表）**

   | Watermark | Model | Method | ASR↑ | $l_2$↓ | $l_\infty$↓ | LPIPS↓ | SSIM↑ | PSNR↑ | FID↓ | Time↓ |
   |---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|

   伪造和移除各一张，Method按Jain、Simple Averaging、Proposed排列。表题或表注明确：Jain按原始单图定义，Simple Averaging与Proposed主设置使用$N=5$；各自不适用的参数不放入主表。

4. **不同 $\beta$ 实验表（E5，仅移除）**

   | Watermark | Model | $\beta$ | ASR↑ | $l_2$↓ | $l_\infty$↓ | LPIPS↓ | SSIM↑ | PSNR↑ | FID↓ | Time↓ |
   |---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|

   只报告Proposed移除方法，固定$N=5$和$\lambda=10^4$，$\beta$按0.5、1.0、2.0排列。

所有表的ASR单元格同时给出 `ASR% (success/eligible)`；95% CI可放表注或独立统计附表。FID为每个Watermark/Model/条件的200图集合级结果，不能逐图平均。错误密钥接受率、目标key top-1、完整CI和统计检验放独立诊断附表，不改变用户指定的上述列结构。

另生成一张不采用上述指标模板的**成本与权限表**，比较参考图数量、代理VAE需求、优化步数、VAE调用次数、攻击时间、显存和是否需要在线检测器。

### 10.2 五组检测统计量—迭代步数线型图（必须生成）

本节“两类主攻击”指Proposed伪造与Proposed移除。五组图均使用步骤0、100、200、…、$T_{\mathrm{formal}}$的离线检测结果；横轴为迭代步数。每张图采用2行 × 3列布局：行分别为`Model=SDv1.4`同模型和`Model=SDv2.0`跨模型，列分别为Tree-Ring、RingID、Gaussian Shading。每个面板恰好三根超参数曲线，不把模型或水印再编码成额外曲线。

- Tree-Ring和RingID纵轴为目标key p值。主线绘制200个key的中位数，阴影为四分位区间；使用0–1原始p值坐标并绘制$p=0.05$水平阈值线。伪造时p值下降表示更接近接受，移除时p值上升表示更接近拒绝。
- Gaussian Shading纵轴为目标消息bit accuracy。主线绘制200个key的均值，阴影为95% bootstrap CI，并绘制原方法正式检测阈值线。伪造时bit accuracy上升更有利，移除时下降更有利。
- 每个面板的三条线使用固定颜色、线型、图例顺序；同一超参数值在所有图中颜色一致。不得挑选成功key或对曲线平滑后隐藏真实评价点。

必须生成以下五张多面板图：

1. **伪造—不同$\lambda$**：$\lambda\in\{10^4,2\times10^4,5\times10^4\}$三根线，固定$N=5$；文件名`forgery_lambda_detector_trajectory.png`。
2. **伪造—不同$N$**：$N\in\{1,5,25\}$三根线，固定$\lambda=10^4$；文件名`forgery_N_detector_trajectory.png`。
3. **移除—不同$\lambda$**：$\lambda\in\{10^4,2\times10^4,5\times10^4\}$三根线，固定$N=5$、$\beta=1$；文件名`removal_lambda_detector_trajectory.png`。
4. **移除—不同$N$**：$N\in\{1,5,25\}$三根线，固定$\lambda=10^4$、$\beta=1$；文件名`removal_N_detector_trajectory.png`。
5. **移除—不同$\beta$**：$\beta\in\{0.5,1.0,2.0\}$三根线，固定$N=5$、$\lambda=10^4$；文件名`removal_beta_detector_trajectory.png`。

相应永久数据文件为上述每张图各自的逐key长表和按步数汇总表；最少字段包括`task`、`watermark`、`model`、`factor_name`、`factor_value`、`key_id`、`step`、`p_value`或`bit_accuracy`、接受状态和资格状态。

### 10.3 其他正文与附录图像

- 最终ASR方法对比图；
- ASR—LPIPS质量权衡图；
- 同模型—跨模型最终结果对比图；
- 使用`key_000`、`key_100`、`key_199`的定性样例和统一色标绝对差分图；
- P0每100步在线早停累计ASR曲线和候选固定预算确认结果；
- 最终检测分数分布、Gaussian Shading bit accuracy分布、五种常规外部移除变换、失败样例和错误身份漂移案例；
- 完整均值、标准差、置信区间、FID和统计检验附表。

正式200-key实验不生成逐步ASR、LPIPS、SSIM、PSNR或FID曲线；只生成本节明确要求的p值/bit accuracy轨迹。P0累计ASR曲线仍单独保存，不能与正式轨迹混合。

### 10.4 样例选择规则

- 主定性图、永久最终图和永久中间 PNG 固定使用 `key_000`、`key_100`、`key_199`，不得按结果挑选。
- 失败案例附录按 key 编号升序展示前若干个，并报告全部失败 key 列表。
- 差分图使用相同动态范围、色表和放大倍数；不得分别自动拉伸造成视觉误导。
- 第10.2节五组轨迹图使用全部200 keys的预注册汇总规则，不按样例key筛选；三条超参数线必须来自同一key集合、相同step网格和相同随机种子协议。
- 正式200-key实验不生成ASR—迭代步数、质量—迭代步数、FID—迭代步数或“首次成功步数”图。正式实验唯一逐步例外是第10.2节五组p值/bit accuracy轨迹；P0则单独生成预算选择所需的每100步累计ASR曲线和首次成功步数数据。

## 11. 必须保留的数据与目录契约

每个 run 使用独立且不可覆盖的目录：

```text
实验结果/<experiment_id>/<run_id>/
  protocol_snapshot/
    正式实验设置.md
    config_resolved.yaml
    source_config.yaml
  manifests/
    run_manifest.json
    key_manifest.json
    sample_manifest.csv
    reference_manifest.csv
    clean_prior_manifest.csv
  logs/
    command.txt
    environment.txt
    run_status.log
    stderr.log
    stdout.log
  checkpoints_visualization_keys/
  resume_state/
  final_images_visualization_keys/
  evaluation_spool/
  curve_checkpoint_spool/
  evaluation/
    final_per_key_metrics.csv
    final_condition_summary.csv
    final_statistical_tests.csv
    detector_trajectory_per_key.csv
    detector_trajectory_summary.csv
  figures/
  checksums.sha256
  <run_id>_实验总结.md
```

P0 单独保存在 `实验结果/budget_selection_pilot/<run_id>/`，至少包含协议/配置快照、100-key pilot manifest、`pilot_first_success.csv`、按任务/水印/模型设置分组的 `pilot_asr_by_step.csv`、伪造与移除 ASR 曲线、`pilot_fixed_budget_confirmation.csv`、时间记录、校验和及一份预算选择总结。P0 文件不得复制进正式 run 或与正式 200-key 指标合并。

### 11.1 永久保留

- 本次协议快照、resolved config、完整 Git SHA、分支、dirty 状态；
- 模型 ID、revision、实际缓存路径、水印代码 commit 和依赖版本；
- 全部 manifest、命令、环境、必要运行状态、退出码和分项时间；
- 3 个预注册可视化 key 在全部实验条件中的最终攻击图、常规变换图和匹配噪声控制图；
- 3 个预注册可视化 key 在迭代条件中的每 150 步 PNG 和 $T_{\mathrm{formal}}$ 最终 PNG；其他 key 不永久保存最终图或中间图；
- 全部 200 keys 的 $T_{\mathrm{formal}}$ 最终评价指标、最终输出 SHA-256 和最终完成状态；
- 每个实验单元一行的 `final_per_key_metrics.csv`、条件级 `final_condition_summary.csv` 和必要的最终统计检验表；
- 第10.2节五组曲线对应的逐key轨迹CSV、按步数汇总CSV和最终PNG/PDF图；
- 第 10 节规定的论文最终表图，以及每个 run 唯一的一份 `<run_id>_实验总结.md`；
- SHA-256 校验文件和结果包 contents 清单。
- P0 的完整每 100 步累计 ASR 数据、首次成功步数、曲线、样本清单和最终预算选择依据；即使正式预算后来改变，也不得覆盖原 P0 记录。

### 11.2 不重复打包

- 不复制或提交模型权重、COCO/提示词原始数据集；只保存稳定路径、上游标识、许可证信息、样本 ID 和文件哈希。
- 密钥张量、秘密 bit message 和大规模参考资产保留在受控实验存储中，不提交 Git；可复现 seed 与 manifest 是否公开由论文发布阶段另行决定。
- `resume_state/` 只保存每个活动 worker 当前实验单元的最新可恢复状态，采用覆盖式原子更新；实验单元完成并且最终图、日志和 manifest 均提交成功后可按程序契约清除该临时状态，清除动作写入日志。
- 3个预注册key的论文插图检查点、最终图、最终指标和最终总结不得作为临时文件清理。`evaluation_spool/`中的其他197个key最终输出按原规则清除；`curve_checkpoint_spool/`中的其他中间图像在轨迹CSV行数、哈希和五组图全部通过校验后自动清除并记录。除这两个明确spool外，其他临时缓存的批量清理仍须先生成精确清单并获得用户授权。

### 11.3 最低逐行字段

最终逐 key 指标表每行至少可追溯到：`protocol_version`、`run_id`、`condition_id`、`watermark`、`model_setting`、`task`、`method`、`key_id`、`target_id`、`reference_ids`、`clean_ids`、`N`、`lambda`、`beta`、`gamma`、`seed`、`final_step=T_formal`、最终扰动、最终检测分数、目标/错误密钥结果、最终质量指标和分项时间。中间损失和中间指标不进入该表。

## 12. 执行顺序与验收门槛

1. 冻结本版本协议、P0 pilot 样本和 key manifest，计算哈希，并验证它们与正式 200-key manifest 不重叠。
2. 实现三个水印在SDv1.4同模型与SDv2.0跨模型两种正式组合下的统一接口；P0只启用跨模型组合。锁定SD1.4、SD2-base、代理VAE revision和检测阈值。
3. 将攻击与离线评价物理拆分，增加禁止检测器调用的测试。
4. 完成全部模型、tokenizer、scheduler、水印代码、LPIPS、Inception/FID 资源和数据清单的离线资产准备与预检。
5. 先对 P0 执行同设置 2-key smoke；通过后由同一工作流直接启动 100-key P0，得到每 100 步累计 ASR。
6. 用户审阅完整 P0 曲线并提出 $T_{\mathrm{candidate}}$；完成同100-key、无早停的固定预算确认后，确认全局 $T_{\mathrm{formal}}$，随后升级协议版本、记录选择依据并冻结预算。该门槛完成前禁止启动任何正式 200-key 实验。
7. 在实际正式 GPU 上完成运行时间基准，生成 ETA 报告并经用户确认后再启动全量任务。
8. 每个正式实验批次先执行一次 2-key smoke gate，验证资产、参数、最终图、断点恢复和最终评价链路；通过后同一工作流直接启动 200-key 正式运行。smoke 结果不进入正式统计。
9. 完成 E0，确认数据清单和原始检测率，不按检测结果更换参考图。
10. 依次运行 E1/E2 主实验、E3 $\lambda$、E4 $N$、E5 $\beta$、E6 常规变换、E7 匹配噪声评价；复用重叠条件。
11. 所有攻击完成后对$T_{\mathrm{formal}}$最终输出运行离线检测和质量评价；对E3–E5 Proposed相关条件额外离线评价每100步临时检查点的p值或bit accuracy，生成第10.2节五组轨迹图后清理临时图像。
12. 每个 run 只生成一次最终总结与哈希校验；失败或不完整 run 同样保留一次状态总结。

### 12.1 每批实验的自动 smoke gate

- “每次实验”定义为一个具有独立 resolved-config 哈希的批次。一个批次可以包含同一实验组内预注册的多种方法或参数条件，但不能跨越不同代码 SHA、资产锁或样本 manifest。
- P0 启动命令先自动生成仅含 `pilot_key_000`、`pilot_key_001` 的 smoke 子配置；通过后直接进入 100-key P0。P0 smoke 保持每 100 步检测和早停，以验证其在线曲线链路。
- 正式批次启动命令先自动生成仅含 `key_000`、`key_001` 的 smoke 子配置。除 `key_count=2`、输出目录和 `run_mode=smoke` 外，模型、方法、$\lambda/N/\beta$、$T=T_{\mathrm{formal}}$、seed 派生、临时恢复频率、离线模式和最终评价代码必须与随后 200-key 配置一致。
- smoke必须实际跑完该批次包含的所有方法/条件，不只调用`--help`或加载模型。普通正式批次smoke生成参数、最终指标和验收报告；E3–E5 Proposed批次smoke必须额外验证“每100步临时检查点→离线p值/bit accuracy→轨迹CSV→线型图→临时图清理”链路。P0 smoke另验证在线检测早停和累计ASR链路。
- smoke 通过条件是：退出码为 0；两个 key 的实验单元均完整；参数和输入哈希匹配；最终图和最终指标文件数量正确；离线最终评价可读；数值无 NaN/Inf；断点状态可恢复；所有预期文件通过 SHA-256。攻击是否成功不是 smoke 的通过条件，禁止因为 smoke ASR 不理想而修改正式参数。
- smoke 失败时立即停止，不启动 200-key 正式实验，并保存失败日志和报告。smoke 通过后，同一编排命令无需增加中间预实验或人工调参，直接启动对应 200-key 大规模实验。
- smoke pass 与 `protocol_version + resolved_config_hash + git_sha + assets_lock_hash + sample_manifest_hash` 绑定。同一批次断点续跑时可复用已通过的 smoke；任一哈希变化都必须重新执行 smoke。
- smoke 输出保存在独立目录 `实验结果/smoke/<condition_id>/<run_id>/`，不得合并进正式 200-key CSV、置信区间、FID 或论文主表。

正式实验的最低验收标准：

- 攻击日志和进程依赖中不存在检测器调用；
- 最终输出固定为 $T_{\mathrm{formal}}$，所有正式迭代攻击实际完成相同预算；
- 方法间样本、密钥、参考顺序、随机种子、更新设置和设备可验证一致；
- 全部key的最终评价指标完整；仅3个可视化key永久保存每150步PNG；E3–E5 Proposed条件的200-key每100步检测统计量轨迹行数完整且只保留CSV/图，不永久保留其他key中间图像；
- 离线最终评价能依赖 manifest、固定输入、代码/资产/环境锁和 seed 独立重算；3 个永久可视化 key 的图像与全部 200 个 key 记录的最终哈希一致；
- 攻击、I/O、离线评价计时分离；
- 在主动中断和进程强制终止测试后，重启同一命令均能从最近持久状态继续，不重复已完成实验单元；
- 拔网或禁用网络后，资产预检、2-key smoke、攻击和最终评价均能完成；
- 预期文件存在、非空且哈希通过；
- 所有最终统计数字能追溯至最终逐key指标表，五组轨迹图能追溯至`detector_trajectory_per_key.csv`和`detector_trajectory_summary.csv`；
- 未通过任一门槛的 run 标记为 `FAILED` 或 `INCOMPLETE`，不得并入正式主表。

## 13. 正式代码重构、离线运行、断点续跑与 ETA 契约

### 13.1 新项目名称与迁移边界

- 在用户确认本协议最终版本后，新建独立代码文件夹 `latent_space_aggregation_attacks/`，作为“潜空间聚合攻击”的正式英文项目名。
- 主要算法来源是现有 `jain_multiref_latent_experiment/` 中已经实现并验证的伪造与移除路径；迁移时重构接口和目录，但不得擅自改变数学目标、损失 reduction、阈值或已锁定协议。
- 旧项目在新项目通过回归测试、2-key smoke 和 Tree-Ring 小规模等价性检查前只读保留；不直接重命名、覆盖或删除旧目录。
- 新项目从零整理正式需要的源码、配置、测试和文档，不批量复制历史输出、临时脚本、旧日志或已废弃实验原型。

### 13.2 强制目录结构

```text
latent_space_aggregation_attacks/
  README.md
  pyproject.toml
  requirements.lock
  configs/
    budget_pilot/
    formal/
    smoke/
  src/latent_space_aggregation_attacks/
    core/                 # 配置、seed、manifest、原子写入、resume、计时
    data/                 # prompt、COCO、参考与 clean-prior 清单
    models/               # 目标模型和公开代理 VAE 的离线加载
    watermarks/           # tree_ring、ringid、gaussian_shading
    methods/
      proposed/           # latent 聚合、本文伪造、本文移除
      baselines/          # Jain、Simple Averaging、五种常规变换
    evaluation/           # 最终评价、统计与 FID
    plotting/             # 论文表格和图像
  scripts/
    main_methods/
      run_forgery.py
      run_removal.py
      run_budget_selection_pilot.py
    baselines/
      run_jain_forgery.py
      run_jain_removal.py
      run_simple_averaging.py
      run_distortion_removal.py
    evaluation/
      evaluate_final.py
      evaluate_detector_trajectories.py
      build_tables_and_figures.py
    operations/
      run_formal_batch.py
      prepare_offline_assets.py
      build_manifests.py
      estimate_runtime.py
      inspect_run.py
      build_cleanup_inventory.py
  tests/
  docs/
```

- `scripts/main_methods/` 只包含本文主方法入口；`scripts/baselines/` 只包含对照方法；评价、制图和运维脚本分别放入自己的目录。禁止把所有算法塞入一个巨型运行脚本。
- CLI 脚本必须保持轻量，只负责参数解析和调用 `src/` 中的可测试模块；同一算法只能有一个权威实现。
- 攻击包不得依赖检测器模块；通过模块依赖测试保证主攻击进程无法导入目标检测代码。
- 正式配置、smoke 配置和历史兼容配置必须分目录，正式入口默认拒绝历史在线检测配置。

### 13.3 README 与最终整理规则

README 至少包含：项目定位、威胁模型、目录树、每个脚本的用途/输入/输出、配置说明、离线资产准备、正式运行命令、断点续跑、ETA、评价、结果目录、测试命令和常见错误。

`run_budget_selection_pilot.py`负责P0链路，输出与正式结果目录物理隔离。`run_formal_batch.py`是正式批次的唯一编排入口，必须先验证已冻结的$T_{\mathrm{formal}}$，再按“2-key smoke → 200-key正式攻击 → 最终离线评价 → 指定条件的离线检测统计量轨迹评价 → 表图生成”的顺序执行；各方法脚本仍保持独立，不得把方法实现复制进编排器。

README 必须有“脚本索引表”，逐个说明上节列出的脚本，避免实验完成后无法判断文件用途。还必须有“保留/清理表”：

- 提交 Git：`src/`、`scripts/`、`configs/`、`tests/`、README、依赖锁和小型 schema；
- 不提交 Git：模型、数据集、密钥张量、实验图片、检查点、日志、结果包、缓存和凭据；
- 永久研究记录：正式配置快照、manifest、最终逐key指标CSV、检测统计量轨迹CSV、最终汇总、论文表图、哈希和每个run的一次最终总结；
- 可清理候选：已验证结果包之外的下载临时文件、构建缓存、完成单元的 `resume_state` 和失败下载碎片。

`build_cleanup_inventory.py` 只能生成待清理路径、大小、类别和理由的 dry-run 清单，不能直接删除文件。所有最终清理仍由用户查看精确路径后授权。

### 13.4 断点续跑

- 最小可恢复实验单元固定为 `condition_id + key_id + method`。每个单元状态只能是 `PENDING/RUNNING/COMPLETE/FAILED`，由 append-only ledger 和原子 manifest 共同记录。
- 每 50 步原子保存当前活动单元的覆盖式 resume state：当前图像 tensor、已完成 step、损失历史、Python/NumPy/PyTorch CPU/CUDA RNG 状态、累计分项时间、输入哈希、resolved-config 哈希、协议版本和完整 Git SHA。
- resume 文件先写临时文件、flush/fsync 后再原子 rename；不得原地写半个文件。并行运行时每个 worker 使用独立状态文件和锁。
- 重新执行完全相同的命令时：验证协议/配置/代码/输入哈希；跳过经完整性验证的 COMPLETE 单元；从最近有效状态恢复 RUNNING 单元；只重跑缺失、损坏或 FAILED 的单元。
- SIGINT/SIGTERM 时尝试在当前更新完成后落盘并退出；突然断电或进程被杀时，最多损失最近 50 步。恢复后不得重复写 CSV 行、覆盖完整结果或把重复运行计入样本量。
- 若 resume state 损坏，只允许从第 0 步重跑该单元，并在 recovery log 中记录；不得从头重跑整个实验，也不得静默忽略损坏。
- 最终评价、最终统计和制图同样必须幂等，支持按已完成 condition/key 跳过并继续。

### 13.5 完全离线运行

- 联网资产准备与正式实验是两个物理分离阶段。`prepare_offline_assets.py` 仅在用户明确执行联网准备时下载缺失资产。
- 资产准备完成后生成 `assets.lock.json`，记录模型、revision、variant、tokenizer、scheduler、VAE、三种水印代码/权重、LPIPS、Inception/FID、数据 manifest 的绝对路径、大小和 SHA-256。
- 正式命令强制 `--offline`：设置 Hugging Face/Transformers/Diffusers 离线模式，全部加载使用 `local_files_only=True` 或锁定本地路径，并禁止运行期 HTTP 请求。
- 启动前必须逐项实际加载资产并执行离线 preflight。任何资产缺失、哈希不符或 revision 不符时立即失败；禁止静默联网、改用默认 cache、替换模型或省略指标。
- 必须在网络禁用状态下通过：资产 preflight、2-key smoke、攻击、断点恢复、最终检测、LPIPS 和 FID。

### 13.6 完成时间预估

- 生成正式代码后、全量实验启动前，必须在实际使用的 GPU、磁盘和并行 worker 数下运行 `estimate_runtime.py`。
- 估计器分别测量：资产/模型加载、参考生成、参考编码、Jain伪造、本文伪造、Jain移除、本文移除、Simple Averaging、常规变换、最终检测、错误密钥检测、最终LPIPS/SSIM/PSNR/FID，以及E3–E5 Proposed条件每100步临时检查点写入、读取、离线p值/bit accuracy评价、轨迹CSV/制图和校验后清理。
- 每类先完成至少 1 个 warm-up，再测量至少 3 个预注册实验单元；报告中位耗时、P90、显存峰值和吞吐量。不得用第一次包含模型下载或编译缓存的耗时直接外推。
- `runtime_estimate.json` 和 Markdown 报告必须给出：硬件/软件环境、各阶段单元数、已完成数、剩余数、串行估计、实际并行估计、P50 ETA、保守 P90 ETA、预计完成时间范围和磁盘需求。
- 总ETA按各阶段“剩余单元数 × 实测单元耗时 + 固定加载/I/O开销”求和，并把最终离线评价、轨迹离线评价和临时检查点I/O分别计入；磁盘预算必须覆盖`evaluation_spool/`与`curve_checkpoint_spool/`的峰值并发占用，不能只估计攻击优化时间。
- 正式运行中每完成一个实验单元更新 `progress.json`，根据最近完成单元的滚动中位数重新估计剩余时间。ETA 是硬件相关估计，不得承诺为确定完成时间。

### 13.7 新项目验收

- 单元测试覆盖 seed 派生、嵌套参考集、方法公式、配置校验、原子写入、resume、幂等跳过、离线加载和统计口径。
- 集成测试覆盖主动中断、强制终止、断网、损坏 resume state、缺失资产、配置哈希冲突和多 worker 锁。
- Tree-Ring 小规模回归测试必须证明新项目在相同输入和配置下复现旧项目 Jain/proposed 的最终输出或达到预注册数值容差；差异必须解释，不能以“重构”为由接受无记录变化。正式批次还必须测试 smoke 失败会阻止全量启动、smoke 通过会直接进入 200-key 阶段。
- 只有新项目完成上述验收后，才把它作为最终项目代码提交；旧项目和历史结果的删除不属于自动迁移步骤。

## 14. 参考依据

- Jain et al., *Forging and Removing Latent-Noise Diffusion Watermarks Using a Single Image*：单参考代理 VAE 攻击、λ 取值、模型设置和 Jain 指标体系。
- Yang et al., *Can Simple Averaging Defeat Modern Watermarks?*：像素域黑盒非配对均值差分、参考数量和失真对照。
- Wen et al., *Tree-Ring Watermarks: Fingerprints for Diffusion Images that are Invisible and Robust*：Tree-Ring 检测与常规图像变换评价。
- 本项目学习卡片、现有代码与历史实验结果只用于核对实现和证据边界，不自动视为正式实验结论。
