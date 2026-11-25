"""
商品素材运营脚本（核心逻辑在 creative/，说明见 creative/__init__.py）

run_generate_copy_excel.py  需要素材时运行：生成卖点1/卖点2/推荐理由/短标题/宝贝名称
                            → 审核 Excel + 每店一个淘宝素材导入文件（不入库）
run_generate_video.py       需要主图视频时运行：图片 → 1:1 视频（默认 15 秒，字幕=短标题/卖点/推荐理由）+ 视频清单
"""
