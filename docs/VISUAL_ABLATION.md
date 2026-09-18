# RingID / FR-LA visual ablation v3

This independent retained-image diagnostic is outside formal 200-key statistics.
It preserves existing v1/v2 outputs and does not change formal_protocol_v1.22.

## Frozen design

RingID with SD2-base target and SD1.4 proxy VAE, locked offline assets, master
seed 205, 150 fixed updates, learning rate .02, scalar encoding and attacks.
Five groups use disjoint sample pairs:

| Group | Keys | Content |
| --- | --- | --- |
| Forgery lambda | key_002/003 | elephant / airplane COCO covers |
| Forgery N | key_004/005 | train / boat COCO covers |
| Removal lambda | key_006/007 | lighthouse / snowy mountains |
| Removal N | key_008/009 | coffee cup / tropical beach |
| Removal beta | key_010/011 | violin / sunflower |

COCO covers are selected by the smallest image ID containing the assigned
category and none of the other three assigned categories. The six removal
prompts are frozen in configs/visual/ringid_fr_la_v3.yaml. Each key retains its
original generation seeds and 64-candidate budget; the first 25 accepted
references are selected. Removal targets remain the first selected reference
and participate in the aggregate. Samples are never selected by attack success.
Pixel hashes and 32x32 RGB thumbnail distances reject identical or near-identical
originals before attack. This gate is not proof of semantic diversity; review the
actual ten originals after preparation, before starting attacks. Failed content
checks stop the run and require review, with no automatic prompt reselection.

Lambda=10000/20000/50000 at N=5; N=1/5/25 at lambda=10000;
removal beta=1/1.5/2 at N=5 and lambda=10000. Other removal groups use beta=1.5.
All three settings in a group share the same original pair. There are 15
conditions, 30 attacks and exactly 10 shared originals plus 30 final PNGs.
No difference PNGs, online detection, final attack detection or quality metrics
are generated. Visual examples cannot establish ASR or general effectiveness.

## Execution and recovery

Defaults: configs/visual/ringid_fr_la_v3.yaml,
ringid_fr_la_visual_v3_20260918, configs/current/formal_v1p22.yaml,
local_assets/assets.lock.json. `--dry-run` needs no assets/GPU. `--phase preflight`
checks locked local assets and at least 5 GiB free space. Prepare and attack
require CUDA. There is no network download fallback.

Run prepare first and review originals, then attack and finalize:

```bash
python scripts/run_visual_ablation.py --dry-run
python -u scripts/run_visual_ablation.py --phase preflight
python -u scripts/run_visual_ablation.py --phase prepare
python -u scripts/run_visual_ablation.py --phase attack
python -u scripts/run_visual_ablation.py --phase finalize
```

`--phase run` launches all three phases in physically separate processes.
Preparation loads RingID generation/detection; attack loads only proxy VAE and
imports no watermark detector. No formal orchestrator is invoked. The filtered
preparation identity binds the v3 content settings; formal default inputs are
unchanged. Run identity binds full commit SHA, settings, config and asset lock.
Repeat the same command to resume; completed hashed units are skipped, active
units save RNG/image/identity state every 50 steps. Corrupt states stop the run.

## Outputs

Under the configured output_root/visual_ablation/<run_id>/:

- shared_preparation/: 250 references, candidate/key manifests and E0 checks.
- original_manifest.csv and images/originals/<key>.png: ten frozen originals.
- images/<task>/<condition>/<key>/final.png: thirty final outputs.
- units/: parameters, input identities, timings and original/final hashes.
- resume_state/: recovery states; logs/ and executions/: runtime records.
- image_manifest.csv: thirty attacks; panel_manifest.csv: thirty figure views.
- checksums.sha256 and visual_report.json: final integrity and image counts.

Reference PNGs are preparation assets in addition to the forty publication
source images. All diagnostic assets are retained for review; no automatic
cleanup occurs. Package only the named run, never repository/model/data caches.
After download verify archive SHA and output hashes, compose the five figures,
then integrate with the paper/Overleaf. Historical v1/v2 assets remain unchanged.
