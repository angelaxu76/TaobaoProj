# Barbour 图片流水线

参数只改 `image_session.py`。不知道该跑哪一步时，运行 `status.py`。

```
准备 repulibcation/codes.xlsx
        │
step1_prepare.py        下载 → 防指纹 → 入长期库 → 选图 → 人物/细节分类
        │
  ✋ 剔除 classify/person 里不适合换脸的图（还想用的移到 classify/detail）
        │
step2_faceswap.py       加 _front_ 关键字 → 上传 R2 → 换脸 → 质量对比 → 自动重试
  （FACESWAP_BATCH="men" 跑一次，"women" 再跑一次）
        │
  ✋ 检查换脸效果（效果差的移到 linkfox_bad，重跑 step2 会重换）
        │
step3_cutout_split.py   细节图按抠图难易拆成 detail / detail_difficult
        │
  ✋ 复核两个目录，判断错的互相移动
  ✋ 把平铺图从 classify/detail 挑到 classify/平铺
        │
step4_finalize_html.py  抠图（detail / 平铺 / 换脸图）→ 平铺图改名 _details
                        → 汇总 → 按优先级改名 __N → HTML → 渲染 → 裁边
        │
publish_generate_excel.py（发布 Excel，不属于图片流程）
```

运行方式（项目根目录下）：

```
python brands/barbour/pipeline/image/status.py
python brands/barbour/pipeline/image/step1_prepare.py
...
```

## 目录流转（都在 repulibcation/ 下）

| 目录 | 谁写入 | 谁读取 |
|---|---|---|
| `codes.xlsx` | 人工 | step1 选图、step4 HTML |
| `images_selected/` | step1 | step1 分类 |
| `classify/person/` | step1 | step2 |
| `classify/detail/` | step1 / step3 | step4 抠图 |
| `classify/detail_difficult/` | step3 | step4 原样复制 |
| `classify/平铺/` | 人工（step3 后从 detail 挑） | step4 抠图（原图不改名） |
| `linkfox_output/` | step2 | step4 抠图 |
| `linkfox_bad/` | step2 质量对比 / 人工 | — |
| `faceswap_codes_{批次}.xlsx` | step2（未完成编码） | step2 |
| `linkfox_processed/` | step4 | step4 改名、HTML |
| `html_cutter/{description,first_page}/` | step4 | 最终产出 |

## 常见情况

- **只跑某几个子步骤**：step1 有 `RUN_DOWNLOAD / RUN_SELECT / RUN_CLASSIFY`；step4 有 9 个
  子步骤开关 `RUN_TAG_DETAILS ~ RUN_RENDER`，不需要的设为 False。step4 开头会打印本次勾选了哪些。
- **平铺图排第 2 位**：每款挑一张或几张平铺图放进 `classify/平铺`（文件名保持 `{code}_{数字}`）。
  step4 子步骤 4 抠图后，把每款编号最小的一张输出图改名为 `linkfox_processed/{code}_details.jpg`，
  同款其余平铺图保持原名，排在优先级图之后。没挑平铺图的编码没有 `_details`，细节图排在换脸图之后；
  想让它们也自动选一张，就打开子步骤 1 `RUN_TAG_DETAILS`。
  `ops/image_rename/run_rename_flat_and_cutout_details.py` 是这一步的独立旧版，走流水线时不用再跑它。
- **step4 提示 linkfox_processed 已改名为 __N**：改名后不能再往里加图；要重新抠图就先清空该目录。
- **调整首页 / 详情页选哪张图**：改 `ops/image_rename/image_priority_config.py` 的 barbour 段，
  然后清空 `linkfox_processed` 重跑 step4（改名只能在未改名的文件上做）。
- **换脸扣点**：每张 20 点；step2 每轮开始前会打印预计点数，没有进展时自动停止重试。
- **别的品牌**：ops/ 下的换脸、上传、抠图脚本保持通用，本目录只是 Barbour 的编排层，
  其他品牌可以照这个结构建自己的 `pipeline/image/`。
